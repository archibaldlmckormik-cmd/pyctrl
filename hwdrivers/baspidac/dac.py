# author: yannik fontana, creation date: 05.05.2026
"""
Serial driver for a multi-channel DAC (Steinacher DAC).

Public API:
- ``voltage[key]`` where key is ``1..8`` or ``"1".."8"``
- ``status[key]`` where key is ``1..8`` or ``"1".."8"``
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import serial

logger = logging.getLogger(__name__)


class _ChannelMap:
    """Dictionary-like view over DAC channels for voltage/status."""

    def __init__(self, dac: "Dac", *, kind: str) -> None:
        self._dac = dac
        self._kind = kind

    def __getitem__(self, key: int | str) -> float | str:
        channel = self._dac._normalize_channel_key(key)
        if self._kind == "voltage":
            return self._dac.getvoltage(channel)
        return self._dac.getstatus(channel)

    def __setitem__(self, key: int | str, value: float | str) -> None:
        channel = self._dac._normalize_channel_key(key)
        if self._kind == "voltage":
            self._dac.setvoltage(channel, float(value))
            return
        self._dac.setstatus(channel, str(value))

    def smooth_ramp(
        self,
        key: int | str,
        target_voltage: float
    ) -> None:
        """
        Smoothly ramps the voltage of a channel to a target voltage.
        usage:
        dac.voltage.smooth_ramp(key, target_voltage)
        Args:
            key: The channel key to ramp.
            target_voltage: The target voltage to ramp to.
            step_v: The step size in voltage.
            tolerance_v: The tolerance in voltage.
        """
        if self._kind != "voltage":
            logger.error("smooth_ramp is only available for DAC voltage channels")
            raise AttributeError("smooth_ramp is only available on dac.voltage")

        channel = self._dac._normalize_channel_key(key)
        target = float(target_voltage)
        step = self._dac._THRESHOLD_SMOOTHMOVE
        pacing = self._dac._RAMP_PACING_S
        tol = self._dac._RAMP_VERIFY_TOLERANCE_V

        if step <= 0:
            logger.error("smooth_ramp step_v must be > 0, got %s", step)
            raise ValueError("smooth_ramp step_v must be > 0")
        if pacing < 0:
            logger.error("smooth_ramp pacing_s must be >= 0, got %s", pacing)
            raise ValueError("smooth_ramp pacing_s must be >= 0")
        if tol <= 0:
            logger.error("smooth_ramp tolerance_v must be > 0, got %s", tol)
            raise ValueError("smooth_ramp tolerance_v must be > 0")

        current = float(self._dac.getvoltage(channel))
        delta = target - current
        if abs(delta) > step:
            direction = 1.0 if delta > 0 else -1.0
            v = current
            while abs(target - v) > step:
                v = v + direction * step
                self._dac.setvoltage(channel, v)
                if pacing > 0:
                    time.sleep(pacing)

        self._dac.setvoltage(channel, target)
        # last readback to check if the target is reached
        readback = float(self._dac.getvoltage(channel))
        if abs(readback - target) > tol:
            logger.warning(
                "DAC smooth_ramp verify mismatch on channel %d: target=%.6f V, readback=%.6f V, tol=%.6f V",
                channel,
                target,
                readback,
                tol,
            )

    def keys(self) -> list[str]:
        return [str(i) for i in range(1, self._dac._N_CHANNELS + 1)]


class Dac:
    """Serial driver for the Steinacher/BASPI 8 channels DAC."""

    _BAUDRATE: int = 115200
    _N_CHANNELS: int = 8
    _RETRIES: int = 5
    _VOLT_SCALE: float = 838848.0
    _VOLT_OFFSET: float = -10.0
    _THRESHOLD_SMOOTHMOVE: float = 1e-3
    _RAMP_PACING_S: float = 0.01
    _RAMP_VERIFY_TOLERANCE_V: float = 1e-5

    def __init__(self, port: str, *, validate_on_init: bool = True, timeout_s: float = 1.0) -> None:
        self.serialconnect: Optional[serial.Serial] = None
        self.voltage = _ChannelMap(self, kind="voltage")
        self.status = _ChannelMap(self, kind="status")

        try:
            self.serialconnect = serial.Serial(
                port=port,
                baudrate=self._BAUDRATE,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                parity=serial.PARITY_NONE,
                xonxoff=True,
                timeout=timeout_s,
                write_timeout=timeout_s,
            )
            self.serialconnect.reset_input_buffer()
            self.serialconnect.reset_output_buffer()
        except serial.SerialException as exc:
            logger.error("DAC initialization error on %s: %s", port, exc)
            self.close()
            raise RuntimeError("DAC initialization error: failed to open serial port") from exc

        logger.info("DAC initialized on %s", port)

        if validate_on_init:
            for channel_index in range(1, self._N_CHANNELS + 1):
                _ = self.getvoltage(channel_index)
                _ = self.getstatus(channel_index)

    def __enter__(self) -> "Dac":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @classmethod
    def _normalize_channel_key(cls, key: int | str) -> int:
        if isinstance(key, int):
            cls._validate_channel(key)
            return key
        text = str(key).strip()
        if not text.isdigit():
            logger.error("Invalid DAC channel key %r: expected 1..%d", key, cls._N_CHANNELS)
            raise ValueError(f"DAC channel key must be 1..{cls._N_CHANNELS}, got {key!r}")
        channel = int(text)
        cls._validate_channel(channel)
        return channel

    def close(self) -> None:
        if self.serialconnect is None:
            return
        try:
            if getattr(self.serialconnect, "is_open", False):
                self.serialconnect.close()
        except serial.SerialException as exc:
            logger.error("DAC close failed: %s", exc)
            raise
        finally:
            self.serialconnect = None

    def _flush_io(self) -> None:
        if self.serialconnect is None:
            return
        try:
            self.serialconnect.reset_input_buffer()
        except Exception:
            logger.debug("DAC reset_input_buffer failed", exc_info=True)
        try:
            self.serialconnect.reset_output_buffer()
        except Exception:
            logger.debug("DAC reset_output_buffer failed", exc_info=True)

    def _read_line_stripped(self) -> Optional[str]:
        if self.serialconnect is None:
            return None
        raw = self.serialconnect.readline()
        if not raw:
            return None
        try:
            s = raw.decode("ascii", errors="ignore")
        except Exception:
            logger.debug("DAC decode reply failed", exc_info=True)
            return None
        s = s.strip()
        return s if s else None

    def _write_line(self, line: str) -> None:
        if self.serialconnect is None:
            logger.error("DAC serial port is not open")
            raise RuntimeError("DAC serial port is not open")
        cmd = f"{line}\r\n"
        self.serialconnect.write(cmd.encode("ascii"))
        self.serialconnect.flush()

    @classmethod
    def _validate_channel(cls, channel: int) -> None:
        if not isinstance(channel, int):
            logger.error("DAC channel must be an integer, got %r", channel)
            raise ValueError("DAC channel must be an integer")
        if channel < 1 or channel > cls._N_CHANNELS:
            logger.error("DAC channel %d out of range [1,%d]", channel, cls._N_CHANNELS)
            raise ValueError(f"DAC channel must be in [1,{cls._N_CHANNELS}]")

    def channel_toggleONOFF(self, channel: int) -> None:
        self._validate_channel(channel)
        key = str(channel)
        current = self.status[key]
        self.status[key] = "OFF" if str(current).upper() == "ON" else "ON"

    def getvoltage(self, channel: int) -> float:
        self._validate_channel(channel)
        attempt = 0
        while attempt < self._RETRIES:
            self._flush_io()
            self._write_line(f"{channel} V?")
            value = self._read_line_stripped()
            if value is None:
                attempt += 1
                continue
            try:
                hex_str = value[2:] if value.lower().startswith("0x") else value
                code = int(hex_str, 16)
            except ValueError as exc:
                logger.error("Invalid DAC voltage hex response on channel %d: %r", channel, value)
                raise ValueError(f"Invalid DAC voltage hex response: {value!r}") from exc
            return code / self._VOLT_SCALE + self._VOLT_OFFSET

        logger.error("Error getting DAC voltage on channel %d: %d attempts failed", channel, self._RETRIES)
        raise RuntimeError("Error getting DAC voltage: five attempts have failed")

    def _flush_input_best_effort(self) -> None:
        if self.serialconnect is None:
            return
        try:
            self.serialconnect.reset_input_buffer()
        except Exception:
            logger.debug("DAC reset_input_buffer after command failed", exc_info=True)

    def setvoltage(self, channel: int, voltage: float) -> None:
        self._validate_channel(channel)
        v = float(voltage)
        if not 0.0 <= v <= 10.0:
            logger.error("DAC voltage %.6f out of range [0,10] on channel %d", v, channel)
            raise ValueError("DAC voltage must be in [0,10] V")

        self._flush_io()
        code = int((v + 10.0) * self._VOLT_SCALE)
        code_hex = f"{(code & 0xFFFFFFFF):06x}".upper()
        self._write_line(f"{channel} {code_hex}")

        value = self._read_line_stripped()
        self._flush_input_best_effort()

        if value is None:
            logger.warning("DAC setvoltage timeout/no response on channel %d", channel)
            return

        if value == "0":
            return

        warnings_map = {
            "1": "invalid DAC-channel",
            "2": "Missing DAC value or Status",
            "3": "DAC value out of range",
            "4": "Mistyped",
            "5": "Remote writing not allowed during local editing",
        }
        if value in warnings_map:
            logger.warning("Error setting DAC voltage on channel %d: %s", channel, warnings_map[value])
            return

        logger.error("Unexpected DAC voltage response on channel %d: %r", channel, value)
        raise ValueError(f"Unexpected DAC voltage response: {value!r}")

    def getstatus(self, channel: int) -> str:
        self._validate_channel(channel)
        attempt = 0
        while attempt < self._RETRIES:
            self._flush_io()
            self._write_line(f"{channel} S?")
            value = self._read_line_stripped()
            if value is None:
                attempt += 1
                continue
            return value

        logger.error("Error getting DAC status on channel %d: %d attempts failed", channel, self._RETRIES)
        raise RuntimeError("Error getting DAC Status: five attempts have failed")

    def setstatus(self, channel: int, status: str) -> None:
        self._validate_channel(channel)
        norm = str(status).strip().upper()
        if norm not in {"ON", "OFF"}:
            logger.error("Invalid DAC status %r on channel %d", status, channel)
            raise ValueError('DAC status must be "ON" or "OFF"')

        self._flush_io()
        self._write_line(f"{channel} {norm}")

        value = self._read_line_stripped()
        self._flush_input_best_effort()

        if value is None:
            logger.warning("DAC setstatus timeout/no response on channel %d", channel)
            return

        if value == "0":
            return

        warnings_map = {
            "1": "invalid DAC-channel",
            "2": "Missing DAC value or Status",
            "3": "DAC value out of range",
            "4": "Mistyped",
            "5": "Remote writing not allowed during local editing",
        }
        if value in warnings_map:
            logger.warning("Error setting DAC status on channel %d: %s", channel, warnings_map[value])
            return

        logger.error("Unexpected DAC status response on channel %d: %r", channel, value)
        raise ValueError(f"Unexpected DAC status response: {value!r}")
