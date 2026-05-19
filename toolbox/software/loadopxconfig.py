# author: yannik fontana, creation date: 05.05.2026
"""
This module contains functions to load and format the OPX TOMLconfiguration file
to a suitable python dictionnary.
"""
import tomllib
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


DEFAULT_OPX_CONFIG_PATH = Path(__file__).parents[2] / "configs" / "qm_base_config.toml"


def load_opx_config(config_path: Path = DEFAULT_OPX_CONFIG_PATH):
    """
    Loads the OPX configuration file from supplied/default path
    and returns a nested dictionnary replacing lists by tuples
    """
    try:
        with open(config_path, "rb") as f:
                raw_cfg = tomllib.load(f)
    except OSError as exc:
        logger.error("Session: cannot read instrument config %s: %s", config_path, exc)
        raise
    except tomllib.TOMLDecodeError as exc:
        logger.error("Session: invalid TOML in %s: %s", config_path, exc)
        raise
    return raw_cfg

def dict_list_to_tuple(d: dict) -> dict:
    """
    searches through a nested dictionary and replaces all lists with tuples
    """
    for key, value in d.items():
        if isinstance(value, list):
            d[key] = tuple(value)
        elif isinstance(value, dict):
            d[key] = dict_list_to_tuple(value)
    return d