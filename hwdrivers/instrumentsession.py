# author: yannik fontana, creation date: 05.05.2026
import tomllib
from pathlib import Path
# the packages for all instrument classes
# add package to add one specific instrument class to be available in the session
from hwdrivers.baspidac.dac import Dac
from hwdrivers.shutterSH05.shutterSH05 import ShutterSH05
from hwdrivers.nidaq.nidaq import Nidaq
from hwdrivers.highfinesse.wlm import Wlm
from hwdrivers.lecroy.lecroy import Scope
from hwdrivers.spectrometer.princeton import SpecRemote
from hwdrivers.qm_opx.qm_opx import Opx
from hwdrivers.powermeter.pd100 import Pd100
from hwdrivers.attocube.anc300 import Anc300
from hwdrivers.timetagger.picoharp300 import Pharp
# class registry, binding the string name in the config to the actual class
# add class to add one specific instrument class to be available in the session
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

DEFAULT_CONFIG_PATH = Path(__file__).parents[1] / "configs" / "instr_config.toml"

class Session:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        with open(config_path, "rb") as f:
            raw_cfg = tomllib.load(f)
        # resolve string class names to actual classes
        self._config = {}
        for name, params in raw_cfg.items():
            cfg = params.copy()
            cfg["cls"] = CLASS_REGISTRY[cfg["cls"]]
            self._config[name] = cfg

        self._instruments = {}

    def get(self, name: str):
        if name not in self._instruments:
            if name not in self._config:
                raise KeyError(f"Instrument '{name}' not found in config")
            cfg = self._config[name].copy()
            cls = cfg.pop("cls")
            self._instruments[name] = cls(**cfg)
        return self._instruments[name]

    def close_all(self):
        for inst in self._instruments.values():
            inst.close()
        self._instruments.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close_all()
