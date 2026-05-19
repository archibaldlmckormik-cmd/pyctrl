# author: yannik fontana, creation date: 06.05.2026
"""
Load and cache flat path entries from configs/path_config.toml.

Cache invalidates when the TOML file's modification time changes.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

# toolbox/software/path_config.py -> parents[2] is pyctrl repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
PATH_CONFIG_TOML = _REPO_ROOT / "configs" / "path_config.toml"

_config_cache: dict[str, str] | None = None
_config_mtime: float | None = None


def load_path_config() -> dict[str, str]:
    """
    Parse configs/path_config.toml.

    Re-reads from disk when the file's mtime changes. Requires ``datapath`` and
    ``labjournalpath`` (string paths).
    """
    global _config_cache, _config_mtime

    if not PATH_CONFIG_TOML.is_file():
        raise FileNotFoundError(f"path config not found: {PATH_CONFIG_TOML}")

    mtime = PATH_CONFIG_TOML.stat().st_mtime
    if _config_cache is not None and _config_mtime == mtime:
        return _config_cache

    with PATH_CONFIG_TOML.open("rb") as f:
        raw = tomllib.load(f)

    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            raise TypeError(
                f"path_config.toml key {key!r} must be a string path, "
                f"got {type(value).__name__}"
            )
        out[key] = value

    for required in ("datapath", "labjournalpath"):
        if required not in out:
            raise KeyError(
                f"path_config.toml must define {required!r}; "
                f"found keys: {sorted(out)!r}"
            )

    _config_cache = out
    _config_mtime = mtime
    return out


def get_datapath() -> str:
    """Root directory for experiment data (``datapath`` in path_config.toml)."""
    return load_path_config()["datapath"]


def get_labjournalpath() -> str:
    """Root directory for lab journal files (``labjournalpath`` in path_config.toml)."""
    return load_path_config()["labjournalpath"]

def get_qmconfigpath() -> str:
    """Path to the quantum machine configuration file (``qmconfigpath`` in path_config.toml)."""
    return load_path_config()["qmconfigpath"]


def reload_path_config() -> dict[str, str]:
    """Force a fresh read of path_config.toml (ignores mtime cache)."""
    global _config_cache, _config_mtime
    _config_cache = None
    _config_mtime = None
    return load_path_config()
