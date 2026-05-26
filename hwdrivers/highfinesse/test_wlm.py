# author: yannik fontana, creation date: 05.05.2026
import os
import pathlib
import sys
import unittest


# Allow running from within the `pyctrl/...` tree without install.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hwdrivers.highfinesse.wlm import Wlm  # noqa: E402


_SERVER = os.environ.get("WLM_SERVER")
_PORT = os.environ.get("WLM_PORT")

_CH1 = {
    "laser_id": "test_ch1",
    "PID_P": 0.1,
    "PID_I": 0.03,
    "PID_D": 0.05,
    "PID_ta": 0.005,
    "PID_sensitivity_factor": 1.0,
    "PID_polarity": -1.0,
}
_CH2 = {
    "laser_id": "test_ch2",
    "PID_P": 0.1,
    "PID_I": 0.03,
    "PID_D": 0.05,
    "PID_ta": 0.005,
    "PID_sensitivity_factor": 1.0,
    "PID_polarity": -1.0,
}


@unittest.skipUnless(_SERVER and _PORT, "Set WLM_SERVER and WLM_PORT to run this hardware test.")
class TestWlm(unittest.TestCase):
    def test_smoke_open_get_frequency_close(self) -> None:
        with Wlm(
            _SERVER,
            int(_PORT),
            ch1=_CH1,
            ch2=_CH2,
            validate_on_init=True,
        ) as wlm:
            _ = wlm.ch1.frequency
            _ = wlm.ch2.frequency


if __name__ == "__main__":
    unittest.main()
