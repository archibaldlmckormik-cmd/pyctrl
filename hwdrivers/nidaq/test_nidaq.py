# author: yannik fontana, creation date: 05.05.2026
"""
Hardware smoke test for ``nidaq`` (skipped without nidaqmx / NI device env).

Set ``NIDAQ_DEVICE`` (e.g. Dev1) to run; optionally ``NIDAQ_AI`` (e.g. ai0) for a short read.
"""

import os
import pathlib
import sys
import unittest


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import nidaqmx  # noqa: F401
except ModuleNotFoundError:
    nidaqmx = None

from hwdrivers.nidaq.nidaq import Nidaq


_DEVICE = os.environ.get("NIDAQ_DEVICE")
_AI = os.environ.get("NIDAQ_AI", "ai0")


@unittest.skipUnless(nidaqmx is not None and _DEVICE, "Set NIDAQ_DEVICE and install nidaqmx to run.")
class TestNidaq(unittest.TestCase):
    def test_smoke_read_one_sample(self) -> None:
        with Nidaq(_DEVICE) as d:
            d.rate = 1000.0
            d.add_ai([_AI])
            x = d.readFG(1)
            self.assertEqual(x.shape, (1, 1))


if __name__ == "__main__":
    unittest.main()
