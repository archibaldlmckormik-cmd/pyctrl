# author: yannik fontana, creation date: 12.05.2026
"""
Collection of nonresonant experiments.
Typically the only laser involved is a green 532nm laser exciting the emitter.
The swepts parameters and means of detection are experiment specific.
"""
from __future__ import annotations

import logging
from typing import Any
import numpy as np
from experiments.generic_exp import GenericExp
from hwdrivers.instrumentsession import Session

logger = logging.getLogger(__name__)

# SCANXY_Z
@dataclass
class InputsScanXY_Z():
    """
    Input parameters for the ScanXY_Z experiment
    """
    cavity_x: None | np.ndarray | float | str = None
    cavity_y: None | np.ndarray | float | str = None
    cavity_z: None | np.ndarray | float | str = None
    power_green: None | float = None
    
    
class ScanXY_Z(GenericExp):
    """
    Excite with green laser.
    For a given grid of x and y cavity positions, scans the cavity along the z axis and records the fluorescence signal on an APD.
    for each z scan, an updated cavity resonance voltage is calculated.
    """
    def __init__(self, *args, **kwargs):
        # relay the __init__ of the Generic_Exp class
        super().__init__(*args, **kwargs)
        # define ScanXY_Z spepcific attributes:
        