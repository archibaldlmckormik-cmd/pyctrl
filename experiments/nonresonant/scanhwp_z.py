# author: yannik fontana, creation date: 22.05.2026
"""
Nonresonant HWP scan: step half-wave plate, z-scan cavity, record fluorescence.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime
from typing import Any
from time import sleep

import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from pyctrl.experiments.generic_exp import GenericExp
from pyctrl.toolbox.hardware.oneway_relock import oneway_relock_mass
from pyctrl.toolbox.software.datamanagement import datastructures as ds

logger = logging.getLogger(__name__)


class ScanHWP_Z(GenericExp):
    """
    Scan the the HWP vs cavity length.
    Non-resonant excitation with green laser
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setup(self) -> None:
        """Setup instruments, data structure, and figure list."""
        self.opx = self.session.get("opx")
        self.dac = self.session.get("dac")
        self.shutter = self.session.get("shutter")
        self.waveplates = self.session.get("waveplates")

        for channel in (1, 2, 3):
            if self.dac.getstatus(channel) == "OFF":
                self.dac.channel_toggleONOFF(channel)

        self.data = ds.ScanHWP_ZData()
        self.result_figs: list[Any] = []

    def pre_run(self) -> None:
        """Validate inputs and allocate signal arrays."""
        self.check_for_data(ds.ScanHWP_ZData)

        aom = self.data.pulses["AOMg1"]
        critical_inputs = [
            self.data.cavity.z,
            aom.duration,
            aom.aom_amplitude,
            self.data.hwp.get("step_voltage"),
            self.data.hwp.get("step_number"),
        ]
        for item in critical_inputs:
            if item is None:
                logger.error("ScanHWP_Z.pre_run: critical input is None")
                raise ValueError("ScanHWP_Z.pre_run: critical input is None")

        self.opx.seconds_to_cycles(aom.duration, name="pulse_duration")

        self.data.cavity.x = np.array([float(self.dac.voltage[2])])
        self.data.cavity.y = np.array([float(self.dac.voltage[3])])

        n_steps = int(self.data.hwp["step_number"])
        if n_steps < 1:
            raise ValueError(f"step_number must be >= 1, got {n_steps}")

        z = np.asarray(self.data.cavity.z, dtype=float).reshape(-1)
        if z.size == 0:
            raise ValueError("cavity.z must be a non-empty array")
        self.data.cavity.z = z

        self.data.signals["counts"] = np.zeros((n_steps + 1, z.size))
        self.data.signals["z_offset"] = np.zeros(n_steps + 1)
        self.data.timestamp = datetime.now()

    def run(self) -> None:
        """Run the ScanHWP_Z experiment."""
        self.pre_run()

        z_now = deepcopy(self.data.cavity.z)
        pulse_duration = self.data.pulses["AOMg1"].duration
        pulse_amplitude = self.data.pulses["AOMg1"].aom_amplitude
        n_steps = int(self.data.hwp["step_number"])
        step_voltage = int(round(float(self.data.hwp["step_voltage"])))
        z_mean = float(self.data.cavity.z.mean())

        hwp = self.waveplates.HWP
        hwp.volt = step_voltage
        hwp.stepper_on()

        start_time = datetime.now()
        try:
            for scan_idx in range(n_steps + 1):
                if scan_idx > 0:
                    hwp.step(1)
                    # pause for 0.5 seconds
                    sleep(0.5)

                self.dac.voltage.smooth_ramp(1, z_now[0])
                counts, center_v = oneway_relock_mass(
                    self.opx,
                    self.dac,
                    self.shutter,
                    z_now,
                    pulse_duration,
                    AOMg1 = pulse_amplitude,
                )
                self.data.signals["counts"][scan_idx, :] = counts
                self.data.signals["z_offset"][scan_idx] = center_v - z_mean
                z_now = self.data.cavity.z + self.data.signals["z_offset"][scan_idx]
        finally:
            hwp.stepper_off()

        self.dac.voltage.smooth_ramp(
            1, self.data.cavity.z[0] + self.data.signals["z_offset"][0]
        )

        runtime = datetime.now() - start_time
        self.logrun(runtime=runtime)
        self.data.run_time = runtime.total_seconds()
        # tags
        self.data.tag.append(f"runtime: {runtime.total_seconds()} s")
        aom = self.data.pulses["AOMg1"]
        self.data.tag.append(f"laser_id: {aom.laser_id}")
        self.data.tag.append(f"pulse_amplitude: {aom.aom_amplitude} V")
        self.data.tag.append(f"pulse_duration: {aom.duration} s")
        self.data.tag.append(f"pulse_power: {aom.power} W")
        self.data.tag.append(f"hwp_step_voltage: {step_voltage} V")
        self.data.tag.append(f"hwp_step_number: {n_steps}")
        self.data.tag.append(f"hwp_z_scans: {n_steps + 1}")

        self.data.save()


    @classmethod
    def plot(cls, data: ds.ScanHWP_ZData) -> list[go.Figure]:
        """Heatmap of counts vs z/steps and line plot of absolute cavity z offset."""
        if data is None or not isinstance(data, ds.ScanHWP_ZData):
            logger.error("ScanHWP_Z.plot: data is not a ScanHWP_ZData instance")
            raise ValueError("ScanHWP_Z.plot: data is not a ScanHWP_ZData instance")

        if "counts" not in data.signals or "z_offset" not in data.signals:
            raise ValueError("ScanHWP_Z.plot: missing counts or z_offset in signals")

        z = np.asarray(data.cavity.z, dtype=float).reshape(-1)
        n_steps = int(data.hwp["step_number"])
        n_scans = n_steps + 1
        step_voltage = float(data.hwp["step_voltage"])
        step_x_title = f"Steps × {step_voltage:g} V"

        counts = deepcopy(np.asarray(data.signals["counts"], dtype=float))
        z_offset = np.asarray(data.signals["z_offset"], dtype=float).reshape(-1)

        if counts.shape != (n_scans, z.size):
            raise ValueError(
                f"counts shape {counts.shape} != expected ({n_scans}, {z.size})"
            )
        if z_offset.shape != (n_scans,):
            raise ValueError(f"z_offset shape {z_offset.shape} != ({n_scans},)")

        aom = data.pulses["AOMg1"]
        if aom.duration is not None:
            counts = counts / aom.duration
            signal_units = "Counts/s"
        else:
            signal_units = "Counts"

        zmax = float(np.nanmax(counts))
        if zmax == 0:
            zmax = 1.0

        ice = px.colors.sequential.ice
        x_centers = np.arange(n_scans) + 0.5

        fig_heatmap = go.Figure(
            data=go.Heatmap(
                x=x_centers,
                y=z,
                z=counts.T,
                colorscale=ice,
                zmin=0,
                zmax=zmax,
                colorbar=dict(title=signal_units),
            )
        )
        fig_heatmap.update_layout(
            title="ScanHWP_Z — counts",
            xaxis_title=step_x_title,
            yaxis_title="Cavity z (V)",
            xaxis=dict(range=[0, n_scans]),
        )

        z_mean = float(z.mean())
        z_abs = z_mean + z_offset
        z_abs_min = float(np.nanmin(z_abs))
        z_abs_max = float(np.nanmax(z_abs))

        fig_line = go.Figure()
        fig_line.add_trace(
            go.Scatter(
                x=x_centers,
                y=z_abs,
                mode="lines+markers",
                name="z offset (absolute)",
            )
        )
        fig_line.add_hline(
            y=z_abs_min,
            line_dash="dash",
            line_color="gray",
            annotation_text="min",
            annotation_position="right",
        )
        fig_line.add_hline(
            y=z_abs_max,
            line_dash="dash",
            line_color="gray",
            annotation_text="max",
            annotation_position="right",
        )
        fig_line.update_layout(
            title="ScanHWP_Z — z offset",
            xaxis_title=step_x_title,
            yaxis_title="Cavity z (V)",
            xaxis=dict(range=[0, n_scans]),
            showlegend=False,
        )

        return [fig_heatmap, fig_line]
