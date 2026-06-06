# author: yannik fontana, creation date: 30.05.2026
"""
Configure stdlib logging for the ``pyctrl`` logger tree.

Call :func:`setup_logging` explicitly (e.g. first cell in a notebook). ``import pyctrl``
does not configure logging.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from logging import Handler, LogRecord
from pathlib import Path
from typing import TextIO, Union

from pyctrl.toolbox.software.path_config import get_logspath

LevelType = Union[int, str]

_FMT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_NOISY_LOGGERS = ("qm", "urllib3", "grpc", "matplotlib")


def _resolve_level(level: LevelType) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        name = level.strip().upper()
        value = logging.getLevelNamesMapping().get(name)
        if value is not None:
            return value
        raise ValueError(f"Unknown log level {level!r}")
    raise TypeError(f"level must be int or str, got {type(level).__name__}")


class _DailyFileHandler(Handler):
    """
    Append to ``pyctrl_YYYY-MM-DD.log`` under ``log_dir``.

    Chooses the file from the record emission time (local date), so long notebook
    kernels roll over at midnight without re-running setup.
    """

    def __init__(self, log_dir: Path, level: int) -> None:
        super().__init__(level)
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._current_day: date | None = None
        self._stream: TextIO | None = None
        self._path: Path | None = None

    def _path_for(self, day: date) -> Path:
        return self._log_dir / f"pyctrl_{day.isoformat()}.log"

    def _ensure_stream(self, day: date) -> None:
        if self._current_day == day and self._stream is not None:
            return
        self._close_stream()
        self._current_day = day
        self._path = self._path_for(day)
        self._stream = self._path.open("a", encoding="utf-8")

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self._current_day = None
        self._path = None

    @property
    def current_path(self) -> Path | None:
        return self._path

    def emit(self, record: LogRecord) -> None:
        try:
            day = datetime.fromtimestamp(record.created).date()
            self._ensure_stream(day)
            msg = self.format(record)
            assert self._stream is not None
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self._close_stream()
        super().close()


def setup_logging(
    *,
    log_level: LevelType = "INFO",
    log_level_file: LevelType = "INFO",
    log_level_console: LevelType = "WARNING",
    log_dir: str | Path | None = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
    enabled: bool = True,
) -> Path | None:
    """
    Attach handlers to the ``pyctrl`` logger.

    Safe to call again in a notebook: existing handlers on ``pyctrl`` are removed and
    replaced (no duplicate lines). Re-running does not change which daily file is active
    except after midnight, when the file handler switches on the next emit.

    Parameters
    ----------
    log_level
        Level on the ``pyctrl`` logger (default ``INFO``).
    log_level_file
        Minimum level written to the daily log file (default ``INFO``).
    log_level_console
        Minimum level printed to stderr / the notebook (default ``WARNING``).
    log_dir
        Directory for log files. If omitted, uses ``logspath`` from path config.
    log_to_file, log_to_console
        Enable file and/or console handlers.
    enabled
        If ``False``, or env ``PYCTRL_LOG`` is ``0`` / ``false`` / ``no``, does nothing.

    Returns
    -------
    Path | None
        Path to the active daily log file after setup, if a file handler was added.
    """
    if not enabled:
        return None
    env = os.environ.get("PYCTRL_LOG", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return None

    pyctrl_logger = logging.getLogger("pyctrl")
    pyctrl_logger.setLevel(_resolve_level(log_level))
    pyctrl_logger.propagate = False

    for handler in list(pyctrl_logger.handlers):
        pyctrl_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)
    log_file_path: Path | None = None

    if log_to_file:
        directory = Path(log_dir) if log_dir is not None else Path(get_logspath())
        file_handler = _DailyFileHandler(directory, _resolve_level(log_level_file))
        file_handler.setFormatter(formatter)
        pyctrl_logger.addHandler(file_handler)
        file_handler._ensure_stream(date.today())
        log_file_path = file_handler.current_path

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(_resolve_level(log_level_console))
        console_handler.setFormatter(formatter)
        pyctrl_logger.addHandler(console_handler)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    if log_file_path is not None:
        pyctrl_logger.info("PyCtrl logging to %s", log_file_path)
    return log_file_path
