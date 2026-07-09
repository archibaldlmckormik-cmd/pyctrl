# author: yannik fontana, creation date: 05.05.2026
"""
This module defines the data structures for the experimental results.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self
import tkinter as tk
from tkinter import filedialog
import numpy as np
import h5py
import datetime
import os
from pyctrl.toolbox.software.path_config import get_datapath
from .dataparsing import DEFAULT_MAX_DEPTH, read_instance_from_h5, write_instance_to_h5

logger = logging.getLogger(__name__)

def _default_datafolder() -> str:
    """
    Returns the default data folder.
    """
    return get_datapath()

# definition of the sub components of the data classes:
# CAVITY POSITION
@dataclass
class CavityParameters:
    """
    defines the data structure for the cavity parameters.
    """

    x: np.ndarray | None = None
    y: np.ndarray | None = None
    z: np.ndarray | None = None

# PULSES 
# class for the collection of pulses
@dataclass
class PulseSet:
    """
    Defines a set/collection of laser pulses.
    """
    pulses: dict[str, PulseItem] = field(default_factory=dict)
    
    # method to the pulseset objects
    def __getitem__(self, key: str) -> PulseItem:
        """
        Returns the PulseItem object for the given key.
        """
        if key not in self.pulses.keys():
            logger.error(f"Pulse item with key {key} not found. Returned None.")
            return None
        return self.pulses[key]

    def __setitem__(self, key: str, value: PulseItem):
        """
        Sets the PulseItem object for the given key.
        """
        if key in self.pulses.keys():
            logger.warning(f"Pulse item with key {key} already exists.")
        else:
            self.pulses[key] = value

    def __delitem__(self, key: str):
        """
        Deletes the PulseItem object for the given key.
        """
        del self.pulses[key]
    
# Class for a single laser item
@dataclass
class PulseItem:
    """
    Defines the parameters of a single (laser) pulse.
    """
    laser_id: str = ""
    aom_amplitude: float | np.ndarray | None = None
    eom_amplitude: float | np.ndarray | None = None
    duration: float | np.ndarray | None = None
    envelope: str | None = None
    power: float | np.ndarray | None = None
    frequency: float | np.ndarray | None = None

# ITERATIONS
# class for the collection of iterations
@dataclass
class IterationSet:
    """
    Defines a set/collection of iteration items.
    """
    iterations: dict[str, IterationItem] = field(default_factory=dict)

    # method to the iterationset objects
    def __getitem__(self, key: str) -> IterationItem:
        """
        Returns the IterationItem object for the given key.
        """
        if key not in self.iterations.keys():
            logger.error(f"Iteration item with key {key} not found. Returned None.")
            return None
        return self.iterations[key]

    def __setitem__(self, key: str, value: IterationItem):
        """
        Sets the IterationItem object for the given key.
        """
        if key in self.iterations.keys():
            logger.warning(f"Iteration item with key {key} already exists.")
        else:
            self.iterations[key] = value

    def __delitem__(self, key: str):
        """
        Deletes the IterationItem object for the given key.
        """
        del self.iterations[key]

# Class for a single iteration item
@dataclass
class IterationItem:
    """
    Defines the parameters of a single iteration item.
    """
    description: str = ""
    values: np.ndarray | list[float] | int | float | None = None

# GENERIC EXPERIMENTAL DATA
# definition of the data class "template" (a parent class for all experimental data classes)
@dataclass
class ExpData:
    """
    A generic class for experimental data. Parent class for all experiment-specific data classes.
    """
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    tag: list[str] = field(default_factory=list)
    run_time:float = field(default_factory=float, default=0.0)
    cavity: CavityParameters = field(default_factory=CavityParameters)
    pulses: PulseSet = field(default_factory=PulseSet)
    iterations: IterationSet = field(default_factory=IterationSet)
    signals: dict[str,np.ndarray] = field(default_factory=dict)

    def __post_init__(self):
        """
        Post-initialization method to set the filename.
        """
        # chelck if the appropriate subfolder exists, if not create it
        root = Path(_default_datafolder())
        class_name = type(self).__name__
        date_s = self.timestamp.strftime("%Y%m%d")
        data_dir = root / f"{class_name}" / date_s
        data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Data directory: %s", data_dir)

        h5_files = sorted(p.name for p in data_dir.glob("*.h5"))
        # check if there are any files in the subfolder, if not, the dataset number is 0 and the filename is
        if not h5_files:
            n = 0
        else:
            # otherwise, the dataset number is the highest number suffix + 1
            n = int(h5_files[-1].removesuffix(".h5").split("_")[-1]) + 1

        self.filename = f"{class_name}_{date_s}_{n:03d}.h5"
        self.filepath = str(data_dir)

    def save(self, overwrite: bool = False):
        """
        Saves the experimental data to the data file.
        """
        fullpath = os.path.join(self.filepath, self.filename)
        # check if the file exists, if it does and overwrite is False, rename the file by changing the number suffix
        if os.path.exists(fullpath) and not overwrite:
            # sort the files alphabetically, the last one has the highest number suffix
            files = sorted(os.listdir(self.filepath))
            # the last one has the highest number suffix
            lastfile = files[-1]
            # get the number suffix
            number = int((lastfile.removesuffix(".h5")).split("_")[-1])
            # set the new filename
            newfilename = type(self).__name__+f"_{self.timestamp.strftime('%Y%m%d')}_{number+1:03d}.h5"
            # update the instance filename and filepath
            self.filename = newfilename
            # log the warning:
            logger.warning(f"File {fullpath} already exists. Renamed to {newfilename}.")
            # update the fullpath variable
            fullpath = os.path.join(self.filepath, newfilename)
        elif os.path.exists(fullpath) and overwrite:
            # delete the file
            os.remove(fullpath)
            # log the warning:
            logger.warning(f"File {fullpath} already exists and will be overwritten.")

        # now save the data to the file, using h5py:
        with h5py.File(fullpath, "w") as f:
            write_instance_to_h5(f, self, max_depth=DEFAULT_MAX_DEPTH)

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        group_name: str = "run",
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> Self:
        """
        Load from HDF5 without running ``__init__`` / ``__post_init__``.

        If ``path`` is omitted, a file dialog opens (initial directory from ``datapath``).
        """
        if path is None:
            # open a file dialog to select the data file
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except tk.TclError:
                pass
            picked = filedialog.askopenfilename(
                initialdir=get_datapath(),
                title="Select experiment HDF5",
                filetypes=[("HDF5", "*.h5"), ("All files", "*.*")],
            )
            root.destroy()
            if not picked:
                raise FileNotFoundError("No HDF5 file selected.")
            path = picked

        return read_instance_from_h5(
            Path(path),
            target_cls=cls,
            group_name=group_name,
            max_depth=max_depth,
        )

# SPECIFIC EXPERIMENTAL DATA
# Non-resonant ScanXY_Z experiment data class
@dataclass
class ScanXY_ZData(ExpData):
    """
    Defines the data structure for the ScanXY_Z experiment.
    """
    def __post_init__(self) -> None:
        super().__post_init__()
        self.pulses["AOMg1"] = PulseItem(laser_id="green_532", frequency=563.8, envelope="rectangular")
        self.iterations["repeat_per_pixel"] = IterationItem(description="number of pulses per pixel", values=1)
        self.signals.update({"counts": np.array([]), "z_offset": np.array([])})


# Non-resonant ScanHWP_Z experiment data class
@dataclass
class AOMCalibData(ExpData):
    """
    Defines the data structure for the aom calibration.
    """
    def __post_init__(self) -> None:
        super().__post_init__()
        self.iterations["read_rep"] = IterationItem(description="number of power read per voltage", values=5)
        self.signals.update({"powermeter": np.array([]), "photodiode": np.array([])})

@dataclass
class ScanHWP_ZData(ExpData):
    """
    Defines the data structure for the ScanHWP_Z experiment.
    """
    def __post_init__(self) -> None:
        super().__post_init__()
        self.pulses["AOMg1"] = PulseItem(laser_id="green_532", frequency=563.8, envelope="rectangular")
        self.iterations["repeat_per_pixel"] = IterationItem(description="number of pulses per pixel", values=1)
        self.hwp = {"step_voltage": 50, "step_number": 10000}
        self.signals.update({"counts": np.array([]), "z_offset": np.array([])})


# Resonant RF spectra experiment data class
@dataclass
class RfSpectraData(ExpData):
    """
    Defines the data structure for the RF spectra experiment.
    """
    pass