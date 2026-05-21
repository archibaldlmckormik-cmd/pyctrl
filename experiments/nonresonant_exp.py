# author: yannik fontana, creation date: 12.05.2026
"""
Collection of nonresonant experiments.
Typically the only laser involved is a green 532nm laser exciting the emitter.
The swepts parameters and means of detection are experiment specific.
"""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime
from copy import deepcopy

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from experiments.generic_exp import GenericExp
from toolbox.hardware.oneway_relock import oneway_relock_mass
from toolbox.software.datamanagement import datastructures as ds

logger = logging.getLogger(__name__)

# SCANXY_Z

class ScanXY_Z(GenericExp):
    """
    Excite with green laser, in a quasi CW fashion
    For a given grid of x and y cavity positions, scans the cavity along the z axis and records the fluorescence signal on an APD.
    for each z scan, an updated cavity resonance voltage is calculated.
    """
    def __init__(self, *args, **kwargs):
        # relay the __init__ of the Generic_Exp class
        super().__init__(*args, **kwargs)

    def setup(self):
        """
        Setup instrument, data structure and figure list for the ScanXY_Z experiment
        Overwrite GenericExp setup method
        """
        # access the instruments
        self.opx = self.session.get("opx")
        self.dac = self.session.get("dac")
        self.shutter = self.session.get("shutterSH05")
        # make sure the dac channels 1,2,3 are on
        for channel in [1,2,3]:
            self.dac.channel_toggleONOFF(channel) if self.dac.getstatus(channel) == "OFF" else None


        # define the IO data structure for the experiment
        self.data = ds.ScanXY_ZData()

        # create the figure list
        self.result_figs: list[Any] = []

    def pre_run(self):
        """
        Validate the critical inputs for the experiment and iniotilialize the signal arrays etc
        """
        # check if data is here at all:
        self.check_for_data(ds.ScanXY_ZData)
        # check if critical inputs are not none
        critical_inputs = [self.data.cavity.x, self.data.cavity.y, self.data.cavity.z,
                           self.data.pulses["AOMg1"].duration, self.data.pulses["AOMg1"].aom_amplitude]
        for input in critical_inputs:
            if input is None:
                logger.error(f"Critical input {input} is None")
                raise ValueError(f"Critical input {input} is None")

        # check if pulse duration is legit by calling seconds_to_cycles
        self.opx.seconds_to_cycles(self.data.pulses["AOMg1"].duration, name="pulse_duration")
        # check if data.cavity.x, data.cavity.y are numpy arrays with at least one element
        if not isinstance(self.data.cavity.x, np.ndarray) or len(self.data.cavity.x) == 0:
            self.data.cavity.x = np.array([self.dac.voltage[2]])
        if not isinstance(self.data.cavity.y, np.ndarray) or len(self.data.cavity.y) == 0:
            self.data.cavity.y = np.array([self.dac.voltage[3]])
        
        # build the signal arrays, init to zero
        self.data.signals["counts"] = np.zeros((self.data.cavity.y.size, self.data.cavity.x.size, self.data.cavity.z.size))
        self.data.signals["z_offset"] = np.zeros((len(self.data.cavity.y), len(self.data.cavity.x)))
        
        # refresh timestamp
        self.data.timestamp = datetime.now()

    def run(self):
        """
        Run the ScanXY_Z experiment
        """
        # define a few shorthands
        # the actual z voltage range for each x,y pixel
        z_now = deepcopy(self.data.cavity.z)
        # the pulse duration in seconds
        pulse_duration = self.data.pulses["AOMg1"].duration
        # the pulse amplitude in volts
        pulse_amplitude = self.data.pulses["AOMg1"].aom_amplitude

        # start timetag to measure experiment runtime
        start_time = datetime.now()
        # loop along the y axis
        for y_idx, y_value in enumerate(self.data.cavity.y):
            # smoothly ramp the y voltage
            self.dac.voltage.smooth_ramp(3, y_value)

            # loop along the x axis
            for x_idx, x_value in enumerate(self.data.cavity.x):
                # smoothly ramp the x voltage
                self.dac.voltage.smooth_ramp(2, x_value)

                # scan the z axis and measure
                # set the z voltage
                self.dac.voltage.smooth_ramp(1, z_now[0])
                # aquire the signal and center of mass voltage
                counts, center_v = oneway_relock_mass(self.opx, self.dac, self.shutter, z_now, pulse_duration, AOMg1=pulse_amplitude)
                # store the counts
                self.data.signals["counts"][y_idx, x_idx, :] = counts
                # store the center of mass voltage
                self.data.signals["z_offset"][y_idx, x_idx] = center_v-self.data.cavity.z.mean()
                # adjust the z voltage by the offset
                z_now = self.data.cavity.z + self.data.signals["z_offset"][y_idx, x_idx]
        
        # return to starting voltages on y x and z
        self.dac.voltage.smooth_ramp(3, self.data.cavity.y[0])
        self.dac.voltage.smooth_ramp(2, self.data.cavity.x[0])
        self.dac.voltage.smooth_ramp(1, self.data.cavity.z[0] + self.data.signals["z_offset"][0, 0])

        # calculate the experiment runtime 
        runtime = datetime.now() - start_time
        # signal that this experiment completed successfully
        self.logrun(runtime=runtime)
        # save in data:
        self.data.run_time = runtime.total_seconds()

        # save the data
        self.data.save()
        # update the data.tag field with experiment runtime
        self.data.tag.append(f"runtime: {runtime.total_seconds()} s")
        # update the data.tag field with pulse amplitude
        aom = self.data.pulses["AOMg1"]
        self.data.tag.append(f"pulse_amplitude: {aom.aom_amplitude} V")
        self.data.tag.append(f"pulse_duration: {aom.duration} s")
        self.data.tag.append(f"pulse_power: {aom.power} W")

    @classmethod
    def plot(cls, data: ds.ScanXY_ZData) -> list[go.Figure]:
        """
        Build Plotly figures for ScanXY_Z data (no lab journal write).

        Layout depends on cavity x/y grid size (1D strip, 2D map, or single z scan).
        """
        if data is None or not isinstance(data, ds.ScanXY_ZData):
            logger.error("ScanXY_Z.plot: data is not a ScanXY_ZData instance")
            raise ValueError("ScanXY_Z.plot: data is not a ScanXY_ZData instance")

        x = np.asarray(data.cavity.x, dtype=float).reshape(-1)
        y = np.asarray(data.cavity.y, dtype=float).reshape(-1)
        z = np.asarray(data.cavity.z, dtype=float).reshape(-1)

        if "counts" not in data.signals or "z_offset" not in data.signals:
            logger.error("ScanXY_Z.plot: signals must contain counts and z_offset")
            raise ValueError("ScanXY_Z.plot: missing counts or z_offset in signals")

        counts = np.asarray(data.signals["counts"], dtype=float)
        z_offset = np.asarray(data.signals["z_offset"], dtype=float)

        ny, nx, nz = y.size, x.size, z.size
        expected_counts = (ny, nx, nz)
        if counts.shape != expected_counts:
            logger.error(
                "ScanXY_Z.plot: counts shape %s != expected %s",
                counts.shape,
                expected_counts,
            )
            raise ValueError(f"counts shape {counts.shape} != {expected_counts}")

        if z_offset.shape != (ny, nx):
            logger.error(
                "ScanXY_Z.plot: z_offset shape %s != expected (%d, %d)",
                z_offset.shape,
                ny,
                nx,
            )
            raise ValueError(f"z_offset shape {z_offset.shape} != ({ny}, {nx})")

        ice = px.colors.sequential.ice
        rdbu = px.colors.diverging.RdBu_r

        def z_offset_colorscale_limits() -> tuple[float, float]:
            lim = float(np.nanmax(np.abs(z_offset)))
            if lim == 0:
                lim = 1.0
            return -lim, lim

        # Case 3: single (x, y) pixel — one z scan only
        if nx == 1 and ny == 1:
            z_axis = z + z_offset[0, 0]
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=z_axis,
                    y=counts[0, 0, :],
                    mode="lines+markers",
                    name="counts",
                )
            )
            fig.update_layout(
                title="ScanXY_Z — z scan",
                xaxis_title="Cavity z (V)",
                yaxis_title="Counts",
                annotations=[
                    dict(
                        text=f"x = {x[0]:.4f} V, y = {y[0]:.4f} V",
                        xref="paper",
                        yref="paper",
                        x=0.02,
                        y=0.98,
                        showarrow=False,
                    )
                ],
            )
            return [fig]

        # Case 2: line scan along x or y
        if nx == 1 or ny == 1:
            fig = make_subplots(
                rows=1,
                cols=3,
                subplot_titles=(
                    "Z profile at max signal",
                    "Max counts along z",
                    "Z offset",
                ),
            )
            if ny == 1:
                ix_star, _ = np.unravel_index(
                    np.nanargmax(counts[0, :, :]), counts[0, :, :].shape
                )
                ix_star = int(ix_star)
                z_axis = z + z_offset[0, ix_star]
                fig.add_trace(
                    go.Scatter(
                        x=z_axis,
                        y=counts[0, ix_star, :],
                        mode="lines+markers",
                        name="z profile",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_annotation(
                    text=f"x = {x[ix_star]:.4f} V, y = {y[0]:.4f} V",
                    xref="x domain",
                    yref="y domain",
                    x=0.02,
                    y=0.98,
                    showarrow=False,
                    row=1,
                    col=1,
                )
                max_along_z = counts.max(axis=2)[0, :]
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=max_along_z,
                        mode="lines+markers",
                        name="max counts",
                    ),
                    row=1,
                    col=2,
                )
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=z_offset[0, :],
                        mode="lines+markers",
                        name="z offset",
                    ),
                    row=1,
                    col=3,
                )
                fig.update_xaxes(title_text="Cavity z (V)", row=1, col=1)
                fig.update_yaxes(title_text="Counts", row=1, col=1)
                fig.update_xaxes(title_text="Cavity x (V)", row=1, col=2)
                fig.update_yaxes(title_text="Counts", row=1, col=2)
                fig.update_xaxes(title_text="Cavity x (V)", row=1, col=3)
                fig.update_yaxes(title_text="Z offset (V)", row=1, col=3)
            else:
                iy_star, _ = np.unravel_index(
                    np.nanargmax(counts[:, 0, :]), counts[:, 0, :].shape
                )
                iy_star = int(iy_star)
                z_axis = z + z_offset[iy_star, 0]
                fig.add_trace(
                    go.Scatter(
                        x=z_axis,
                        y=counts[iy_star, 0, :],
                        mode="lines+markers",
                        name="z profile",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_annotation(
                    text=f"x = {x[0]:.4f} V, y = {y[iy_star]:.4f} V",
                    xref="x domain",
                    yref="y domain",
                    x=0.02,
                    y=0.98,
                    showarrow=False,
                    row=1,
                    col=1,
                )
                max_along_z = counts.max(axis=2)[:, 0]
                fig.add_trace(
                    go.Scatter(
                        x=y,
                        y=max_along_z,
                        mode="lines+markers",
                        name="max counts",
                    ),
                    row=1,
                    col=2,
                )
                fig.add_trace(
                    go.Scatter(
                        x=y,
                        y=z_offset[:, 0],
                        mode="lines+markers",
                        name="z offset",
                    ),
                    row=1,
                    col=3,
                )
                fig.update_xaxes(title_text="Cavity z (V)", row=1, col=1)
                fig.update_yaxes(title_text="Counts", row=1, col=1)
                fig.update_xaxes(title_text="Cavity y (V)", row=1, col=2)
                fig.update_yaxes(title_text="Counts", row=1, col=2)
                fig.update_xaxes(title_text="Cavity y (V)", row=1, col=3)
                fig.update_yaxes(title_text="Z offset (V)", row=1, col=3)

            fig.update_layout(title_text="ScanXY_Z", height=450, showlegend=False)
            return [fig]

        # Case 1: 2D x–y grid
        if nx <= 1 or ny <= 1:
            logger.error("ScanXY_Z.plot: unexpected grid shape nx=%d ny=%d", nx, ny)
            raise ValueError("ScanXY_Z.plot: invalid cavity x/y grid")

        iy, ix, _ = np.unravel_index(np.nanargmax(counts), counts.shape)
        iy, ix = int(iy), int(ix)
        z_axis = z + z_offset[iy, ix]
        max_along_z = counts.max(axis=2)
        zmin, zmax = z_offset_colorscale_limits()

        fig = make_subplots(
            rows=1,
            cols=3,
            subplot_titles=(
                "Z profile at global max",
                "Max counts along z",
                "Z offset",
            ),
        )
        fig.add_trace(
            go.Scatter(
                x=z_axis,
                y=counts[iy, ix, :],
                mode="lines+markers",
                name="z profile",
            ),
            row=1,
            col=1,
        )
        fig.add_annotation(
            text=f"x = {x[ix]:.4f} V, y = {y[iy]:.4f} V",
            xref="x domain",
            yref="y domain",
            x=0.02,
            y=0.98,
            showarrow=False,
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Heatmap(
                x=x,
                y=y,
                z=max_along_z,
                colorscale=ice,
                colorbar=dict(title="Counts", len=0.6, y=0.5),
            ),
            row=1,
            col=2,
        )
        fig.add_trace(
            go.Heatmap(
                x=x,
                y=y,
                z=z_offset,
                colorscale=rdbu,
                zmid=0,
                zmin=zmin,
                zmax=zmax,
                colorbar=dict(title="Z offset (V)", len=0.6, y=0.5),
            ),
            row=1,
            col=3,
        )
        fig.update_xaxes(title_text="Cavity z (V)", row=1, col=1)
        fig.update_yaxes(title_text="Counts", row=1, col=1)
        fig.update_xaxes(title_text="Cavity x (V)", row=1, col=2)
        fig.update_yaxes(title_text="Cavity y (V)", row=1, col=2)
        fig.update_xaxes(title_text="Cavity x (V)", row=1, col=3)
        fig.update_yaxes(title_text="Cavity y (V)", row=1, col=3)
        fig.update_layout(title_text="ScanXY_Z", height=450, showlegend=False)
        return [fig]

