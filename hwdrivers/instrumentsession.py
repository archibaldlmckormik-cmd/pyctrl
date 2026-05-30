# author: yannik fontana, creation date: 05.05.2026
"""
Lazy instrument session: load instrument config TOML, open drivers on ``get()``.

Uses ``instr_config.local.toml`` when present, else ``instr_config.toml``.
An explicit ``config_path`` bypasses that resolution.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from pyctrl.hwdrivers.attocube.anc300 import Anc300
from pyctrl.hwdrivers.baspidac.dac import Dac
from pyctrl.hwdrivers.highfinesse.wlm import Wlm
from pyctrl.hwdrivers.lecroy.lecroy import Scope
from pyctrl.hwdrivers.nidaq.nidaq import Nidaq
from pyctrl.hwdrivers.powermeter.pd100 import Pd100
from pyctrl.hwdrivers.qm_opx.qm_opx import Opx
from pyctrl.hwdrivers.shutterSH05.shutterSH05 import ShutterSH05
from pyctrl.hwdrivers.spectrometer.princeton import SpecRemote
from pyctrl.hwdrivers.timetagger.picoharp300 import Pharp
from pyctrl.toolbox.software.path_config import _resolve_config_path

logger = logging.getLogger(__name__)

# class registry, binding the string name in the config to the actual class
CLASS_REGISTRY = {
    "opx": Opx,
    "dac": Dac,
    "wlm": Wlm,
    "shutterSH05": ShutterSH05,
    "nidaq": Nidaq,
    "scope": Scope,
    "spec_remote": SpecRemote,
    "pd100": Pd100,
    "anc300": Anc300,
    "pharp": Pharp,
}

class Session:
    """Instrument pool backed by instrument config TOML; drivers open on first ``get``.
    Usage:
    with Session() as session:
        # open you instrument here
        your_instrument = session.get("your_instrument")
        # to see all available instruments:
    print(session.available_instruments)
    # the instrument will be closed automatically
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = _resolve_config_path("instr_config")
        else:
            config_path = Path(config_path)
        try:
            with open(config_path, "rb") as f:
                raw_cfg = tomllib.load(f)
        except OSError as exc:
            logger.error(
                "Session: cannot read instrument config %s: %s",
                config_path,
                exc,
            )
            raise
        except tomllib.TOMLDecodeError as exc:
            logger.error("Session: invalid TOML in %s: %s", config_path, exc)
            raise

        self._config: dict[str, dict[str, Any]] = {}
        for name, params in raw_cfg.items():
            cfg = dict(params)
            cls_name = cfg.get("cls")
            if cls_name not in CLASS_REGISTRY:
                logger.error(
                    "Session: unknown instrument class %r for %r; registry keys: %s",
                    cls_name,
                    name,
                    sorted(CLASS_REGISTRY),
                )
                raise KeyError(
                    f"Unknown instrument class {cls_name!r} for instrument {name!r}"
                )
            cfg["cls"] = CLASS_REGISTRY[cls_name]
            self._config[name] = cfg

        self._instruments: dict[str, Any] = {}
        logger.info(
            "Session: loaded %d instrument(s) from %s",
            len(self._config),
            config_path,
        )

    @property
    def available_instruments(self) -> list[str]:
        """Names that can be passed to ``get()`` (from the loaded config, no drivers opened)."""
        return list(self._config.keys())

    def get(self, name: str) -> Any:
        if name in self._instruments:
            return self._instruments[name]

        if name not in self._config:
            logger.error("Session: instrument %r not found in config", name)
            raise KeyError(f"Instrument {name!r} not found in config")

        cfg = self._config[name].copy()
        cls = cfg.pop("cls")
        try:
            inst = cls(**cfg)
        except Exception as exc:
            logger.error("Session: failed to build instrument %r: %s", name, exc)
            raise RuntimeError(f"Session: failed to build instrument {name!r}") from exc

        self._instruments[name] = inst
        logger.info("Session: opened instrument %r (%s)", name, cls.__name__)
        return inst

    def close_all(self) -> None:
        if not self._instruments:
            return
        for name, inst in list(self._instruments.items()):
            try:
                inst.close()
                logger.info("Session: closed instrument %r", name)
            except Exception as exc:
                logger.warning("Session: close failed for %r: %s", name, exc)
        self._instruments.clear()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *_: object) -> None:
        self.close_all()
