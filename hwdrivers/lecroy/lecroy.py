# author: yannik fontana, creation date: 05.05.2026
"""
Teledyne LeCroy oscilloscope driver via PyVISA.

This module intentionally focuses on transport and waveform acquisition only.
Plotting, saving, and post-processing should live outside the driver.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Optional, Sequence

import numpy as np
import pyvisa

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Waveform:
    """Simple waveform payload."""

    x: np.ndarray
    y: np.ndarray
    x_unit: str = "s"
    y_unit: str = "V"
    channel: str = ""


class Scope:
    """
    Teledyne LeCroy VISA scope driver.

    Parameters
    ----------
    resource_name:
        VISA resource string, for example:
        ``USB0::0x05FF::0x1023::phys-optic-31::INSTR`` or
        ``TCPIP0::192.168.0.10::inst0::INSTR``.
    visa_backend:
        Optional backend for pyvisa ``ResourceManager`` (e.g. ``"@ni"`` or ``"@py"``).
    timeout_s:
        VISA timeout in seconds.
    Connection is established during initialization and ``*IDN?`` is queried.
    """

    def __init__(
        self,
        resource_name: str,
        *,
        visa_backend: Optional[str] = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._resource_name = str(resource_name)
        self._visa_backend = visa_backend
        self._timeout_s = float(timeout_s)

        self._rm = None
        self._inst = None
        self._idn = ""
        self._time_div: float = float("nan")
        self._voltage_div: dict[int, float] = {i: float("nan") for i in range(1, 5)}
        self._trigger_mode: str = "normal"
        self._trigger_source: Optional[int] = None
        self._trigger_level: float = float("nan")
        self.connect()

    def __enter__(self) -> "Scope":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def idn(self) -> str:
        """Cached response from ``*IDN?`` after connect."""
        return self._idn

    @property
    def is_connected(self) -> bool:
        return self._inst is not None

    def connect(self) -> None:
        """Open VISA session and perform a basic identity query."""
        if self._inst is not None:
            return

        self._rm = pyvisa.ResourceManager(self._visa_backend) if self._visa_backend else pyvisa.ResourceManager()
        inst = self._rm.open_resource(self._resource_name)
        inst.timeout = int(self._timeout_s * 1000.0)

        # Keep ASCII transfers deterministic for text queries.
        inst.write_termination = "\n"
        inst.read_termination = "\n"

        self._inst = inst
        try:
            self._idn = self.query("*IDN?").strip()
            logger.info("Connected LeCroy scope: %s", self._idn)
        except Exception:
            # Keep the connection open even when *IDN? is unavailable.
            logger.warning("Connected, but *IDN? query failed.", exc_info=True)
        self._refresh_settings_cache()

    def close(self) -> None:
        """Close the VISA instrument and resource manager."""
        if self._inst is not None:
            try:
                self._inst.close()
            except Exception:
                pass
            self._inst = None

        if self._rm is not None:
            try:
                self._rm.close()
            except Exception:
                pass
            self._rm = None

    def write(self, command: str) -> None:
        """Send a SCPI/VBS command to the scope."""
        if self._inst is None:
            self.connect()
        assert self._inst is not None
        self._inst.write(str(command))

    def query(self, command: str) -> str:
        """Send query and return text response."""
        if self._inst is None:
            self.connect()
        assert self._inst is not None
        return str(self._inst.query(str(command)))

    def _write_vbs(self, expression: str) -> None:
        """Send a LeCroy VBS command expression."""
        self.write(f"VBS '{expression}'")

    def _query_vbs(self, expression: str) -> str:
        """Query a LeCroy VBS expression and return the text response."""
        return self.query(f"VBS? 'return= {expression}'").strip()

    def _refresh_settings_cache(self) -> None:
        """Best-effort readback of scope settings into local cached properties."""
        try:
            self._time_div = float(self._query_vbs("app.Acquisition.Horizontal.HorScale"))
        except Exception:
            logger.debug("Could not read HorScale.", exc_info=True)

        for c in range(1, 5):
            try:
                raw = self._query_vbs(f"app.Acquisition.C{c}.VerScale")
                self._voltage_div[c] = float(raw)
            except Exception:
                logger.debug("Could not read VerScale for C%s.", c, exc_info=True)

        try:
            raw_mode = self._query_vbs("app.Acquisition.TriggerMode").strip().strip('"').lower()
            if raw_mode:
                self._trigger_mode = raw_mode
        except Exception:
            logger.debug("Could not read TriggerMode.", exc_info=True)

        try:
            raw_source = self._query_vbs("app.Acquisition.Trigger.Source").strip().strip('"').upper()
            if raw_source.startswith("C"):
                self._trigger_source = int(raw_source[1:])
        except Exception:
            logger.debug("Could not read Trigger.Source.", exc_info=True)

        if self._trigger_source is not None:
            try:
                raw_level = self._query_vbs(f"app.Acquisition.Trigger.C{self._trigger_source}.Level")
                self._trigger_level = float(raw_level)
            except Exception:
                logger.debug("Could not read trigger level for source channel.", exc_info=True)

    @property
    def time_div(self) -> float:
        """Horizontal scale in seconds/div."""
        return self._time_div

    @time_div.setter
    def time_div(self, seconds_per_div: float) -> None:
        value = float(seconds_per_div)
        if value <= 0:
            raise ValueError("time_div must be > 0.")
        self._write_vbs(f"app.Acquisition.Horizontal.HorScale = {value}")
        self._time_div = value

    @property
    def voltage_div(self) -> dict[int, float]:
        """Per-channel vertical scale in V/div, keyed by channel index (1..4)."""
        return dict(self._voltage_div)

    @voltage_div.setter
    def voltage_div(self, values: dict[int, float]) -> None:
        for c, vdiv in dict(values).items():
            ch = int(c)
            if ch < 1 or ch > 4:
                raise ValueError(f"channel index {ch} is out of range; expected 1..4.")
            val = float(vdiv)
            if val <= 0:
                raise ValueError("voltage_div values must be > 0.")
            self._write_vbs(f"app.Acquisition.C{ch}.VerScale = {val}")
            self._voltage_div[ch] = val

    @property
    def trigger_mode(self) -> str:
        """Trigger mode, one of: auto, normal, single."""
        return self._trigger_mode

    @trigger_mode.setter
    def trigger_mode(self, mode: str) -> None:
        key = str(mode).strip().lower()
        mapping = {
            "auto": "Auto",
            "normal": "Normal",
            "single": "Single",
        }
        if key not in mapping:
            raise ValueError("trigger_mode must be one of: auto, normal, single")
        self._write_vbs(f'app.Acquisition.TriggerMode = "{mapping[key]}"')
        self._trigger_mode = key

    @property
    def trigger_source(self) -> Optional[int]:
        """Trigger source channel index (1..4) when known."""
        return self._trigger_source

    @trigger_source.setter
    def trigger_source(self, channel: int) -> None:
        ch = int(channel)
        if ch < 1 or ch > 4:
            raise ValueError("trigger_source must be in 1..4.")
        self._write_vbs(f'app.Acquisition.Trigger.Source = "C{ch}"')
        self._trigger_source = ch
        try:
            raw_level = self._query_vbs(f"app.Acquisition.Trigger.C{ch}.Level")
            self._trigger_level = float(raw_level)
        except Exception:
            logger.debug("Could not refresh trigger level after changing trigger source.", exc_info=True)

    @property
    def trigger_level(self) -> float:
        """Trigger level in volts for the current trigger source channel."""
        return self._trigger_level

    @trigger_level.setter
    def trigger_level(self, level_v: float) -> None:
        if self._trigger_source is None:
            raise RuntimeError("trigger_source is unknown; set trigger_source before trigger_level.")
        value = float(level_v)
        self._write_vbs(f"app.Acquisition.Trigger.C{self._trigger_source}.Level = {value}")
        self._trigger_level = value

    @property
    def trigger(self) -> dict[str, Any]:
        """Combined trigger settings: mode, source_channel, level_v."""
        return {
            "mode": self._trigger_mode,
            "source_channel": self._trigger_source,
            "level_v": self._trigger_level,
        }

    @trigger.setter
    def trigger(self, settings: dict[str, Any]) -> None:
        cfg = dict(settings)
        if "mode" in cfg:
            self.trigger_mode = str(cfg["mode"])
        if "source_channel" in cfg:
            self.trigger_source = int(cfg["source_channel"])
        if "level_v" in cfg:
            self.trigger_level = float(cfg["level_v"])

    def read_waveform_ascii(self, channel: int | str) -> Waveform:
        """
        Read one channel waveform using LeCroy ASCII INSPECT queries.

        Notes
        -----
        This path favors simplicity and readability over transfer speed.
        For high throughput, add a binary ``WF?`` parser later.
        """
        ch = self._normalize_channel(channel)

        x_text = self.query(f"{ch}:INSPECT? HORIZ_VALUES")
        y_text = self.query(f"{ch}:INSPECT? SIMPLE")

        x = self._parse_ascii_list(x_text)
        y = self._parse_ascii_list(y_text)
        n = min(x.size, y.size)
        if n == 0:
            raise RuntimeError(f"{ch}: empty waveform response.")
        if x.size != y.size:
            logger.warning("%s: x/y length mismatch (%s vs %s); trimming to %s", ch, x.size, y.size, n)

        return Waveform(x=x[:n], y=y[:n], x_unit="s", y_unit="V", channel=ch)

    # --- Scope setup helpers ---
    def set_time_div(self, seconds_per_div: float) -> None:
        """Set horizontal time scale in seconds/div."""
        self.time_div = seconds_per_div

    def get_time_div(self) -> float:
        """Get horizontal time scale in seconds/div."""
        return self.time_div

    def set_voltage_div(self, channel: int, volts_per_div: float) -> None:
        """Set vertical scale (V/div) for one channel."""
        self.voltage_div = {int(channel): float(volts_per_div)}

    def get_voltage_div(self, channel: int) -> float:
        """Get vertical scale (V/div) for one channel."""
        ch = int(channel)
        if ch < 1 or ch > 4:
            raise ValueError("channel index must be in 1..4.")
        return float(self._voltage_div[ch])

    def set_trigger_mode(self, mode: str) -> None:
        """
        Set trigger mode.

        Accepted values: ``"auto"``, ``"normal"``, ``"single"``.
        """
        self.trigger_mode = mode

    def set_trigger_source(self, channel: int) -> None:
        """Set trigger source to a scope channel (1..4)."""
        self.trigger_source = int(channel)

    def set_trigger_level(self, channel: int, level_v: float) -> None:
        """
        Set trigger level in volts for a given channel.

        This writes channel-specific level (e.g. Trigger.C1.Level).
        """
        ch = int(channel)
        if ch != self._trigger_source:
            self.trigger_source = ch
        self.trigger_level = float(level_v)

    def configure_trigger(self, *, mode: str, source_channel: int, level_v: float) -> None:
        """Convenience method to configure mode, source, and level together."""
        self.set_trigger_mode(mode)
        self.set_trigger_source(source_channel)
        self.set_trigger_level(source_channel, level_v)

    def read_channels(self, channels: Sequence[int]) -> dict[str, dict[str, Any]]:
        """
        Read one trace from each requested channel and return MATLAB-like payload.

        Parameters
        ----------
        channels:
            Iterable of channel indices in the range 1..4, e.g. ``[1, 3, 4]``.

        Returns
        -------
        dict
            Mapping like ``{"CH1": {"X": ..., "Y": ..., "XUNIT": ..., "YUNIT": ...}, ...}``.
            ``X`` and ``Y`` are 1D ``numpy.ndarray`` values.
        """
        ch_list = [int(c) for c in channels]
        if not ch_list:
            raise ValueError("channels must be non-empty.")

        out: dict[str, dict[str, Any]] = {}
        for c in ch_list:
            if c < 1 or c > 4:
                raise ValueError(f"channel index {c} is out of range; expected 1..4.")
            wf = self.read_waveform_ascii(c)
            key = f"CH{c}"
            out[key] = {
                "X": wf.x,
                "Y": wf.y,
                "XUNIT": wf.x_unit,
                "YUNIT": wf.y_unit,
            }
        return out

    @staticmethod
    def _normalize_channel(channel: int | str) -> str:
        if isinstance(channel, int):
            if channel < 1:
                raise ValueError("channel index must be >= 1")
            return f"C{channel}"
        text = str(channel).strip().upper()
        if text.startswith("CHANNEL"):
            text = "C" + text.replace("CHANNEL", "", 1)
        if text.startswith("CH"):
            text = "C" + text[2:]
        if not text.startswith("C"):
            raise ValueError("channel must look like 1, 'C1', 'CH1', or 'channel1'")
        return text

    @staticmethod
    def _parse_ascii_list(payload: str) -> np.ndarray:
        # LeCroy INSPECT replies often include labels like:
        # "SIMPLE: 0.1,0.2,0.3"
        text = str(payload).strip()
        if ":" in text:
            text = text.split(":", 1)[1]
        text = text.replace("\r", " ").replace("\n", " ")
        text = text.replace(",", " ")
        parts = [p for p in text.split() if p]
        if not parts:
            return np.empty(0, dtype=float)
        return np.asarray([float(v) for v in parts], dtype=float)
