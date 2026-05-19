# author: yannik fontana, creation date: 05.05.2026
import os
import pathlib
import sys
import unittest


# Allow running from within the `pyctrl/...` tree without install.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pyctrl.hwdrivers.wlm.wlm import WLM  # noqa: E402


_SERVER = os.environ.get("WLM_SERVER")
_PORT = os.environ.get("WLM_PORT")


@unittest.skipUnless(_SERVER and _PORT, "Set WLM_SERVER and WLM_PORT to run this hardware test.")
class TestWLM(unittest.TestCase):
    def test_smoke_open_get_frequency_close(self) -> None:
        with WLM(_SERVER, int(_PORT), validate_on_init=True) as wlm:
            _ = wlm.frequency_ch1
            _ = wlm.frequency_ch2


if __name__ == "__main__":
    unittest.main()

