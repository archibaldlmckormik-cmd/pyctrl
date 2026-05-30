# author: yannik fontana, creation date: 30.05.2026
"""Unit tests for ShutterSH05 lifecycle (no hardware)."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import MagicMock

_PROJECT_PARENT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from pyctrl.hwdrivers.shutterSH05.shutterSH05 import ShutterSH05  # noqa: E402


class TestShutterSH05Close(unittest.TestCase):
    def test_close_idempotent(self) -> None:
        shutter = ShutterSH05.__new__(ShutterSH05)
        device = MagicMock()
        shutter._deviceNET = device
        shutter._initialized = True
        shutter.serialnumber = "68000001"
        shutter.controllername = "KCube"
        shutter.controllerdescription = "desc"
        shutter.stagename = "SH05"

        shutter.close()
        shutter.close()

        device.StopPolling.assert_called_once()
        device.DisableDevice.assert_called_once()
        device.Disconnect.assert_called_once()
        self.assertIsNone(shutter._deviceNET)
        self.assertFalse(shutter._initialized)

    def test_close_noop_when_never_connected(self) -> None:
        shutter = ShutterSH05.__new__(ShutterSH05)
        shutter._deviceNET = None
        shutter._initialized = False
        shutter.close()
        self.assertIsNone(shutter._deviceNET)


if __name__ == "__main__":
    unittest.main()
