# author: yannik fontana, creation date: 05.05.2026
import logging
import os
import pathlib
import sys
import unittest


# Allow running this file directly without `pip install -e .`: put the folder
# that *contains* the `pyctrl` package (the repo's parent) on sys.path.
_PROJECT_PARENT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from pyctrl.hwdrivers.baspidac.dac import Dac  # noqa: E402


logging.basicConfig(level=logging.INFO)

_COM_PORT = os.environ.get("DAC_COM_PORT")


@unittest.skipUnless(_COM_PORT, "Set DAC_COM_PORT (e.g. COM3) to run this hardware test.")
class TestDAC(unittest.TestCase):
    def test_smoke_open_read_write_close(self) -> None:
        # Match MATLAB constructor behavior by validating communication on init.
        with Dac(_COM_PORT, validate_on_init=True) as dac:
            # Basic readback
            voltage_original = dac.voltage["1"]
            _ = dac.status["1"]

            # No-op smooth ramp (verifies API path without changing output).
            dac.voltage.smooth_ramp("1", voltage_original)

            # Basic write: restore channel 1 voltage.
            dac.voltage[1] = voltage_original
            voltage_readback = dac.voltage["1"]
            self.assertEqual(voltage_original, voltage_readback)


if __name__ == "__main__":
    unittest.main()
