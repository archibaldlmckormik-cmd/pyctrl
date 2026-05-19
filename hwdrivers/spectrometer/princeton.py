# author: yannik fontana, creation date: 05.05.2026
"""
Princeton Instruments spectrometer remote driver (UDP/JSON).

Connects via UDP to a server running on a remote machine and relay commands/results from the client/server to the server/client
"""

from __future__ import annotations

import json
import socket
from typing import Any, Optional

import numpy as np


class SpecRemote:
    """
    Remote spectrometer driver compatible with the PI server command set.

    Parameters
    ----------
    srvr:
        Server hostname or IP address.
    port:
        UDP port.
    timeout_s:
        Socket timeout in seconds.
    validate_on_init:
        When True, checks server availability via `CheckServer`.
    """

    _N_PIXELS = 1340
    _CHUNK_WL = 335
    _CHUNK_COUNTS = 670

    # Physical constants for axis conversion.
    _H = 6.626070040e-34
    _C = 2.99792458e8
    _EV = 1.6021766209e-19

    def __init__(
        self,
        srvr: str,
        port: int,
        *,
        timeout_s: float = 60.0
    ) -> None:
        self._server = str(srvr)
        self._port = int(port)
        self._timeout_s = float(timeout_s)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(self._timeout_s)
        self._is_ready = False

        self._xaxis_cache: Optional[dict[str, np.ndarray]] = None
        self._last_exposure: Optional[float] = None
        self._last_acttemp: Optional[float] = None
        self._last_tempstat: Optional[int] = None
        self._last_settemp: Optional[float] = None
        self._last_shuttmod: Optional[int] = None
        self._last_grating: Optional[int] = None
        self._last_position: Optional[float] = None

        # validate server reachability and populate core cached settings
        self.bootstrap()

    def __enter__(self) -> "SpecRemote":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass

    def _recv_json(self) -> dict[str, Any]:
        data, _addr = self._sock.recvfrom(65535)
        text = data.decode("utf-8", errors="ignore")
        return json.loads(text)

    def _send(self, command: str, exp: Any) -> dict[str, Any]:
        payload = {"command": command, "exp": exp}
        self._sock.sendto(json.dumps(payload).encode("utf-8"), (self._server, self._port))
        return self._recv_json()

    def bootstrap(self, *, preload_xaxis: bool = False) -> None:
        """
        Validate server reachability and populate core cached settings.

        Notes
        -----
        `preload_xaxis` is optional because it requires a chunked transfer.
        """
        self._send("CheckServer", 0)
        self._last_exposure = self.exposure
        self._last_settemp = self.settemp
        self._last_acttemp = self.acttemp
        self._last_tempstat = self.tempstat
        self._last_grating = self.grating
        self._last_position = self.position
        if preload_xaxis:
            self._xaxis_cache = self.xaxis
        self._is_ready = True

    @property
    def xaxis(self) -> dict[str, np.ndarray]:
        """
        Return wavelength axis in three representations.

        Keys:
        - `wl` in nm
        - `energy` in eV
        - `frq` in THz
        """
        wl = np.zeros(self._N_PIXELS, dtype=float)

        first = self._send("GetCalib", 0)
        wl[0 : self._CHUNK_WL] = np.asarray(first["wl"], dtype=float)
        for chunk_n in range(1, 4):
            rsp = self._recv_json()
            i0 = chunk_n * self._CHUNK_WL
            i1 = i0 + self._CHUNK_WL
            wl[i0:i1] = np.asarray(rsp["wl"], dtype=float)

        energy = self._H * self._C / wl * 1e9 / self._EV
        frq = self._C / wl * 1e9 * 1e-12
        out = {"wl": wl, "energy": energy, "frq": frq}
        self._xaxis_cache = out
        return out

    @property
    def counts(self) -> np.ndarray:
        """Acquire and return counts (length 1340)."""
        counts = np.zeros(self._N_PIXELS, dtype=float)

        first = self._send("GetCounts", 0)
        counts[0 : self._CHUNK_COUNTS] = np.asarray(first["counts"], dtype=float)

        rsp = self._recv_json()
        counts[self._CHUNK_COUNTS : self._N_PIXELS] = np.asarray(rsp["counts"], dtype=float)
        return counts

    @property
    def exposure(self) -> float:
        """Exposure / integration time (s)."""
        rsp = self._send("GetIntTime", 0)
        self._last_exposure = float(rsp["exposure"])
        return self._last_exposure

    @exposure.setter
    def exposure(self, expo: float) -> None:
        self._send("SetIntTime", float(expo))
        self._last_exposure = float(expo)

    @property
    def acttemp(self) -> float:
        """Actual detector temperature."""
        rsp = self._send("GetActTemp", 0)
        self._last_acttemp = float(rsp["acttemp"])
        return self._last_acttemp

    @property
    def tempstat(self) -> int:
        """Temperature lock status: 0 unlocked, 1 locked."""
        rsp = self._send("GetTempStat", 0)
        self._last_tempstat = int(rsp["tempstat"])
        return self._last_tempstat

    @property
    def acttempgui(self) -> str:
        """GUI-style temperature status message."""
        t = self.acttemp
        return f"temp {'locked' if self.tempstat else 'not locked'} {t}"

    @property
    def settemp(self) -> float:
        rsp = self._send("GetSetTemp", 0)
        self._last_settemp = float(rsp["settemp"])
        return self._last_settemp

    @settemp.setter
    def settemp(self, temp: float) -> None:
        self._send("SetTemp", float(temp))
        self._last_settemp = float(temp)

    @property
    def shuttmod(self) -> Optional[int]:
        """
        Cached shutter mode placeholder.

        Server API in MATLAB reference exposes only SetShuttMod, no GetShuttMod.
        """
        return self._last_shuttmod

    @shuttmod.setter
    def shuttmod(self, shutt: int) -> None:
        sh = int(shutt)
        if sh not in (1, 2, 3):
            raise ValueError("shuttmod must be Normal(1), Disabled Closed(2), or Disabled Open(3).")
        self._send("SetShuttMod", sh)
        self._last_shuttmod = sh

    def acqback(self) -> None:
        self._send("AcqBack", 0)

    @property
    def grating(self) -> int:
        rsp = self._send("GetGrating", 0)
        self._last_grating = int(rsp["grating"])
        return self._last_grating

    @grating.setter
    def grating(self, gratnum: int) -> None:
        g = int(gratnum)
        if g not in (1, 2, 3):
            raise ValueError("grating must be one of 1, 2, 3.")
        self._send("SetGrating", g)
        self._last_grating = g

    @property
    def position(self) -> float:
        rsp = self._send("GetPosition", 0)
        self._last_position = float(rsp["position"])
        return self._last_position

    @position.setter
    def position(self, pos: float) -> None:
        self._send("SetPosition", float(pos))
        self._last_position = float(pos)

    def move(self) -> None:
        self._send("Move", 0)

    def cleanup(self) -> None:
        self._send("CleanUp", 0)

    def switchbackend(self) -> None:
        self._send("SwitchBackend", 0)
