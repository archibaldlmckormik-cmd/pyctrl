# author: yannik fontana, creation date: 05.05.2026
"""
Attocube ANC300 rack: one serial connection, multiple hardware channels (1–6).

Mirrors ``init_anc300.m`` (shared COM) and ``ANC300.m`` (per-channel commands). Uses **pyserial**
with ``\\r\\n`` line endings as in MATLAB ``fprintf(..., [req, char(13), char(10)])``.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Optional

logger = logging.getLogger(__name__)

import serial

_CHANNEL_INDEX_MIN = 1
_CHANNEL_INDEX_MAX = 6
_MAX_CHANNELS = 6
_EMPTY_SLOT_MARKER = "-"


def _channel_index_str(index: int) -> str:
    if index < _CHANNEL_INDEX_MIN or index > _CHANNEL_INDEX_MAX:
        raise ValueError(
            f"Channel index must be in [{_CHANNEL_INDEX_MIN}, {_CHANNEL_INDEX_MAX}], got {index}."
        )
    return str(int(index))


def _parse_float_first(s: str) -> float:
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if not m:
        raise ValueError(f"Could not parse a number from device reply: {s!r}")
    return float(m.group(0))


class Anc300:
    """
    ANC300 controller: opens the serial port to communicate with the ANC300 cabinet and attaches :class:`Channel` instances according to the channels dictionary.

    Parameters
    ----------
    port:
        Serial port name (e.g. ``"COM11"``).
    channels:
        Channel layout specification. Supported forms:

        - Mapping form: **logical name → physical channel index** (1–6)
        - Slot-list form: sequence of exactly 6 strings; position i maps to channel i+1.
          Use ``"-"`` for an empty slot.

        Dynamic attributes are created for active channel names, e.g. ``ctrl.LP``.
    baudrate, bytesize, parity, stopbits:
        Passed to :class:`serial.Serial`.
    timeout_s:
        Read timeout (seconds).

    Notes
    -----
    * Up to six modules / channels; channel indices are **1-based** like the hardware.
    * Only :meth:`close` on this object closes the serial connection.
    """

    def __init__(
        self,
        port: str,
        *,
        channels: Any,
        baudrate: int = 115200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        timeout_s: float = 2.0,
    ) -> None:
        ch_map = self._normalize_channels(channels)

        self.port = str(port)
        self._lock = threading.Lock()
        self._ser: Optional[serial.Serial] = None

        self._ser = serial.Serial(
            port=self.port,
            baudrate=int(baudrate),
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=float(timeout_s),
        )
        try:
            self._ser.reset_input_buffer()
        except Exception:
            logger.debug("reset_input_buffer failed", exc_info=True)

        for name, ch_index in ch_map.items():
            setattr(self, name, Channel(self, ch_index))

        self._channel_names = tuple(ch_map.keys())
        logger.info("Anc300 opened %s with channels: %s", self.port, self._channel_names)

    @staticmethod
    def _validate_name(name: str) -> str:
        text = str(name).strip()
        if not text or not text.isidentifier():
            raise ValueError(f"Channel name {name!r} must be a valid Python identifier.")
        return text

    @classmethod
    def _normalize_channels(cls, channels: Any) -> dict[str, int]:
        if isinstance(channels, Mapping):
            if not channels:
                raise ValueError(
                    "channels mapping must be non-empty (name -> channel index in 1..6)."
                )
            if len(channels) > _MAX_CHANNELS:
                raise ValueError(f"At most {_MAX_CHANNELS} channels supported; got {len(channels)}.")
            out: dict[str, int] = {}
            for raw_name, raw_idx in channels.items():
                name = cls._validate_name(str(raw_name))
                if name in out:
                    raise ValueError(f"Duplicate channel name {name!r}.")
                ch_index = int(raw_idx)
                if ch_index < _CHANNEL_INDEX_MIN or ch_index > _CHANNEL_INDEX_MAX:
                    raise ValueError(
                        f"Channel {name!r}: channel index {ch_index} out of range "
                        f"[{_CHANNEL_INDEX_MIN}, {_CHANNEL_INDEX_MAX}]."
                    )
                out[name] = ch_index
            return out

        if isinstance(channels, Sequence) and not isinstance(channels, (str, bytes, bytearray)):
            if len(channels) != _MAX_CHANNELS:
                raise ValueError(
                    f"channels slot list must have exactly {_MAX_CHANNELS} entries, got {len(channels)}."
                )
            out: dict[str, int] = {}
            for i, raw_name in enumerate(channels, start=1):
                name = str(raw_name).strip()
                if name == _EMPTY_SLOT_MARKER:
                    continue
                name = cls._validate_name(name)
                if name in out:
                    raise ValueError(f"Duplicate channel name {name!r} in slot list.")
                out[name] = i
            if not out:
                raise ValueError("channels slot list contains only empty slots ('-').")
            return out

        raise TypeError(
            "channels must be either a mapping {name: index} or a 6-item slot list like "
            "['LP', 'QWP', 'HWP', '-', '-', '-']."
        )

    def __enter__(self) -> "Anc300":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Close the serial port (channels must not be used afterwards)."""
        for name in self._channel_names:
            try:
                delattr(self, name)
            except AttributeError:
                pass
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                logger.warning("Anc300: error closing serial port.", exc_info=True)
            self._ser = None

    def _serial_write(self, req: str) -> None:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("Serial port is not open.")
        line = str(req).encode("ascii", errors="strict") + b"\r\n"
        with self._lock:
            self._ser.write(line)
            self._ser.flush()

    def _serial_readline(self) -> str:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("Serial port is not open.")
        with self._lock:
            raw = self._ser.readline()
        text = raw.decode("ascii", errors="replace").strip()
        return text


class Channel:
    """
    One ANC300 hardware channel (same role as MATLAB ``ANC300``).

    Does **not** own the serial port; use :meth:`Anc300.close` on the controller.
    """

    def __init__(self, ctrl: "Anc300", channel_index: int) -> None:
        self._ctrl = ctrl
        self.m_channel = _channel_index_str(channel_index)
        self._frq_cache = float("nan")
        self._offset_cache = float("nan")

    @property
    def channel(self) -> str:
        """Physical channel index as string (``'1'`` … ``'6'``) used in device commands."""
        return self.m_channel

    def _write(self, req: str) -> None:
        self._ctrl._serial_write(req)

    def _read_line(self) -> str:
        return self._ctrl._serial_readline()

    def stepper_on(self) -> None:
        self._write(f"setm {self.m_channel} stp")
        self.filter_off()

    def stepper_off(self) -> None:
        self._write(f"setm {self.m_channel} gnd")

    def AC_on(self) -> None:
        self._write(f"setaci {self.m_channel} on")

    def AC_off(self) -> None:
        self._write(f"setaci {self.m_channel} off")

    def DC_on(self) -> None:
        self._write(f"setdci {self.m_channel} on")

    def DC_off(self) -> None:
        self._write(f"setdci {self.m_channel} off")

    def step(self, val: float) -> None:
        n = int(round(float(val)))
        if n > 0:
            self._write(f"stepu {self.m_channel} {n}")
        else:
            self._write(f"stepd {self.m_channel} {-n}")

    def waitstepfinished(self) -> None:
        self._write(f"stepw {self.m_channel}")

    @property
    def volt(self) -> float:
        self._write(f"getv {self.m_channel}")
        return _parse_float_first(self._read_line())

    @volt.setter
    def volt(self, val: float) -> None:
        v = int(round(float(val)))
        if v > 60 or v < 10:
            raise ValueError("volt must be an integer between 10 and 60.")
        self._write(f"setv {self.m_channel} {v}")

    @property
    def frq(self) -> float:
        """Last set frequency (Hz); MATLAB wrapper only documents a setter."""
        return self._frq_cache

    @frq.setter
    def frq(self, val: float) -> None:
        v = int(round(float(val)))
        if v > 1000 or v < 10:
            raise ValueError("frq must be an integer between 10 and 1000.")
        self._write(f"setf {self.m_channel} {v}")
        self._frq_cache = float(v)

    def filter_on(self) -> None:
        self.stepper_off()
        self._write(f"setfil {self.m_channel} 16")

    def filter_off(self) -> None:
        self._write(f"setfil {self.m_channel} off")

    @property
    def offset(self) -> float:
        """Last set offset (V); MATLAB only exposes ``seta`` for write."""
        return self._offset_cache

    @offset.setter
    def offset(self, val: float) -> None:
        v = int(round(float(val)))
        if v > 150 or v < 0:
            raise ValueError("offset must be an integer between 0 and 150.")
        self._write(f"seta {self.m_channel} {v}")
        self._offset_cache = float(v)

    def offset_on(self) -> None:
        self._write(f"setm {self.m_channel} off")

    def stop(self) -> None:
        self._write(f"stop {self.m_channel}")
