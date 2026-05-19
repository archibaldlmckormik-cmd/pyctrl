# author: yannik fontana, creation date: 05.05.2026
"""
Remote wavelength meter (HighFinesse) UDP/JSON driver.
"""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _WlmReply:
    """Parsed server reply wrapper."""

    msg: str

    @classmethod
    def from_json(cls, payload: str) -> "_WlmReply":
        data = json.loads(payload)
        msg = data.get("msg", "")
        return cls(msg=str(msg))


class Wlm:
    """Remote wavelength meter driver.

    Parameters
    ----------
    server:
        WLM server hostname or IP.
    port:
        UDP port used by the remote WLM server.
    timeout_s:
        Socket timeout for receiving replies.
    validate_on_init:
        When True, sends startup commands required to bring the remote server into a usable state
        (server check, stop/start measurement, enable PID, untick constant dt on both channels).
    """

    def __init__(
        self,
        IP_address: str,
        port: int,
        *,
        timeout_s: float = 120.0,
        validate_on_init: bool = True,
    ) -> None:
        self._IP_address = IP_address
        self._port = int(port)
        self._timeout_s = float(timeout_s)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(self._timeout_s)

        # Cache last-set values for parameters that the protocol exposes as set-only.
        self._pid_cache: dict[str, dict[int, float]] = {
            "PID_P": {1: float("nan"), 2: float("nan")},
            "PID_I": {1: float("nan"), 2: float("nan")},
            "PID_D": {1: float("nan"), 2: float("nan")},
            "PID_ta": {1: float("nan"), 2: float("nan")},
            "PID_sensitivity_factor": {1: float("nan"), 2: float("nan")},
            "PID_polarity": {1: float("nan"), 2: float("nan")},
        }

        if validate_on_init:
            self._startup()
            logger.info("WLM initialized on %s:%s", self._server, self._port)

    def __enter__(self) -> "Wlm":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Close the UDP socket."""
        try:
            self._sock.close()
        except Exception:
            # Socket closing is best-effort.
            pass

    def _startup(self) -> None:
        """Send startup commands expected by the remote WLM server."""
        # Check server availability.
        rep = self._send({"command": "CheckServer", "exp": 0})
        if rep.msg.startswith("Error"):
            raise RuntimeError(f"WLM server not available: {rep.msg}")

        # Stop all measurements, start measurement, enable PID.
        rep = self._send({"command": "Operation", "exp": 0})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (stop): {rep.msg}")

        rep = self._send({"command": "Operation", "exp": 2})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (start measurement): {rep.msg}")

        rep = self._send({"command": "SetDeviationMode", "exp": 1})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (enable PID): {rep.msg}")

        # Untick "constant dt" on both PID channels.
        rep = self._send({"command": "SetPIDSetting", "exp": [1059, 1, 0, 0]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (untick constant dt CH1): {rep.msg}")

        rep = self._send({"command": "SetPIDSetting", "exp": [1059, 2, 0, 0]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"WLM startup failed (untick constant dt CH2): {rep.msg}")

    def _send(self, msg: dict[str, Any]) -> _WlmReply:
        payload = json.dumps(msg)
        self._sock.sendto(payload.encode("utf-8"), (self._server, self._port))
        data, _addr = self._sock.recvfrom(65535)
        reply_text = data.decode("utf-8", errors="ignore")
        return _WlmReply.from_json(reply_text)

    # ---- PID parameter properties (set + cached get) ----
    def _set_pid_setting(self, key: str, channel: int, value: float, exp_code: int) -> None:
        if channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        rep = self._send({"command": "SetPIDSetting", "exp": [exp_code, channel, 1, value]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set {key} on channel {channel}: {rep.msg}")
        self._pid_cache[key][channel] = float(value)

    @property
    def PID_P_ch1(self) -> float:
        return self._pid_cache["PID_P"][1]

    @PID_P_ch1.setter
    def PID_P_ch1(self, value: float) -> None:
        self._set_pid_setting("PID_P", 1, value, 1034)

    @property
    def PID_P_ch2(self) -> float:
        return self._pid_cache["PID_P"][2]

    @PID_P_ch2.setter
    def PID_P_ch2(self, value: float) -> None:
        self._set_pid_setting("PID_P", 2, value, 1034)

    @property
    def PID_I_ch1(self) -> float:
        return self._pid_cache["PID_I"][1]

    @PID_I_ch1.setter
    def PID_I_ch1(self, value: float) -> None:
        self._set_pid_setting("PID_I", 1, value, 1035)

    @property
    def PID_I_ch2(self) -> float:
        return self._pid_cache["PID_I"][2]

    @PID_I_ch2.setter
    def PID_I_ch2(self, value: float) -> None:
        self._set_pid_setting("PID_I", 2, value, 1035)

    @property
    def PID_D_ch1(self) -> float:
        return self._pid_cache["PID_D"][1]

    @PID_D_ch1.setter
    def PID_D_ch1(self, value: float) -> None:
        self._set_pid_setting("PID_D", 1, value, 1036)

    @property
    def PID_D_ch2(self) -> float:
        return self._pid_cache["PID_D"][2]

    @PID_D_ch2.setter
    def PID_D_ch2(self, value: float) -> None:
        self._set_pid_setting("PID_D", 2, value, 1036)

    @property
    def PID_ta_ch1(self) -> float:
        return self._pid_cache["PID_ta"][1]

    @PID_ta_ch1.setter
    def PID_ta_ch1(self, value: float) -> None:
        rep = self._send({"command": "SetPIDSetting", "exp": [1033, 1, 1, value]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set PID_ta on channel 1: {rep.msg}")
        # Tick "use ta in I and D"
        rep = self._send({"command": "SetPIDSetting", "exp": [1031, 1, 1, 1]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to enable ta usage on channel 1: {rep.msg}")
        self._pid_cache["PID_ta"][1] = float(value)

    @property
    def PID_ta_ch2(self) -> float:
        return self._pid_cache["PID_ta"][2]

    @PID_ta_ch2.setter
    def PID_ta_ch2(self, value: float) -> None:
        rep = self._send({"command": "SetPIDSetting", "exp": [1033, 2, 1, value]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set PID_ta on channel 2: {rep.msg}")
        rep = self._send({"command": "SetPIDSetting", "exp": [1031, 2, 1, 1]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to enable ta usage on channel 2: {rep.msg}")
        self._pid_cache["PID_ta"][2] = float(value)

    @property
    def PID_sensitivity_factor_ch1(self) -> float:
        return self._pid_cache["PID_sensitivity_factor"][1]

    @PID_sensitivity_factor_ch1.setter
    def PID_sensitivity_factor_ch1(self, value: float) -> None:
        self._set_pid_setting("PID_sensitivity_factor", 1, value, 1037)

    @property
    def PID_sensitivity_factor_ch2(self) -> float:
        return self._pid_cache["PID_sensitivity_factor"][2]

    @PID_sensitivity_factor_ch2.setter
    def PID_sensitivity_factor_ch2(self, value: float) -> None:
        self._set_pid_setting("PID_sensitivity_factor", 2, value, 1037)

    @property
    def PID_polarity_ch1(self) -> float:
        return self._pid_cache["PID_polarity"][1]

    @PID_polarity_ch1.setter
    def PID_polarity_ch1(self, value: float) -> None:
        self._set_pid_setting("PID_polarity", 1, value, 1038)

    @property
    def PID_polarity_ch2(self) -> float:
        return self._pid_cache["PID_polarity"][2]

    @PID_polarity_ch2.setter
    def PID_polarity_ch2(self, value: float) -> None:
        self._set_pid_setting("PID_polarity", 2, value, 1038)

    # ---- Wavelength / frequency properties ----
    @property
    def wavelength_ch1(self) -> float:
        rep = self._send({"command": "GetWavelengthNum", "exp": 1})
        if rep.msg == "Error: Channel number is either 1 or 2":
            raise RuntimeError(rep.msg)
        return float(rep.msg)

    @wavelength_ch1.setter
    def wavelength_ch1(self, wl: float) -> None:
        rep = self._send({"command": "SetPIDCourseNum", "exp": [1, float(wl)]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set wavelength_ch1: {rep.msg}")

    @property
    def wavelength_ch2(self) -> float:
        rep = self._send({"command": "GetWavelengthNum", "exp": 2})
        if rep.msg == "Error: Channel number is either 1 or 2":
            raise RuntimeError(rep.msg)
        return float(rep.msg)

    @wavelength_ch2.setter
    def wavelength_ch2(self, wl: float) -> None:
        rep = self._send({"command": "SetPIDCourseNum", "exp": [2, float(wl)]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set wavelength_ch2: {rep.msg}")

    @property
    def frequency_ch1(self) -> float:
        rep = self._send({"command": "GetFrequencyNum", "exp": 1})
        if rep.msg == "Error: Channel number is either 1 or 2":
            raise RuntimeError(rep.msg)
        return float(rep.msg)  # in THz

    @frequency_ch1.setter
    def frequency_ch1(self, freq: float) -> None:
        rep = self._send({"command": "SetPIDCourseNum", "exp": [1, float(freq)]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set frequency_ch1: {rep.msg}")

    @property
    def frequency_ch2(self) -> float:
        rep = self._send({"command": "GetFrequencyNum", "exp": 2})
        if rep.msg == "Error: Channel number is either 1 or 2":
            raise RuntimeError(rep.msg)
        return float(rep.msg)  # in THz

    @frequency_ch2.setter
    def frequency_ch2(self, freq: float) -> None:
        rep = self._send({"command": "SetPIDCourseNum", "exp": [2, float(freq)]})
        if rep.msg != "Ok!":
            raise RuntimeError(f"Failed to set frequency_ch2: {rep.msg}")

    # ---- Convenience wrappers ----
    def setf(self, chan: int, val: float) -> None:
        """Set frequency on channel `chan` (1 or 2)."""
        if chan == 1:
            self.frequency_ch1 = val
        elif chan == 2:
            self.frequency_ch2 = val
        else:
            raise ValueError("chan must be 1 or 2")

    def getf(self, chan: int) -> float:
        """Get frequency on channel `chan` (1 or 2), returned in THz."""
        if chan == 1:
            return self.frequency_ch1
        if chan == 2:
            return self.frequency_ch2
        raise ValueError("chan must be 1 or 2")

