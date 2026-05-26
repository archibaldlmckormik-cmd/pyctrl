# author: yannik fontana, creation date: 05.05.2026
"""
Remote wavelength meter (HighFinesse) UDP/JSON driver.
"""

from __future__ import annotations

import json
import logging
import math
import socket
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_PID_CODES: dict[str, int] = {
    "P": 1034,
    "I": 1035,
    "D": 1036,
    "ta": 1033,
    "sensitivity_factor": 1037,
    "polarity": 1038,
}

_PID_TOML_KEYS: dict[str, str] = {
    "PID_P": "P",
    "PID_I": "I",
    "PID_D": "D",
    "PID_ta": "ta",
    "PID_sensitivity_factor": "sensitivity_factor",
    "PID_polarity": "polarity",
}

_PID_COMPARE_ATOL = 1e-6


@dataclass(frozen=True)
class _WlmReply:
    """Parsed server reply wrapper."""

    msg: str

    @classmethod
    def from_json(cls, payload: str) -> "_WlmReply":
        data = json.loads(payload)
        return cls(msg=str(data.get("msg", "")))


def _parse_channel_table(table: dict[str, Any]) -> tuple[str, dict[str, float]]:
    """Build ``laser_id`` and ``pid`` dict from a ``[wlm.chN]`` config table."""
    if "laser_id" not in table:
        raise KeyError("channel config must define laser_id")
    pid: dict[str, float] = {}
    for toml_key, pid_key in _PID_TOML_KEYS.items():
        if toml_key in table:
            pid[pid_key] = float(table[toml_key])
    return str(table["laser_id"]), pid


class WlmChannel:
    """
    One WLM PID channel (1 or 2).

    Parameters
    ----------
    wlm:
        Parent driver used for UDP commands.
    index:
        Hardware channel index (1 or 2).
    laser_id:
        Labelling string from config (not sent to the server).
    pid:
        Desired PID parameters from config (keys ``P``, ``I``, ``D``, ``ta``,
        ``sensitivity_factor``, ``polarity``).
    """

    def __init__(
        self,
        wlm: "Wlm",
        index: int,
        *,
        laser_id: str,
        pid: dict[str, float],
    ) -> None:
        if index not in (1, 2):
            raise ValueError("channel index must be 1 or 2")
        self._wlm = wlm
        self.index = int(index)
        self.laser_id = str(laser_id)
        self.pid: dict[str, float] = dict(pid)

    def apply_pid(self) -> None:
        """Push all entries in :attr:`pid` to the remote server."""
        for key, value in self.pid.items():
            self._set_pid_param(key, float(value))

    def _set_pid_param(self, key: str, value: float) -> None:
        if key not in _PID_CODES:
            raise KeyError(f"unknown PID key {key!r}")
        code = _PID_CODES[key]
        if key == "ta":
            self._wlm._set_pid_setting(code, self.index, value)
            rep = self._wlm._send({"command": "SetPIDSetting", "exp": [1031, self.index, 1, 1]})
            if rep.msg != "Ok!":
                raise RuntimeError(
                    f"failed to enable ta usage on channel {self.index}: {rep.msg}"
                )
            return
        self._wlm._set_pid_setting(code, self.index, value)

    def _get_pid_param(self, key: str) -> float:
        if key not in _PID_CODES:
            raise KeyError(f"unknown PID key {key!r}")
        return self._wlm._get_pid_setting(_PID_CODES[key], self.index)

    @property
    def frequency(self) -> float:
        """Optical frequency in THz (``GetFrequencyNum``)."""
        rep = self._wlm._send({"command": "GetFrequencyNum", "exp": self.index})
        if rep.msg == "Error: Channel number is either 1 or 2":
            raise RuntimeError(rep.msg)
        return float(rep.msg)

    @frequency.setter
    def frequency(self, freq: float) -> None:
        rep = self._wlm._send(
            {"command": "SetPIDCourseNum", "exp": [self.index, float(freq)]}
        )
        if rep.msg != "Ok!":
            raise RuntimeError(
                f"failed to set frequency on channel {self.index}: {rep.msg}"
            )


class Wlm:
    """
    Remote wavelength meter driver (UDP/JSON).

    Exposes :attr:`ch1`, :attr:`ch2` (:class:`WlmChannel`) and
    :attr:`lock_frequencies` (global PID lock).
    """

    def __init__(
        self,
        IP_address: str,
        port: int,
        *,
        ch1: dict[str, Any] | None = None,
        ch2: dict[str, Any] | None = None,
        timeout_s: float = 5.0,
        validate_on_init: bool = True,
    ) -> None:
        self._IP_address = str(IP_address)
        self._port = int(port)
        self._timeout_s = float(timeout_s)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(self._timeout_s)

        ch1_laser, ch1_pid = _parse_channel_table(ch1 or {})
        ch2_laser, ch2_pid = _parse_channel_table(ch2 or {})
        self.ch1 = WlmChannel(self, 1, laser_id=ch1_laser, pid=ch1_pid)
        self.ch2 = WlmChannel(self, 2, laser_id=ch2_laser, pid=ch2_pid)

        self._lock_frequencies = False

        if validate_on_init:
            self._startup()
            self._lock_frequencies = self._read_lock_frequencies()
            self._compare_pid_to_hardware()

        logger.info("WLM initialized on %s:%s", self._IP_address, self._port)

    def __enter__(self) -> "Wlm":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Close the UDP socket."""
        try:
            self._sock.close()
        except Exception:
            logger.warning("Failed to close WLM socket", exc_info=True)

    @property
    def lock_frequencies(self) -> bool:
        """Whether frequency PID locking is enabled on the server."""
        return self._lock_frequencies

    @lock_frequencies.setter
    def lock_frequencies(self, enabled: bool) -> None:
        exp = 1 if enabled else 0
        rep = self._send({"command": "SetDeviationMode", "exp": exp})
        if rep.msg != "Ok!":
            raise RuntimeError(f"failed to set lock_frequencies={enabled}: {rep.msg}")
        self._lock_frequencies = bool(enabled)

    def apply_all_pid(self) -> None:
        """Push config PID values for both channels to the hardware."""
        self.ch1.apply_pid()
        self.ch2.apply_pid()

    def _startup(self) -> None:
        """Bring the remote server to a usable state (does not enable PID lock)."""
        rep = self._send({"command": "CheckServer", "exp": 0})
        if rep.msg.startswith("Error"):
            raise RuntimeError(f"WLM server not available: {rep.msg}")

        rep = self._send({"command": "Operation", "exp": 0})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (stop): {rep.msg}")

        rep = self._send({"command": "Operation", "exp": 2})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (start measurement): {rep.msg}")

        for channel in (1, 2):
            rep = self._send({"command": "SetPIDSetting", "exp": [1059, channel, 0, 0]})
            if rep.msg != "Ok!":
                raise RuntimeError(
                    f"WLM startup failed (untick constant dt CH{channel}): {rep.msg}"
                )

    def _read_lock_frequencies(self) -> bool:
        rep = self._send({"command": "GetDeviationMode", "exp": 0})
        if rep.msg == "1":
            return True
        if rep.msg == "0":
            return False
        logger.warning(
            "WLM GetDeviationMode returned unexpected msg %r; treating as False",
            rep.msg,
        )
        return False

    def _compare_pid_to_hardware(self) -> None:
        for channel in (self.ch1, self.ch2):
            for key, expected in channel.pid.items():
                try:
                    actual = channel._get_pid_param(key)
                except Exception as exc:
                    logger.warning(
                        "WLM CH%d: could not read PID %s from hardware (%s); "
                        "call apply_all_pid() to push config",
                        channel.index,
                        key,
                        exc,
                    )
                    continue
                if not math.isclose(
                    actual, expected, rel_tol=0.0, abs_tol=_PID_COMPARE_ATOL
                ):
                    logger.warning(
                        "WLM CH%d PID %s differs from config: hardware=%s config=%s "
                        "(call apply_all_pid() to push config)",
                        channel.index,
                        key,
                        actual,
                        expected,
                    )

    def _send(self, msg: dict[str, Any]) -> _WlmReply:
        payload = json.dumps(msg)
        self._sock.sendto(payload.encode("utf-8"), (self._IP_address, self._port))
        data, _addr = self._sock.recvfrom(65535)
        return _WlmReply.from_json(data.decode("utf-8", errors="ignore"))

    def _set_pid_setting(self, code: int, channel: int, value: float) -> None:
        rep = self._send(
            {"command": "SetPIDSetting", "exp": [code, channel, 1, float(value)]}
        )
        if rep.msg != "Ok!":
            raise RuntimeError(
                f"failed to set PID code {code} on channel {channel}: {rep.msg}"
            )

    def _get_pid_setting(self, code: int, channel: int) -> float:
        rep = self._send({"command": "GetPIDSetting", "exp": [code, channel]})
        if rep.msg.startswith("Error"):
            raise RuntimeError(
                f"failed to get PID code {code} on channel {channel}: {rep.msg}"
            )
        return float(rep.msg)
