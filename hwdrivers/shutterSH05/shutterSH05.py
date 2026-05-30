# author: yannik fontana, creation date: 05.05.2026
"""
Thorlabs K-Cube Solenoid (SH05) shutter driver via Kinesis .NET API.

This driver uses `pythonnet` (the `clr` module) to load Thorlabs Kinesis assemblies and
control a Solenoid shutter.

If `pythonnet` is not available, constructing `ShutterSH05` will raise a clear error.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import logging

logger = logging.getLogger(__name__)

import clr  # type: ignore



class ShutterSH05:
    """
    Driver for a Thorlabs SH05 solenoid shutter using the Kinesis .NET API.

    Parameters
    ----------
    serialnumber:
        Device serial number to connect to (e.g. "10123456").
        If omitted, the driver attempts to auto-connect when exactly one compatible device
        is present.
    kinesis_path:
        Base folder containing Thorlabs Kinesis DLLs.
    timeout_settings_ms:
        Timeout for device settings initialization (ms).
    """

    # Defaults from the MATLAB wrapper
    _KINESISPATHDEFAULT = r"C:\Program Files\Thorlabs\Kinesis"
    _DEVICEMANAGERDLL = "Thorlabs.MotionControl.DeviceManagerCLI.dll"
    _GENERICMOTORDLL = "Thorlabs.MotionControl.GenericMotorCLI.dll"
    _SOLENOIDDLL = "Thorlabs.MotionControl.KCube.SolenoidCLI.dll"

    _TPOLLING_MS = 250
    _TIMEOUTSETTINGS_MS = 5000

    def __init__(
        self,
        serialnumber: Optional[str] = None,
        *,
        kinesis_path: Optional[str] = None,
        timeout_settings_ms: Optional[int] = None,
        validate_on_init: bool = True,
    ) -> None:
        if clr is None:
            raise RuntimeError(
                "pythonnet is required to use ShutterSH05. Install with `pip install pythonnet` "
                "and ensure Thorlabs Kinesis DLLs are available."
            )

        self._kinesis_path = kinesis_path or self._KINESISPATHDEFAULT
        self._timeout_settings_ms = int(timeout_settings_ms or self._TIMEOUTSETTINGS_MS)

        self.serialnumber: Optional[str] = None
        self.controllername: Optional[str] = None
        self.controllerdescription: Optional[str] = None
        self.stagename: Optional[str] = None

        self._deviceNET = None
        self._initialized = False

        if validate_on_init:
            if serialnumber is None:
                serials = self.listdevices(kinesis_path=self._kinesis_path)
                if len(serials) == 0:
                    raise RuntimeError("No compatible Thorlabs K-Cube Solenoid devices found.")
                if len(serials) > 1:
                    raise RuntimeError(
                        "Multiple compatible devices found; pass `serialnumber` to connect."
                    )
                serialnumber = serials[0]
            self.connect(serialnumber, kinesis_path=self._kinesis_path)

    def __enter__(self) -> "ShutterSH05":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    @classmethod
    def loaddlls(cls, *, kinesis_path: Optional[str] = None) -> None:
        """
        Load Kinesis .NET assemblies required for shutter control.
        """
        if clr is None:  # pragma: no cover
            raise RuntimeError("pythonnet (clr) is not available.")

        kinesis_path = kinesis_path or cls._KINESISPATHDEFAULT
        # Load assemblies once per process; pythonnet doesn't expose a perfect "loaded?" check,
        # so we just attempt to add them and let exceptions surface if DLLs are missing.
        def _add(dll_name: str) -> None:
            dll_path = os.path.join(kinesis_path, dll_name)
            clr.AddReference(dll_path)

        _add(cls._DEVICEMANAGERDLL)
        _add(cls._GENERICMOTORDLL)
        _add(cls._SOLENOIDDLL)

    @classmethod
    def listdevices(cls, *, kinesis_path: Optional[str] = None) -> list[str]:
        """
        List compatible Thorlabs Solenoid shutter serial numbers.
        """
        cls.loaddlls(kinesis_path=kinesis_path)

        from Thorlabs.MotionControl.DeviceManagerCLI import (  # type: ignore
            DeviceManagerCLI,
        )
        from Thorlabs.MotionControl.KCube.SolenoidCLI import (  # type: ignore
            KCubeSolenoid,
        )

        DeviceManagerCLI.BuildDeviceList()
        serial_numbers_net = DeviceManagerCLI.GetDeviceList(KCubeSolenoid.DevicePrefix)
        return [str(s) for s in serial_numbers_net]

    # ---- Connection lifecycle ----
    def connect(self, serialnumber: str, *, kinesis_path: Optional[str] = None) -> None:
        """
        Connect to the shutter device and start polling.
        """
        if self._initialized:
            raise RuntimeError("Device is already connected.")

        kinesis_path = kinesis_path or self._kinesis_path
        type(self).loaddlls(kinesis_path=kinesis_path)

        from Thorlabs.MotionControl.KCube.SolenoidCLI import (  # type: ignore
            KCubeSolenoid,
            SolenoidStatus,
            ThorlabsKCubeSolenoidSettings,
        )

        prefix = int(str(serialnumber)[:2])
        if prefix != int(KCubeSolenoid.DevicePrefix):
            raise RuntimeError("Thorlabs Shutter and K-Cube not recognised for this serial number.")

        self._deviceNET = KCubeSolenoid.CreateKCubeSolenoid(serialnumber)
        self._deviceNET.Connect(serialnumber)

        if not self._deviceNET.IsSettingsInitialized():
            self._deviceNET.WaitForSettingsInitialized(self._timeout_settings_ms)
        if not self._deviceNET.IsSettingsInitialized():
            raise RuntimeError(f"Unable to initialize device {serialnumber}")

        self._deviceNET.StartPolling(int(self._TPOLLING_MS))
        self._deviceNET.EnableDevice()

        self.serialnumber = str(self._deviceNET.DeviceID)
        shutter_settings = self._deviceNET.GetSolenoidConfiguration(serialnumber)
        self.stagename = str(shutter_settings.DeviceSettingsName)

        current_settings = ThorlabsKCubeSolenoidSettings.GetSettings(shutter_settings)
        self.controllername = str(self._deviceNET.GetDeviceInfo().Name)
        self.controllerdescription = str(self._deviceNET.GetDeviceInfo().Description)

        # Store operating states enum values for open/close.
        # Expected members are `Active`/`Inactive` and `OperatingStates`.
        try:
            op_states = SolenoidStatus.OperatingStates
            self._OPSTATE_ACTIVE = op_states.Active
            self._OPSTATE_INACTIVE = op_states.Inactive
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Unable to resolve Solenoid operating state enums.") from e

        self._initialized = True
        logger.info("Shutter connected: %s", self.serialnumber)

    def disconnect(self) -> None:
        """
        Disconnect the device and stop polling.
        """
        if not self.isconnected:
            raise RuntimeError("Device not connected.")

        try:
            self._deviceNET.StopPolling()
            self._deviceNET.DisableDevice()
            self._deviceNET.Disconnect()
        finally:
            self._deviceNET = None
            self._initialized = False

    def reset(self, serialnumber: str) -> None:
        """
        Reset the connection to the device.
        """
        if not self.isconnected:
            raise RuntimeError("Device not connected.")
        self._deviceNET.ResetConnection(serialnumber)

    # ---- Properties (mirroring MATLAB Dependent properties) ----
    @property
    def isconnected(self) -> bool:
        """True when the device reports itself as connected."""
        return bool(self._deviceNET.IsConnected()) if self._deviceNET is not None else False

    @property
    def frontpanellock(self) -> bool:
        """Get whether the device front panel is locked (if supported)."""
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        self._deviceNET.RequestFrontPanelLocked()
        return bool(self._deviceNET.GetFrontPanelLocked())

    @frontpanellock.setter
    def frontpanellock(self, lockstate: bool) -> None:
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        if not self._deviceNET.CanDeviceLockFrontPanel():
            raise RuntimeError("Device does not support front panel locking.")
        self._deviceNET.SetFrontPanelLock(bool(lockstate))

    @property
    def operatingmode(self) -> str:
        """Current shutter operating mode as a string."""
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        return str(self._deviceNET.GetOperatingMode())

    @operatingmode.setter
    def operatingmode(self, newmode: str) -> None:
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")

        if isinstance(newmode, str):
            newmode_norm = newmode.strip().lower()
        else:
            raise ValueError("operatingmode must be a string.")

        from Thorlabs.MotionControl.KCube.SolenoidCLI import SolenoidStatus  # type: ignore

        op_modes = SolenoidStatus.OperatingModes
        mapping = {
            "manual": getattr(op_modes, "Manual", None),
            "singletoggle": getattr(op_modes, "SingleToggle", None),
            "autotoggle": getattr(op_modes, "AutoToggle", None),
            "triggered": getattr(op_modes, "Triggered", None),
        }
        mode_enum = mapping.get(newmode_norm)
        if mode_enum is None:
            raise ValueError(f"Operating mode not recognized: {newmode!r}")
        self._deviceNET.SetOperatingMode(mode_enum)

    @property
    def open(self) -> bool:
        """True if the shutter operating state is 'Active' (open command state)."""
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        res = str(self._deviceNET.GetOperatingState()).lower()
        return "active" in res

    @open.setter
    def open(self, newstate: bool) -> None:
        """
        Open or close the shutter and block until the physical solenoid state matches.
        """
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        if not isinstance(newstate, bool):
            raise ValueError("Shutter state should be boolean.")

        if newstate:
            self._deviceNET.SetOperatingState(self._OPSTATE_ACTIVE)
            # Wait until solenoid state becomes Open
            time.sleep(0.05)
            while str(self.state).lower() == "closed":
                time.sleep(0.01)
        else:
            self._deviceNET.SetOperatingState(self._OPSTATE_INACTIVE)
            time.sleep(0.05)
            while str(self.state).lower() == "open":
                time.sleep(0.01)

    @property
    def state(self) -> str:
        """Physical solenoid state as returned by the device (typically 'Open'/'Closed')."""
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        return str(self._deviceNET.GetSolenoidState())

    # ---- Misc ----
    def status(self) -> dict[str, bool]:
        """
        Request device status bits and decode a small set of flags.
        """
        if self._deviceNET is None:
            raise RuntimeError("Device not connected.")
        self._deviceNET.RequestStatus()
        res = int(self._deviceNET.GetStatusBits())
        solenoid_output_enabled = bool(res & 0x1)
        # Mirror MATLAB: flip a 4-digit hex string and check if 4th char equals '2'
        # This is heuristic; the exact bit mapping depends on the device firmware.
        reshexflip = "".join(reversed(f"{res:04X}"))
        interlock_enabled = reshexflip[3] == "2"
        return {
            "solenoid_output_enabled": solenoid_output_enabled,
            "solenoid_interlock_enabled": interlock_enabled,
        }

    def __del__(self) -> None:  # pragma: no cover
        try:
            if getattr(self, "_deviceNET", None) is not None:
                self.disconnect()
        except Exception:
            pass

