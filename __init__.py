# author: yannik fontana, created 20.04.2026
"""
PyCtrl — Python control stack for the NV/cavity setup.

Importing ``pyctrl`` gives you the single hardware entry point, :class:`Session`.
Everything else lives in clearly named sub-packages that you import directly:

    import pyctrl
    from pyctrl.experiments.nonresonant.scanhwp_z import ScanHWP_Z
    from pyctrl.toolbox.software import common_mathfuns

    pyctrl.setup_logging()      # optional; once per kernel — see README
    pyctrl.shutdown_logging()   # tear down handlers when done

    with pyctrl.Session() as session:
        ...

Sub-packages
------------
- ``pyctrl.hwdrivers``   instrument drivers + the ``Session`` instrument pool
- ``pyctrl.experiments`` ``GenericExp`` and concrete experiment classes
- ``pyctrl.toolbox``     ``software/`` (data, plotting, IO) and ``hardware/`` routines
"""

__author__ = "yannik fontana"
__version__ = "0.1.0"

from pyctrl.hwdrivers import Session
from pyctrl.toolbox.software.logging_config import setup_logging, shutdown_logging
from pyctrl import experiments

__all__ = ["Session", "setup_logging", "shutdown_logging", "experiments", "__version__"]
