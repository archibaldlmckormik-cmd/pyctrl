# author: yannik fontana, creation date: 05.05.2026
"""
Thorlabs optical power meter (PD100 / TLPMX console) via Thorlabs .NET Interop.

Uses ``pythonnet`` and ``Thorlabs.TLPMX_64.Interop.dll``, matching ``PD100class.m``.
Community reference: https://github.com/Tinyblack/Python-Driver-for-Thorlabs-power-meter
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

import clr



def _unpack_find_rsrc(result: Any) -> int:
    """Normalize ``findRsrc`` return into device count (handles pythonnet out/ref quirks)."""
    if result is None:
        raise RuntimeError("findRsrc returned None.")
    if isinstance(result, tuple):
        if len(result) == 1:
            return int(result[0])
        # MATLAB: [~, deviceCount] = device.findRsrc();
        return int(result[1])
    return int(result)


class Pd100:
    """
    Thorlabs power meter driver using TLPMX .NET Interop.

    Parameters
    ----------
    interop_dll:
        Full path to ``Thorlabs.TLPMX_64.Interop.dll`` (or your install location).
    address:
        Optional VISA-style resource string. If omitted, devices are enumerated and
        ``resource_index`` selects which one (default 0). If exactly one device exists,
        index 0 is used.
    resource_index:
        Index passed to ``getRsrcName`` when multiple meters are present (0-based).
    channel:
        Measurement channel (PD100 setup uses 1).
    """

    _DEFAULT_INTEROP_DLL = (
        r"C:\Program Files (x86)\Microsoft.NET\Primary Interop Assemblies\Thorlabs.TLPMX_64.Interop.dll"
    )

    def __init__(
        self,
        interop_dll: Optional[str] = None,
        *,
        address: Optional[str] = None,
        resource_index: int = 0,
        channel: int = 1,
    ) -> None:
        if clr is None:
            raise RuntimeError(
                "pythonnet is required for pd100. Install with `pip install pythonnet` "
                "and install Thorlabs Optical Power Monitor / TLPMX Interop DLL."
            )

        self._interop_dll = os.path.abspath(str(interop_dll or self._DEFAULT_INTEROP_DLL))
        if not os.path.isfile(self._interop_dll):
            raise FileNotFoundError(f"TLPMX Interop DLL not found: {self._interop_dll}")

        self.channel = int(channel)
        self.address: str = ""
        self._connection: Any = None
        self._tlpmx_type: Any = None

        clr.AddReference(self._interop_dll)
        from Thorlabs.TLPMX_64.Interop import TLPMX  # type: ignore

        self._tlpmx_type = TLPMX

        if address:
            self.address = str(address)
            self._connection = TLPMX(self.address, True, False)
        else:
            self.address = self._discover_address(TLPMX, resource_index=int(resource_index))
            self._connection = TLPMX(self.address, True, False)

        self._bootstrap_properties()

    def _discover_address(self, TLPMX: Any, *, resource_index: int) -> str:
        from System import IntPtr  # type: ignore
        from System.Text import StringBuilder  # type: ignore

        handle = IntPtr.Zero
        probe = TLPMX(handle)
        try:
            raw = probe.findRsrc()
            device_count = _unpack_find_rsrc(raw)
            if device_count < 1:
                raise RuntimeError("No compatible Thorlabs power meter found (findRsrc).")
            if resource_index < 0 or resource_index >= device_count:
                raise ValueError(
                    f"resource_index={resource_index} out of range; {device_count} device(s) found."
                )
            sb = StringBuilder(256)
            probe.getRsrcName(resource_index, sb)
            return str(sb.ToString())
        finally:
            try:
                probe.Dispose()
            except Exception:
                pass

    def _bootstrap_properties(self) -> None:
        """Touch readbacks like MATLAB constructor (wavelength, autorange, …)."""
        _ = self.wavelength
        _ = self.autorange
        _ = self.deltamode
        _ = self.deltavalue
        _ = self.screenmode

    def __enter__(self) -> "Pd100":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.Dispose()
            except Exception:
                logger.warning("pd100: error during Dispose.", exc_info=True)
            self._connection = None

    def readpow(self, samples: int = 1) -> Tuple[float, float]:
        """Average power and sample std (W); ``samples`` repeated ``measPower`` calls."""
        n = int(samples)
        if n < 1:
            raise ValueError("samples must be >= 1.")
        p_av = 0.0
        p_m2 = 0.0
        conn = self._connection
        ch = self.channel
        for i in range(1, n + 1):
            _err, p_temp = self._meas_power(conn, ch)
            d = p_temp - p_av
            p_av += d / i
            d2 = p_temp - p_av
            p_m2 += d * d2
        if n == 1:
            return p_av, 0.0
        return p_av, math.sqrt(p_m2 / (n - 1))

    @staticmethod
    def _meas_power(conn: Any, channel: int) -> Tuple[Any, float]:
        r = conn.measPower(channel)
        if isinstance(r, tuple):
            if len(r) >= 2:
                return r[0], float(r[1])
            return 0, float(r[0])
        return 0, float(r)

    @property
    def wavelength(self) -> float:
        r = self._connection.getWavelength(0, self.channel)
        if isinstance(r, tuple) and len(r) >= 2:
            return float(r[1])
        if isinstance(r, tuple):
            return float(r[0])
        return float(r)

    @wavelength.setter
    def wavelength(self, wl: float) -> None:
        self._connection.setWavelength(float(wl), self.channel)

    @property
    def autorange(self) -> bool:
        r = self._connection.getPowerAutorange(self.channel)
        if isinstance(r, tuple) and len(r) >= 2:
            return bool(r[1])
        if isinstance(r, tuple):
            return bool(r[0])
        return bool(r)

    @autorange.setter
    def autorange(self, value: bool) -> None:
        self._connection.setPowerAutoRange(bool(value), self.channel)

    @property
    def deltamode(self) -> bool:
        r = self._connection.getPowerRefState(self.channel)
        if isinstance(r, tuple) and len(r) >= 2:
            return bool(r[1])
        if isinstance(r, tuple):
            return bool(r[0])
        return bool(r)

    @deltamode.setter
    def deltamode(self, value: bool) -> None:
        self._connection.setPowerRefState(bool(value), self.channel)

    @property
    def deltavalue(self) -> float:
        r = self._connection.getPowerRef(0, self.channel)
        if isinstance(r, tuple) and len(r) >= 2:
            return float(r[1])
        if isinstance(r, tuple):
            return float(r[0])
        return float(r)

    @deltavalue.setter
    def deltavalue(self, delta: float) -> None:
        self._connection.setPowerRef(float(delta), self.channel)

    def zeropow(self) -> None:
        """Set relative power reference so current beam reads as zero (MATLAB ``zeropow``)."""
        if self.deltamode:
            self.deltamode = False
        p_av, _ = self.readpow(10)
        self.deltavalue = p_av
        self.deltamode = True

    @property
    def screenmode(self) -> bool:
        r = self._connection.getDispBrightness()
        if isinstance(r, tuple) and len(r) >= 2:
            return bool(float(r[1]))
        if isinstance(r, tuple):
            return bool(float(r[0]))
        return bool(float(r))

    @screenmode.setter
    def screenmode(self, value: bool) -> None:
        self._connection.setDispBrightness(float(bool(value)))
