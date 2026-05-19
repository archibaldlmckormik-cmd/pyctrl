# author: yannik fontana, creation date: 05.05.2026
"""
PicoQuant PicoHarp 300 driver (PHLib) via ctypes.

- scans/open devices
- initializes mode
- applies default settings from config
- exposes core controls for histogram and TTTR buffer access
"""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class _Const:
    TTREADMAX: int = 131072
    MAXHISTBINS: int = 65536
    FLAG_OVERFLOW: int = 0x0001
    FLAG_FIFOFULL: int = 0x0002


class Pharp:
    def __init__(
        self,
        library_path: str,
        *,
        device_index: int = 0,
        mode: int = 0,
        syncdiv: int = 1,
        syncoff: int = 0,
        inpcfd0: list[int] | tuple[int, int] = (100, 5),
        inpcfd1: list[int] | tuple[int, int] = (140, 10),
        binning: int = 128,
        acqt: int = 60000,
        offset: int = 0,
    ) -> None:
        dll_path = Path(library_path)
        if not dll_path.exists():
            raise FileNotFoundError(f"PicoHarp PHLib DLL not found: {dll_path}")

        self._lib = ct.WinDLL(str(dll_path))
        self.constant = _Const()
        self.ninput = 2
        self.harp: list[int] = []
        self.ch = 0
        self._open_devices()
        if not self.harp:
            raise RuntimeError("No PicoHarp device found.")
        if device_index < 0 or device_index >= len(self.harp):
            raise ValueError(f"device_index {device_index} out of range for {len(self.harp)} device(s).")
        self.ch = int(device_index)

        self.mode = mode
        self._syncdiv = int(syncdiv)
        self._syncoff = int(syncoff)
        self._inpcfd0 = (int(inpcfd0[0]), int(inpcfd0[1]))
        self._inpcfd1 = (int(inpcfd1[0]), int(inpcfd1[1]))
        self._binning = int(binning)
        self._offset = int(offset)
        self.acqt = int(acqt)

        self.setphmode(int(mode))
        self.syncdiv = self._syncdiv
        self.syncoff = self._syncoff
        self.inpcfd0 = self._inpcfd0
        self.inpcfd1 = self._inpcfd1
        self.binning = self._binning
        self.offset = self._offset
        self.calibrate()

    def __enter__(self) -> "Pharp":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def _dev(self) -> int:
        return int(self.harp[self.ch])

    def _check(self, ret: int, func_name: str) -> None:
        if ret < 0:
            msg = self._error_string(ret)
            raise RuntimeError(f"{func_name} failed ({ret}): {msg}")

    def _error_string(self, code: int) -> str:
        buf = ct.create_string_buffer(40)
        self._lib.PH_GetErrorString(buf, ct.c_int(code))
        return buf.value.decode(errors="replace")

    def _open_devices(self) -> None:
        self.harp.clear()
        for i in range(8):
            serial = ct.create_string_buffer(8)
            ret = self._lib.PH_OpenDevice(ct.c_int(i), serial)
            if ret == 0:
                self.harp.append(i)

    def setphmode(self, val: int) -> None:
        ret = self._lib.PH_Initialize(ct.c_int(self._dev), ct.c_int(int(val)))
        self._check(ret, "PH_Initialize")
        if val == 0:
            self.mode = "HIST_MODE"
        elif val == 2:
            self.mode = "T2_MODE"
        elif val == 3:
            self.mode = "T3_MODE"
        else:
            self.mode = f"MODE_{val}"

    def calibrate(self) -> None:
        ret = self._lib.PH_Calibrate(ct.c_int(self._dev))
        self._check(ret, "PH_Calibrate")

    @property
    def syncdiv(self) -> int:
        return self._syncdiv

    @syncdiv.setter
    def syncdiv(self, val: int) -> None:
        v = int(val)
        ret = self._lib.PH_SetSyncDiv(ct.c_int(self._dev), ct.c_int(v))
        self._check(ret, "PH_SetSyncDiv")
        self._syncdiv = v

    @property
    def syncoff(self) -> int:
        return self._syncoff

    @syncoff.setter
    def syncoff(self, val: int) -> None:
        v = int(val)
        ret = self._lib.PH_SetSyncOffset(ct.c_int(self._dev), ct.c_int(v))
        self._check(ret, "PH_SetSyncOffset")
        self._syncoff = v

    @property
    def inpcfd0(self) -> tuple[int, int]:
        return self._inpcfd0

    @inpcfd0.setter
    def inpcfd0(self, val: list[int] | tuple[int, int]) -> None:
        discr, zc = int(val[0]), int(val[1])
        ret = self._lib.PH_SetInputCFD(ct.c_int(self._dev), ct.c_int(0), ct.c_int(discr), ct.c_int(zc))
        self._check(ret, "PH_SetInputCFD(ch0)")
        self._inpcfd0 = (discr, zc)

    @property
    def inpcfd1(self) -> tuple[int, int]:
        return self._inpcfd1

    @inpcfd1.setter
    def inpcfd1(self, val: list[int] | tuple[int, int]) -> None:
        discr, zc = int(val[0]), int(val[1])
        ret = self._lib.PH_SetInputCFD(ct.c_int(self._dev), ct.c_int(1), ct.c_int(discr), ct.c_int(zc))
        self._check(ret, "PH_SetInputCFD(ch1)")
        self._inpcfd1 = (discr, zc)

    @property
    def binning(self) -> int:
        return self._binning

    @binning.setter
    def binning(self, val: int) -> None:
        # MATLAB behavior: mode = round(log2(val/4)); effective binning = 2**mode * 4
        v = int(val)
        if v < 4:
            raise ValueError("binning must be >= 4 ps.")
        modeval = int(round(np.log2(v / 4.0)))
        ret = self._lib.PH_SetBinning(ct.c_int(self._dev), ct.c_int(modeval))
        self._check(ret, "PH_SetBinning")
        self._binning = int((2**modeval) * 4)

    @property
    def offset(self) -> int:
        return self._offset

    @offset.setter
    def offset(self, val: int) -> None:
        v = int(val)
        ret = self._lib.PH_SetOffset(ct.c_int(self._dev), ct.c_int(v))
        self._check(ret, "PH_SetOffset")
        self._offset = v

    @property
    def resol(self) -> float:
        out = ct.c_double(0.0)
        ret = self._lib.PH_GetResolution(ct.c_int(self._dev), ct.byref(out))
        self._check(ret, "PH_GetResolution")
        return float(out.value)

    @property
    def ctsrate(self) -> tuple[float, float]:
        vals: list[float] = []
        for i in range(self.ninput):
            out = ct.c_int32(0)
            ret = self._lib.PH_GetCountRate(ct.c_int(self._dev), ct.c_int(i), ct.byref(out))
            self._check(ret, f"PH_GetCountRate(ch{i})")
            vals.append(float(out.value))
        return (vals[0], vals[1])

    def run(self) -> None:
        ret = self._lib.PH_StartMeas(ct.c_int(self._dev), ct.c_int(int(self.acqt)))
        self._check(ret, "PH_StartMeas")

    def stop(self) -> None:
        ret = self._lib.PH_StopMeas(ct.c_int(self._dev))
        self._check(ret, "PH_StopMeas")

    def running(self) -> int:
        out = ct.c_int32(0)
        ret = self._lib.PH_CTCStatus(ct.c_int(self._dev), ct.byref(out))
        self._check(ret, "PH_CTCStatus")
        return int(out.value)

    def gtflag(self) -> tuple[int, int]:
        out = ct.c_int32(0)
        ret = self._lib.PH_GetFlags(ct.c_int(self._dev), ct.byref(out))
        self._check(ret, "PH_GetFlags")
        return int(ret), int(out.value)

    def fetchbuffer(self) -> tuple[int, np.ndarray, int]:
        buffsize = 512 * 20
        arr = np.zeros(buffsize, dtype=np.uint32)
        n_tags = ct.c_int32(0)
        ret = self._lib.PH_ReadFiFo(
            ct.c_int(self._dev),
            arr.ctypes.data_as(ct.POINTER(ct.c_uint32)),
            ct.c_int(buffsize),
            ct.byref(n_tags),
        )
        if ret < 0:
            return int(ret), np.empty(0, dtype=np.uint32), 0
        n = int(n_tags.value)
        return int(ret), arr[:n].copy(), n

    def get_histogram(self, block: int = 0) -> np.ndarray:
        buf = np.zeros(self.constant.MAXHISTBINS, dtype=np.uint32)
        ret = self._lib.PH_GetHistogram(
            ct.c_int(self._dev),
            buf.ctypes.data_as(ct.POINTER(ct.c_uint32)),
            ct.c_int(int(block)),
        )
        self._check(ret, "PH_GetHistogram")
        return buf

    def clear_hist_mem(self, blocknumber: int = 0) -> None:
        ret = self._lib.PH_ClearHistMem(ct.c_int(self._dev), ct.c_int(int(blocknumber)))
        self._check(ret, "PH_ClearHistMem")

    def close(self) -> None:
        for i in range(8):
            self._lib.PH_CloseDevice(ct.c_int(i))

