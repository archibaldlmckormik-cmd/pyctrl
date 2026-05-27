# author: yannik fontana, creation date: 05.05.2026
"""
Quantum MAchine OPX+ driver, 
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from copy import deepcopy

from qm import QuantumMachinesManager
from qm import qua
from qm.jobs.running_qm_job import RunningQmJob
import qualang_tools.bakery as bakery
from toolbox.software.path_config import get_qmconfigpath

logger = logging.getLogger(__name__)


class QMConfig:
    """
    Opens, parses and conditions the TOML quantum machine configuration file.

    Parameters
    ----------
    config_file:
        Path to the QM config TOML. If omitted, uses ``get_qmconfigpath()`` (``qmconfigpath``
        in path config — ``path_config.local.toml`` or ``path_config.toml``).
    """

    def __init__(self, config_file: str | Path | None = None):
        """
        Initializes the QMConfig object,loads the config from file and bakes the operations.
        instances attributes:
        - config: the config as a dictionary
        - baked: the baked operations as a dictionary
        ancillary attributes:
        - config_from_file: the config from file as a dictionary
        - baked_from_file: the baked operations from file as a dictionary
        
        """
        path = get_qmconfigpath() if config_file is None else Path(config_file)
        raw_cfg = self.load_opx_config(path)
        self.config_from_file = self.dict_list_to_tuple(raw_cfg)
        self.baked_from_file = self.config_from_file.pop("baked_pulses",{})
        self.config = deepcopy(self.config_from_file)
        self.baked = {}
        try:
            self.bake_all()
        except Exception as e:
            logger.error("Error during pulse baking operations: %s", e)
            raise

    def load_opx_config(self, config_path: Path):
        """
        Loads the OPX configuration file from supplied/default path
        and returns a nested dictionnary replacing lists by tuples
        """
        try:
            with open(config_path, "rb") as f:
                    raw_cfg = tomllib.load(f)
        except OSError as exc:
            logger.error("Session: cannot read instrument config %s: %s", config_path, exc)
            raise
        except tomllib.TOMLDecodeError as exc:
            logger.error("Session: invalid TOML in %s: %s", config_path, exc)
            raise
        return raw_cfg

    def dict_list_to_tuple(self,d: dict) -> dict:
        """
        searches through a nested dictionary and replaces all lists with tuples
        """
        for key, value in d.items():
            if isinstance(value, list):
                d[key] = tuple(value)
            elif isinstance(value, dict):
                d[key] = self.dict_list_to_tuple(value)
        return d

    def bake_all(self):
        """
        Bakes all the operations in the baked_from_file dictionary.
        """
        for name, spec in self.baked_from_file.items():
            element = spec['element']
            sampling = spec['sampling']
            padding = spec['padding']
            I_samples = spec['I_samples']
            Q_samples = spec.get('Q_samples', [])
            samples = [I_samples, Q_samples] if Q_samples else I_samples
            with bakery.baking(self.config, padding_method = padding ,sampling_rate = sampling) as b:
                b.add_op(name, element, samples)
                b.play(name, element)

            self.baked[name] = b   # store handle by name

class Opx:
    """
    Driver initializing and running QUA program on an OPX+ quantum machine.
    
    Parameters
    ----------
    host: str
        Hostname or IP address of the OPX+ quantum machine.
    port: int
        Port number of the OPX+ quantum machine.
    """

    CLOCK_CYCLE_NS: int = 4
    MIN_PULSEWIDTH_NS: int = 16

    def __init__(self, IP_address: str, port: int = 80):
        self.qmm = QuantumMachinesManager(host=IP_address, port=port)
        self._qm = None
        self._running_job: RunningQmJob | None = None

    def open_quantum_machine(self, config: dict):
        """Open a QM with a given config dict, closing any previous one."""
        if self._qm is not None:
            self._qm.close()
        self._qm = self.qmm.open_qm(config)
        return self._qm

    @property
    def qm(self):
        if self._qm is None:
            raise RuntimeError("No quantum machine open. Call open_quantum_machine() first.")
        return self._qm

    def execute(self, program):
        """Compile and run a QUA program, return the job."""
        return self.qm.execute(program)

    def close(self):
        """
        Closes the OPX quantum machine instance, halting any running job.
        """
        if self._running_job is not None:
            try:
                self._running_job.halt()
            except Exception as exc:
                logger.warning("close: failed to halt running OPX job: %s", exc)
                raise RuntimeError("Failed to halt running OPX job.") from exc
            self._running_job = None

        if self._qm is not None:
            self._qm.close()
            self._qm = None
    
    # Utility method to convert seconds to cycles
    @classmethod
    def seconds_to_cycles(cls, seconds: float, name: str = "duration") -> int:
        """Convert a duration in seconds to an integer number of OPX clock cycles."""
        if seconds <= 0:
            logger.error("Opx: %s must be > 0, got %s", name, seconds)
            raise ValueError(f"{name} must be > 0")

        ns = float(seconds) * 1e9
        ns_i = int(round(ns))
        if abs(ns - ns_i) > 1e-6:
            logger.error(
                "Opx: %s=%s s does not map to an integer ns duration.",
                name,
                seconds,
            )
            raise ValueError(f"{name} must map to an integer number of ns")

        if ns_i < cls.MIN_PULSEWIDTH_NS:
            logger.error(
                "Opx: %s=%d ns is below minimum pulse length %d ns.",
                name,
                ns_i,
                cls.MIN_PULSEWIDTH_NS,
            )
            raise ValueError(f"{name} must be >= {cls.MIN_PULSEWIDTH_NS} ns")

        if ns_i % cls.CLOCK_CYCLE_NS != 0:
            logger.error(
                "Opx: %s=%d ns is not divisible by %d ns.",
                name,
                ns_i,
                cls.CLOCK_CYCLE_NS,
            )
            raise ValueError(f"{name} must be divisible by {cls.CLOCK_CYCLE_NS} ns")

        return ns_i // cls.CLOCK_CYCLE_NS

    # Measurement methods needing the opx as the sole hardware
    def quasicw_counts(
        self,
        t_s: float,
        *,
        AOMg1: float | None = None,
        AOMr1: float | None = None,
        AOMr2: float | None = None,
        EOMr2: float | None = None,
        apd: int | None = None,
        chunk_s: float = 0.01,
        max_tags: int = 8192,
    ) -> int:
        """
        Measure total APD counts in a quasi-CW fashion with chunked time-tagging windows.

        - Optional optical elements are played when their amplitude is provided.
        - Optical drive is started once for the full duration (long ``play``), while APD readout is chunked.
        - By default (``apd=None``), APD1 and APD2 counts are summed on machine and returned as one scalar.
        - With ``apd=1`` or ``apd=2``, only that analog input is measured and aligned.
        - Timing is validated against OPX clock constraints (4 ns cycle, >=16 ns pulse).
        """
        # collect active optical elements
        active_elements: dict[str, float] = {}
        for name, value in {
            "AOMg1": AOMg1,
            "AOMr1": AOMr1,
            "AOMr2": AOMr2,
            "EOMr2": EOMr2,
        }.items():
            if value is None:
                continue
            active_elements[name] = float(value)

        if apd not in (None, 1, 2):
            logger.error(
                "quasicw_counts: apd must be None, 1, or 2, got %s",
                apd,
            )
            raise ValueError("apd must be None, 1, or 2")

        apd_elements = ["APD1", "APD2"] if apd is None else [f"APD{apd}"]

        if apd is None:

            def _measure_chunk(
                dur_cycles: int, counts1, counts2, total, times1, times2
            ) -> None:
                dur_ns = dur_cycles * self.CLOCK_CYCLE_NS
                qua.measure(
                    "record_photons",
                    "APD1",
                    None,
                    qua.time_tagging.analog(times1, dur_ns, counts1),
                )
                qua.measure(
                    "record_photons",
                    "APD2",
                    None,
                    qua.time_tagging.analog(times2, dur_ns, counts2),
                )
                qua.assign(total, total + counts1 + counts2)

        else:

            def _measure_chunk(dur_cycles: int, counts, total, times) -> None:
                dur_ns = dur_cycles * self.CLOCK_CYCLE_NS
                qua.measure(
                    "record_photons",
                    apd_elements[0],
                    None,
                    qua.time_tagging.analog(times, dur_ns, counts),
                )
                qua.assign(total, total + counts)

        # check if the OPX quantum machine is open
        try:
            _ = self.qm
        except Exception as exc:
            logger.error("quasicw_counts: OPX quantum machine is not open: %s", exc)
            raise RuntimeError("OPX quantum machine is not open.") from exc

        if max_tags <= 0:
            logger.error("quasicw_counts: max_tags must be > 0, got %s", max_tags)
            raise ValueError("max_tags must be > 0")

        if not active_elements:
            logger.error("quasicw_counts: no active optical element amplitude provided.")
            raise ValueError("At least one element amplitude must be provided.")

        total_cycles = self.seconds_to_cycles(t_s, name="t_s")
        if chunk_s <= 0:
            logger.warning(
                "quasicw_counts: chunk_s=%s is invalid, using minimum chunk of %d ns.",
                chunk_s,
                self.MIN_PULSEWIDTH_NS,
            )
            chunk_cycles = self.MIN_PULSEWIDTH_NS // self.CLOCK_CYCLE_NS
        else:
            chunk_ns = int(round(float(chunk_s) * 1e9))
            chunk_ns = max(self.MIN_PULSEWIDTH_NS, chunk_ns)
            chunk_cycles = max(1, int(round(chunk_ns / self.CLOCK_CYCLE_NS)))

        n_full = total_cycles // chunk_cycles
        rem_cycles = total_cycles % chunk_cycles

        if n_full == 0 and rem_cycles > 0:
            n_full = 1
            rem_cycles = 0
            chunk_cycles = total_cycles

        aligned_elements = list(active_elements.keys()) + apd_elements

        with qua.program() as prog:
            total = qua.declare(qua.int)
            i = qua.declare(qua.int)
            total_st = qua.declare_stream()

            qua.assign(total, 0)

            if apd is None:
                counts1 = qua.declare(qua.int)
                counts2 = qua.declare(qua.int)
                times1 = qua.declare(qua.int, size=max_tags)
                times2 = qua.declare(qua.int, size=max_tags)
            else:
                counts = qua.declare(qua.int)
                times = qua.declare(qua.int, size=max_tags)

            # Align active optical and selected APD element(s) once before starting.
            qua.align(*aligned_elements)
            # Start optical drive once for the full duration (quasi-CW).
            for elem_name, amp in active_elements.items():
                qua.play("fire_cst" * qua.amp(amp), elem_name, duration=total_cycles)

            # Chunk only the APD readout while the optical drive is ongoing.
            with qua.for_(i, 0, i < n_full, i + 1):
                if apd is None:
                    _measure_chunk(chunk_cycles, counts1, counts2, total, times1, times2)
                else:
                    _measure_chunk(chunk_cycles, counts, total, times)

            if rem_cycles > 0:
                if apd is None:
                    _measure_chunk(rem_cycles, counts1, counts2, total, times1, times2)
                else:
                    _measure_chunk(rem_cycles, counts, total, times)

            qua.save(total, total_st)
            with qua.stream_processing():
                total_st.save("total_counts")

        job = self.execute(prog)
        handles = job.result_handles
        handles.wait_for_all_values()
        payload = handles.get("total_counts").fetch_all()

        if isinstance(payload, dict) and "value" in payload:
            payload = payload["value"]
        try:
            return int(payload[-1]) if hasattr(payload, "__getitem__") else int(payload)
        except Exception as exc:
            logger.error("quasicw_counts: could not parse total_counts payload %r", payload)
            raise RuntimeError("Failed to parse total_counts from OPX result.") from exc

    def turn_outputs_on(
        self,
        t_s: float = 100e-6,
        AOMg1: float | None = None,
        AOMr1: float | None = None,
        AOMr2: float | None = None,
        EOMr2: float | None = None,
    ) -> None:
        """
        Turn on specified OPX outputs until :meth:`turn_outputs_off` is called.

        Starts one ``infinite_loop_`` per active element (parallel on the OPX).
        Each loop plays ``fire_cst`` at ``amp`` with pulse length ``t_s`` (cycles
        from :meth:`seconds_to_cycles`). Stop with :meth:`turn_outputs_off` when
        external measurements (NI-DAQ, powermeter, etc.) are finished.

        If a previous CW job is still running, it is halted before starting a new one.

        Parameters
        ----------
        t_s
            Duration of each repeated play in seconds (default 100 µs).
        AOMg1, AOMr1, AOMr2, EOMr2
            Amplitude scaling for each element; omit (``None``) to leave off.
        """
        active_elements: dict[str, float] = {}
        for name, value in {
            "AOMg1": AOMg1,
            "AOMr1": AOMr1,
            "AOMr2": AOMr2,
            "EOMr2": EOMr2,
        }.items():
            if value is None:
                continue
            active_elements[name] = float(value)

        try:
            _ = self.qm
        except Exception as exc:
            logger.error("turn_outputs_on: OPX quantum machine is not open: %s", exc)
            raise RuntimeError("OPX quantum machine is not open.") from exc

        if not active_elements:
            logger.error("turn_outputs_on: no active optical element amplitude provided.")
            raise ValueError("At least one element amplitude must be provided.")

        if self._running_job is not None:
            try:
                self._running_job.halt()
            except Exception as exc:
                logger.warning("turn_outputs_on: halt previous job failed: %s", exc)
            self._running_job = None

        cycles_per_pulse = self.seconds_to_cycles(t_s, name="t_s")

        with qua.program() as prog:
            for elem_name, amp in active_elements.items():
                with qua.infinite_loop_():
                    qua.play(
                        "fire_cst" * qua.amp(amp),
                        elem_name,
                        duration=cycles_per_pulse,
                    )

        self._running_job = self.execute(prog)

    def turn_outputs_off(self) -> None:
        """
        Halt the quasi-CW job started by :meth:`turn_outputs_on`.

        If no job is running, logs a warning and returns (safe to call from
        ``finally`` after a failed ``turn_outputs_on`` or a second cleanup).

        Raises
        ------
        RuntimeError
            If halting the running job fails.
        """
        if self._running_job is None:
            # if fail, warn
            logger.warning("turn_outputs_off: no running OPX job to halt")
            return
        try:
            self._running_job.halt()
        except Exception as exc:
            # if fail, log error and raise exception
            logger.error("turn_outputs_off: failed to halt running OPX job: %s", exc)
            raise RuntimeError("Failed to halt running OPX job.") from exc

        self._running_job = None

