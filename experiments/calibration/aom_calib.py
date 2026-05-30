# author: yannik fontana, creation date: 22.05.2026
"""
Nonresonant HWP scan: step half-wave plate, z-scan cavity, record fluorescence.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime
from typing import Any
from time import sleep

import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from pyctrl.experiments.generic_exp import GenericExp
from pyctrl.toolbox.hardware.oneway_relock import oneway_relock_mass
from pyctrl.toolbox.software.datamanagement import datastructures as ds
from pyctrl.hwdrivers.instrumentsession import Session

logger = logging.getLogger(__name__)

class AOMCalib(GenericExp):
    """
    Calibrate the AOM.
    Measure the power of the laser at the aom photodiode and at the powermeter head.
    versus the AOM voltage.
    aom: string, the name of the aom
    laser_id: string, the id of the laser
    aom and laser_id should go in pairs, but is not enforced. e.g
    aom = AOMg1, laser_id = green_532
    aom = AOMr1, laser_id = velocity2
    aom = AOMr2, laser_id = velocity1
    """

    AOM_PULSE_S = 100e-6
    AOM_RANGE = (0, 1000,101)
    
    def __init__(self, session: Session, aom: str = "AOMg1", laser_id: str = "green_532"):
        self.session = session
        self.setup(aom=aom, laser_id=laser_id)

    def setup(self,aom: str = "", laser_id: str = "") -> None:
        """Setup instruments, data structure, and figure list."""
        self.data = ds.AOMCalibData()
        # complement the data structure with the aom and laser_id
        lookup_laser={"AOMg1": "green_532", "AOMr1": "velocity_2", "AOMr2": "velocity_1"}
        if aom not in lookup_laser:
            logger.error(f"AOMCalib: aom {aom} not recognized in lookup_laser")
            raise ValueError(f"AOMCalib: aom {aom} not recognized in lookup_laser")
        else:
            if laser_id != lookup_laser[aom]:
                logger.warning(f"AOMCalib: laser_id {laser_id} not matchig standard pattern {lookup_laser[aom]}")
        # create the pulse item for the aom
        #
        self.data.pulses[aom] = ds.PulseItem(laser_id=laser_id, aom_amplitude=np.linspace(*AOM_RANGE), duration=AOM_PULSE_S, envelope="rectangular")

        # load the instruments
        self.opx = self.session.get("opx")
        if "AOMg1" in self.data.pulses:
            # load the shutter
            self.shutter = self.session.get("shutter")
        self.pd100 = self.session.get("pd100")
        self.nidaq = self.session.get("nidaq")
        # add the two AI channels to the nidaq
        self.nidaq.add_ai(["ai0", "ai1"])

        self.result_figs: list[Any] = []

    def pre_run(self) -> None:
        """Validate inputs and allocate signal arrays."""
        self.check_for_data(ds.AOMCalibData)
        aom_name = next(iter(self.data.pulses.pulses))
        self.data.signals["powermeter"] = np.zeros(self.data.pulses[aom_name].aom_amplitude.size)
        self.data.signals["photodiode"] = np.zeros(self.data.pulses[aom_name].aom_amplitude.size)
        self.data.timestamp = datetime.now()

    def run(self) -> None:
        """
        Run the calibration of the aom.
        
        """
        self.pre_run()
        aom_name = next(iter(self.data.pulses.pulses))
        aom = self.data.pulses[aom_name]

       

    @classmethod
    def plot(cls, data: ds.ScanHWP_ZData) -> list[go.Figure]:
        """Heatmap of counts vs z/steps and line plot of absolute cavity z offset."""
        