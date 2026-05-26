# author: yannik fontana, creation date: 11.05.2026
"""
Base experiment: instrument session, required hardware, ``setup`` / ``run`` / ``save`` hooks.
DO NOT MODIFY IF NOT NECESSARY
=> THIS CLASS IS USED TO CREATE NEW EXPERIMENTS
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from hwdrivers.instrumentsession import Session
from toolbox.software.save_to_html import save_to_html

logger = logging.getLogger(__name__)


class GenericExp:
    """
    Master experiment class.
    All experiment classes derive from this class, and implement their particular version of "setup", "pre_run", "run", and "plot".
    instance methods:
    The "setup" method is used to initialize the experiment parameters and define the experiment variables
    The "run" method is the main method that performs the experimental protocol.
    The "pre_run" method is used to prepare the experiment for the run.
    The "plot" method is used to plot the results of the experiment.
    The "save" method is used to save the results of the experiment, e.g. to save the data to a file.
    The "logrun" method is used to log the runtime of the experiment to the logger.
    The "check_for_data" method is used to check if a data instance exists. if not, propose to load one.
    class methods:
    The "plot_and_log" method is used to plot the results of the experiment and log the results to the lab journal.
    it leverages the "plot" method usually overridden in the subclass.
    
    Every experiment class must have a compatible/matching datastructure class to save the experiment data.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.setup()


    def setup(self,*args, **kwargs) -> None:
        """Prepare attributes before ``run``.4
        Overwrite or complement in subclasses (e.g. construct ``data`` and ``result_figs``).
        """
        self.data = None
        self.result_figs: list[Any] = []


    def pre_run(self) -> None:
        """Prepare the experiment for the run. Override in subclasses."""
        pass

    def run(self) -> None:
        """Experimental protocol. complement in subclasses."""
        self.pre_run()

    def save(self, overwrite: bool = False) -> None:
        """Delegate to ``self.data.save`` if ``data`` is set."""
        if self.data is None:
            logger.error("Cannot save: ``data`` is None (call ``setup()`` on a subclass that sets it).")
            raise RuntimeError("GenericExp.save: self.data is None")
        self.data.save(overwrite=overwrite)

    def logrun(self, runtime: datetime.timedelta) -> None:
        """Log the runtime of the experiment to the logger."""
        logger.info(f"{self.__class__.__name__} experiment completed successfully at{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} in {runtime.total_seconds()} seconds")

    def check_for_data(self, data_class: type[Any]) -> None:
        """ Checkif a data instance exists. if not, propose to load one.
        """
        if self.data is None:
            logger.info("No data instance found. Proposing to load one.")
            # use the load method to load a data instance
            self.data = data_class.load()

    def plot_and_log(self, *, open_in_edge: bool = True) -> Path | None:
        """
        Build figures from ``self.data``, store them in ``self.result_figs``, and append to the lab journal HTML.
        """
        if self.data is None:
            logger.error("%s.plot_and_log: self.data is None", type(self).__name__)
            raise RuntimeError("self.data is None")
        self.result_figs = type(self).plot(self.data)
        return save_to_html(
            self.data,
            self.result_figs,
            open_in_edge_on_create=open_in_edge,
        )

    @classmethod
    def plot(cls, data: Any) -> list[Any]:
        """
        Build Plotly figures for ``data`` without writing the lab journal.

        Subclasses must override and return a list of ``plotly.graph_objects.Figure``.
        """
        raise NotImplementedError(f"{cls.__name__} must implement plot(data).")