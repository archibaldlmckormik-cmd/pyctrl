# author: yannik fontana, creation date: 05.05.2026
import os
import pathlib
import sys
import unittest


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import clr  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    clr = None

from pyctrl.hwdrivers.shutterSH05.shutterSH05 import ShutterSH05  # noqa: E402


_SERIAL = os.environ.get("SH05_SERIAL")


@unittest.skipUnless(clr is not None and _SERIAL, "Set SH05_SERIAL and install pythonnet to run this test.")
class TestShutterSH05(unittest.TestCase):
    def test_connect_read_state_toggle_if_allowed(self) -> None:
        allow_toggle = os.environ.get("SH05_TOGGLE", "").lower() in {"1", "true", "yes"}
        with ShutterSH05(_SERIAL, validate_on_init=True) as sh:
            self.assertTrue(sh.isconnected)
            _ = sh.state
            _ = sh.open
            if allow_toggle:
                sh.open = True
                self.assertTrue(sh.open)
                sh.open = False
                self.assertFalse(sh.open)


if __name__ == "__main__":
    unittest.main()

