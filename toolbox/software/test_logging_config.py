# author: yannik fontana, creation date: 30.05.2026
"""Unit tests for PyCtrl logging setup (no path_config disk dependency)."""

from __future__ import annotations

import logging
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime

_PROJECT_PARENT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from pyctrl.toolbox.software.logging_config import (  # noqa: E402
    _DailyFileHandler,
    setup_logging,
    shutdown_logging,
)


class TestDailyFileHandler(unittest.TestCase):
    def test_writes_dated_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = pathlib.Path(tmpdir)
            handler = _DailyFileHandler(log_dir, logging.INFO)
            handler.setFormatter(logging.Formatter("%(message)s"))
            created = datetime(2026, 5, 30, 12, 0, 0).timestamp()
            record = logging.LogRecord(
                name="pyctrl.test",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="hello",
                args=(),
                exc_info=None,
            )
            record.created = created
            handler.emit(record)
            handler.close()
            expected = log_dir / "pyctrl_2026-05-30.log"
            self.assertTrue(expected.exists())
            self.assertIn("hello", expected.read_text(encoding="utf-8"))


class TestSetupLogging(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_logging()

    def test_replace_handlers_on_second_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir, log_to_console=False)
            logger = logging.getLogger("pyctrl")
            self.assertEqual(len(logger.handlers), 1)
            setup_logging(log_dir=tmpdir, log_to_console=False)
            self.assertEqual(len(logger.handlers), 1)
            shutdown_logging()

    def test_disabled_via_enabled(self) -> None:
        setup_logging(enabled=False)
        self.assertEqual(len(logging.getLogger("pyctrl").handlers), 0)

    def test_shutdown_removes_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir, log_to_console=False)
            logger = logging.getLogger("pyctrl")
            self.assertEqual(len(logger.handlers), 1)
            shutdown_logging()
            self.assertEqual(len(logger.handlers), 0)
            self.assertEqual(logger.level, logging.NOTSET)
            self.assertTrue(logger.propagate)
            shutdown_logging()

    def test_shutdown_resets_noisy_loggers_when_requested(self) -> None:
        setup_logging(log_to_file=False, log_to_console=False)
        logging.getLogger("qm").setLevel(logging.WARNING)
        shutdown_logging(reset_noisy_loggers=True)
        self.assertEqual(logging.getLogger("qm").level, logging.NOTSET)


if __name__ == "__main__":
    unittest.main()
