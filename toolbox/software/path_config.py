# author: yannik fontana, creation date: 06.05.2026
"""
Load and cache flat path entries from configs/path_config.toml or path_config.local.toml.

If ``<stem>.local.toml`` exists, only that file is used; otherwise the tracked ``<stem>.toml``.
"""
from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# toolbox/software/path_config.py -> parents[2] is pyctrl repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIGS_DIR = _REPO_ROOT / "configs"

_config_cache: dict[str, str] | None = None
_config_mtime: float | None = None
_resolved_path_config: Path | None = None


def _resolve_config_path(stem: str) -> Path:
    """
    Resolve a config file under ``configs/``.

    Uses ``<stem>.local.toml`` when present, else ``<stem>.toml``.
    ``stem`` is e.g. ``path_config`` or ``instr_config`` (no extension).
    """
    local_path = _CONFIGS_DIR / f"{stem}.local.toml"
    default_path = _CONFIGS_DIR / f"{stem}.toml"
    if local_path.is_file():
        logger.info("Using %s config: %s", stem, local_path)
        return local_path
    if default_path.is_file():
        logger.info("Using %s config: %s (no local override)", stem, default_path)
        return default_path
    raise FileNotFoundError(
        f"config not found for {stem!r}: tried {local_path} and {default_path}"
    )


def _path_config_file() -> Path:
    global _resolved_path_config
    if _resolved_path_config is None:
        _resolved_path_config = _resolve_config_path("path_config")
    return _resolved_path_config


def load_path_config() -> dict[str, str]:
    """
    Parse the resolved path config TOML.

    Re-reads from disk when the file's mtime changes. Requires ``datapath``,
    ``labjournalpath``, and ``logspath`` (string paths).
    """
    global _config_cache, _config_mtime

    path = _path_config_file()
    if not path.is_file():
        raise FileNotFoundError(f"path config not found: {path}")

    mtime = path.stat().st_mtime
    if _config_cache is not None and _config_mtime == mtime:
        return _config_cache

    with path.open("rb") as f:
        raw = tomllib.load(f)

    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            raise TypeError(
                f"{path.name} key {key!r} must be a string path, "
                f"got {type(value).__name__}"
            )
        out[key] = value

    for required in ("datapath", "labjournalpath", "logspath"):
        if required not in out:
            raise KeyError(
                f"{path.name} must define {required!r}; "
                f"found keys: {sorted(out)!r}"
            )

    _config_cache = out
    _config_mtime = mtime
    return out


def get_datapath() -> str:
    """Root directory for experiment data (``datapath`` in path config)."""
    return load_path_config()["datapath"]


def get_labjournalpath() -> str:
    """Root directory for lab journal files (``labjournalpath`` in path config)."""
    return load_path_config()["labjournalpath"]


def get_logspath() -> str:
    """Root directory for PyCtrl log files (``logspath`` in path config)."""
    return load_path_config()["logspath"]


def get_qmconfigpath() -> str:
    """Path to the quantum machine configuration file (``qmconfigpath`` in path config)."""
    return load_path_config()["qmconfigpath"]


def reload_path_config() -> dict[str, str]:
    """Force a fresh read of path config (ignores mtime cache)."""
    global _config_cache, _config_mtime, _resolved_path_config
    _config_cache = None
    _config_mtime = None
    _resolved_path_config = None
    return load_path_config()
