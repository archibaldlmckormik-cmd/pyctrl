# author: yannik fontana, creation date: 05.05.2026
"""
Smoke tests for ``pd100`` (Thorlabs TLPMX).

- Unit test: ``_unpack_find_rsrc`` (no hardware).
- Hardware test: skipped unless ``PD100_RUN_HW=1``. Optional ``PD100_INTEROP_DLL``,
  ``PD100_ADDRESS``, ``PD100_RESOURCE_INDEX``, ``PD100_CHANNEL``.

Run from repo root (folder containing ``hwdrivers``), e.g.::

    set PD100_RUN_HW=1
    python -m pytest hwdrivers/powermeter/test_pd100.py -v
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hwdrivers.powermeter.pd100 import Pd100, _unpack_find_rsrc  # noqa: E402


class TestUnpackFindRsrc(unittest.TestCase):
    def test_int(self) -> None:
        self.assertEqual(_unpack_find_rsrc(2), 2)

    def test_tuple_count_second(self) -> None:
        self.assertEqual(_unpack_find_rsrc((0, 3)), 3)

    def test_tuple_single(self) -> None:
        self.assertEqual(_unpack_find_rsrc((1,)), 1)


@unittest.skipUnless(
    os.environ.get("PD100_RUN_HW") == "1",
    "Set PD100_RUN_HW=1 (and connect meter) to run TLPMX hardware smoke test.",
)
class TestPD100Hardware(unittest.TestCase):
    def test_smoke_open_readpow_close(self) -> None:
        dll = os.environ.get("PD100_INTEROP_DLL")
        addr = os.environ.get("PD100_ADDRESS")
        idx = int(os.environ.get("PD100_RESOURCE_INDEX", "0"))
        ch = int(os.environ.get("PD100_CHANNEL", "1"))

        kwargs: dict = {"resource_index": idx, "channel": ch}
        if dll:
            kwargs["interop_dll"] = dll
        if addr:
            kwargs["address"] = addr

        with Pd100(**kwargs) as pm:
            self.assertTrue(pm.address)
            wl = pm.wavelength
            self.assertIsInstance(wl, float)
            p_av, p_std = pm.readpow(3)
            self.assertIsInstance(p_av, float)
            self.assertIsInstance(p_std, float)
            self.assertGreaterEqual(p_std, 0.0)


if __name__ == "__main__":
    unittest.main()
