# author: yannik fontana, creation date: 05.05.2026
"""
NI-DAQmx driver for analog, digital, and counter input (and analog/digital output setup).

Lazy task construction: NI-DAQmx `Task` objects are created when you first acquire or
configure channels, not in `__init__`.
"""

from __future__ import annotations

import logging
import threading
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping
from nidaqmx.constants import Edge

logger = logging.getLogger(__name__)

# Allowed AI voltage span halves (±V), same set as MATLAB NIDAQclass.
_RANGES_V: Tuple[float, ...] = (0.2, 1.0, 5.0, 10.0)


@dataclass
class _BgSource:
    """Minimal stand-in for MATLAB callback `source` with a `.data` attribute."""

    data: np.ndarray


class Nidaq:
    """
    NI-DAQmx session-style wrapper for mixed analog, counter, and digital **input** acquisition.

    Channel names are short NI names without the device prefix (e.g. ``\"ai0\"``, ``\"ctr0\"``);
    the driver builds ``f\"{device}/{name}\"``.

    Foreground reads return a 2D ``numpy`` array ``(nsamples, n_channels)``. Column order follows
    the order each **input** channel was added (``add_ai``, ``add_ctr``, ``add_di``). AO/DO are
    not included in ``readFG``.

    Parameters
    ----------
    device:
        NI device name (default ``\"Dev1\"``).
    """

    def __init__(self, device: str = "Dev1") -> None:
        self.device: str = str(device)
        self.samplesN: int = 1
        self._rate: float = 1000.0

        # Channel name -> kind: 'ai' | 'ao' | 'di' | 'do' | 'ctr'
        self._channel_kind: Dict[str, str] = {}
        # Input channels only, in insertion order (defines read column order)
        self._read_order: List[str] = []

        # Per-AI (min, max) volts; applied when tasks are built
        self._ai_volts_range: Dict[str, Tuple[float, float]] = {}

        self._running_tasks: List[Any] = []
        self._bg_thread: Optional[threading.Thread] = None
        self._bg_result: Optional[np.ndarray] = None
        self._bg_lock = threading.Lock()

    def __enter__(self) -> "Nidaq":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Stop acquisition, close tasks, and clear channel bookkeeping."""
        self._stop_running_tasks_best_effort()
        with self._bg_lock:
            if self._bg_thread is not None and self._bg_thread.is_alive():
                self._stop_running_tasks_best_effort()
                self._bg_thread.join(timeout=2.0)
            self._bg_thread = None
            self._bg_result = None

        self._channel_kind.clear()
        self._read_order.clear()
        self._ai_volts_range.clear()

    # --- Public API: MATLAB-compatible channel dict (lightweight) ---
    @property
    def channels(self) -> Dict[str, str]:
        """Map channel name -> kind string (``'ai'``, ``'ao'``, ``'di'``, ``'do'``, ``'ctr'``)."""
        return dict(self._channel_kind)

    def _phys(self, short_name: str) -> str:
        return f"{self.device}/{short_name}"

    def _append_read_order(self, name: str) -> None:
        if name not in self._read_order:
            self._read_order.append(name)

    def _validate_names(self, names: Sequence[str]) -> List[str]:
        out = [str(n) for n in names]
        if not out:
            raise ValueError("Channel list must be non-empty.")
        return out

    def add_ai(self, list_ai: Sequence[str]) -> None:
        """Add analog input voltage channels."""
        for name in self._validate_names(list_ai):
            if name in self._channel_kind:
                raise ValueError(f"Channel {name!r} already registered.")
            self._channel_kind[name] = "ai"
            self._ai_volts_range[name] = (-10.0, 10.0)
            self._append_read_order(name)

    def add_ao(self, list_ao: Sequence[str]) -> None:
        """Add analog output voltage channels (outputs are not read by ``readFG``)."""
        for name in self._validate_names(list_ao):
            if name in self._channel_kind:
                raise ValueError(f"Channel {name!r} already registered.")
            self._channel_kind[name] = "ao"

    def add_ctr(self, list_ctr: Sequence[str]) -> None:
        """Add counter input edge-count channels (rising edge)."""
        for name in self._validate_names(list_ctr):
            if name in self._channel_kind:
                raise ValueError(f"Channel {name!r} already registered.")
            self._channel_kind[name] = "ctr"
            self._append_read_order(name)

    def add_di(self, list_di: Sequence[str]) -> None:
        """Add digital input channels (one line or port per name, as NI expects)."""
        for name in self._validate_names(list_di):
            if name in self._channel_kind:
                raise ValueError(f"Channel {name!r} already registered.")
            self._channel_kind[name] = "di"
            self._append_read_order(name)

    def add_do(self, list_do: Sequence[str]) -> None:
        """Add digital output channels (not read by ``readFG``)."""
        for name in self._validate_names(list_do):
            if name in self._channel_kind:
                raise ValueError(f"Channel {name!r} already registered.")
            self._channel_kind[name] = "do"

    def remove_channel(self, list_channel: Sequence[str]) -> None:
        """Remove channels by name (stops any running tasks first)."""
        self._stop_running_tasks_best_effort()
        for name in self._validate_names(list_channel):
            if name not in self._channel_kind:
                continue
            del self._channel_kind[name]
            if name in self._read_order:
                self._read_order.remove(name)
            self._ai_volts_range.pop(name, None)

    @property
    def rate(self) -> float:
        """Sample clock rate (Hz) for finite input acquisitions."""
        return float(self._rate)

    @rate.setter
    def rate(self, value: float) -> None:
        self._rate = float(value)

    def autorange_ai(self) -> None:
        """Pick ±V range per AI from ``(0.2, 1, 5, 10)`` using a short probe acquisition."""
        if not self._read_order:
            raise RuntimeError("No input channels configured.")
        ai_names = [n for n in self._read_order if self._channel_kind.get(n) == "ai"]
        if not ai_names:
            raise RuntimeError("No analog input channels to autorange.")

        for n in ai_names:
            self._ai_volts_range[n] = (-10.0, 10.0)

        time_s = 3.0 * (1.0 / 50.0)
        nsamples = max(1, int(round(time_s * self._rate)))
        probe = self.readFG(nsamples)

        col_index = {name: i for i, name in enumerate(self._read_order)}
        for n in ai_names:
            j = col_index[n]
            peak = float(np.max(np.abs(probe[:, j])))
            chosen = 10.0
            for r in _RANGES_V:
                if r > 2.0 * peak:
                    chosen = r
                    break
            self._ai_volts_range[n] = (-chosen, chosen)

    def setrange_ai(self, ai_list: Sequence[str], ranges: Sequence[float]) -> None:
        """Set AI range using the smallest allowed ±span >= each requested magnitude."""
        names = [str(x) for x in ai_list]
        rng = [float(x) for x in ranges]
        if len(names) > 1 and len(rng) == 1:
            rng = [rng[0]] * len(names)
        if len(rng) != len(names):
            raise ValueError("ranges must match ai_list length, or be a single value.")

        chan_set = set(self._channel_kind.keys())
        for n, mag in zip(names, rng):
            if n not in chan_set or self._channel_kind.get(n) != "ai":
                continue
            cands = [r for r in _RANGES_V if r >= abs(mag)]
            span = min(cands) if cands else _RANGES_V[-1]
            self._ai_volts_range[n] = (-span, span)

    def readFG(self, nsamples: Optional[int] = None) -> np.ndarray:
        """
        Blocking finite acquisition; returns ``(nsamples, n_input_channels)`` float array.
        """
        if nsamples is None:
            nsamples = int(self.samplesN)
        nsamples = int(nsamples)
        if nsamples < 1:
            raise ValueError("nsamples must be a positive integer.")
        if not self._read_order:
            raise RuntimeError("No input channels configured (add_ai / add_di / add_ctr).")

        return self._acquire_finite(nsamples)

    def startBG(
        self,
        nsamples: Optional[Union[int, str]] = None,
        callback_handle: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Start a background (non-blocking) finite acquisition on a worker thread.

        When complete, ``callback_handle(event, source)`` is called with ``source.data`` set to
        the acquired matrix.

        .. note::
            ``nsamples=\"continuous\"`` (MATLAB-style) is **not implemented** yet.

            # TODO: Continuous acquisition + periodic callback via nidaqmx register_every_n_samples_* .
        """
        if nsamples is None:
            nsamples = int(self.samplesN)

        if isinstance(nsamples, str) and nsamples.strip().lower() == "continuous":
            raise NotImplementedError(
                'Continuous acquisition (nsamples="continuous") is TODO for nidaqmx; '
                "use finite integer nsamples for now."
            )

        ns = int(nsamples)
        if ns < 1:
            raise ValueError("nsamples must be a positive integer.")

        if callback_handle is None:

            def _default_cb(_event: Any, source: Any) -> Any:
                return getattr(source, "data", None)

            callback_handle = _default_cb

        with self._bg_lock:
            if self._bg_thread is not None and self._bg_thread.is_alive():
                raise RuntimeError("Background acquisition already running.")

            def _worker() -> None:
                try:
                    data = self.readFG(ns)
                    with self._bg_lock:
                        self._bg_result = data
                    callback_handle(None, _BgSource(data=data))
                except Exception as e:  # pragma: no cover
                    logger.warning(f"nidaq background acquisition failed: {e!r}")

            self._bg_result = None
            t = threading.Thread(target=_worker, daemon=True)
            self._bg_thread = t
            t.start()

    def stopBG(self, wait_string: str = "") -> np.ndarray:
        """
        Stop background acquisition.

        If ``wait_string`` is ``\"wait\"`` (case-insensitive), wait for the worker to finish and
        return the last acquired matrix (or empty array if none).

        Otherwise, stop running NI tasks best-effort and return an empty array (MATLAB parity).
        """
        ws = str(wait_string).strip().lower()
        if ws == "wait":
            th: Optional[threading.Thread] = None
            with self._bg_lock:
                th = self._bg_thread
            if th is not None:
                th.join()
            with self._bg_lock:
                out = self._bg_result
                self._bg_thread = None
                self._bg_result = None
            if out is None:
                return np.empty((0, 0))
            return out

        self._stop_running_tasks_best_effort()
        with self._bg_lock:
            self._bg_thread = None
            self._bg_result = None
        return np.empty((0, 0))

    # --- Internals ---

    def _stop_running_tasks_best_effort(self) -> None:
        for t in list(self._running_tasks):
            try:
                t.stop()
            except Exception:
                pass
            try:
                t.close()
            except Exception:
                pass
        self._running_tasks.clear()

    def _normalize_read_array(self, data: Any, nsamples: int, n_chan: int) -> np.ndarray:
        if isinstance(data, list):
            if not data:
                return np.empty((nsamples, 0))
            cols = [np.asarray(x, dtype=float).reshape(-1) for x in data]
            arr = np.column_stack(cols)
        else:
            arr = np.asarray(data, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1) if n_chan >= 1 else arr.reshape(nsamples, -1)
        if arr.shape[0] != nsamples:
            # Some devices return (n_chan, nsamples); fix if obvious
            if arr.shape[1] == nsamples and arr.shape[0] == n_chan:
                arr = arr.T
        return arr

    def _build_input_tasks(self, nsamples: int) -> Tuple[List[Any], Dict[str, Tuple[int, int]]]:
        """
        Build up to three tasks (AI, CI, DI) and a map: channel_name -> (task_idx, col_idx).
        """
        assert nidaqmx is not None
        tasks: List[Any] = []
        name_to_pos: Dict[str, Tuple[int, int]] = {}

        ai_names = [n for n in self._read_order if self._channel_kind.get(n) == "ai"]
        ctr_names = [n for n in self._read_order if self._channel_kind.get(n) == "ctr"]
        di_names = [n for n in self._read_order if self._channel_kind.get(n) == "di"]

        if ai_names:
            t_ai = nidaqmx.Task()
            tasks.append(t_ai)
            task_idx = len(tasks) - 1
            for j, n in enumerate(ai_names):
                lo, hi = self._ai_volts_range.get(n, (-10.0, 10.0))
                t_ai.ai_channels.add_ai_voltage_chan(self._phys(n), min_val=lo, max_val=hi)
                name_to_pos[n] = (task_idx, j)
            t_ai.timing.cfg_samp_clk_timing(
                rate=self._rate,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=nsamples,
            )

        if ctr_names:
            t_ci = nidaqmx.Task()
            tasks.append(t_ci)
            task_idx = len(tasks) - 1
            for j, n in enumerate(ctr_names):
                t_ci.ci_channels.add_ci_count_edges_chan(self._phys(n), edge=Edge.RISING)
                name_to_pos[n] = (task_idx, j)
            try:
                t_ci.timing.cfg_samp_clk_timing(
                    rate=self._rate,
                    sample_mode=AcquisitionType.FINITE,
                    samps_per_chan=nsamples,
                )
            except Exception:
                t_ci.timing.cfg_implicit_timing(
                    sample_mode=AcquisitionType.FINITE,
                    samps_per_chan=nsamples,
                )

        if di_names:
            t_di = nidaqmx.Task()
            tasks.append(t_di)
            task_idx = len(tasks) - 1
            for j, n in enumerate(di_names):
                t_di.di_channels.add_di_chan(
                    self._phys(n),
                    line_grouping=LineGrouping.CHAN_PER_LINE,
                )
                name_to_pos[n] = (task_idx, j)
            t_di.timing.cfg_samp_clk_timing(
                rate=self._rate,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=nsamples,
            )

        return tasks, name_to_pos

    def _acquire_finite(self, nsamples: int) -> np.ndarray:
        self._stop_running_tasks_best_effort()
        tasks, name_to_pos = self._build_input_tasks(nsamples)
        self._running_tasks = tasks

        buffers: Dict[int, np.ndarray] = {}
        try:
            for ti, t in enumerate(tasks):
                t.start()
            timeout_s = float(nsamples) / float(self._rate) + 10.0
            for t in tasks:
                t.wait_until_done(timeout=timeout_s)

            for ti, t in enumerate(tasks):
                raw = t.read(number_of_samples_per_channel=nsamples)
                n_ch = int(getattr(t, "number_of_channels", len(getattr(t, "channel_names", []))))
                buffers[ti] = self._normalize_read_array(raw, nsamples, n_ch)

            out = np.zeros((nsamples, len(self._read_order)), dtype=float)
            for j, name in enumerate(self._read_order):
                ti, col = name_to_pos[name]
                out[:, j] = buffers[ti][:, col]
            return out
        finally:
            self._stop_running_tasks_best_effort()

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass
