# author: yannik fontana, creation date: 11.05.2026
"""
Base experiment: instrument session, required hardware, ``setup`` / ``run`` / ``save`` hooks.
DO NOT MODIFY IF NOT NECESSARY
=> THIS CLASS IS USED TO CREATE NEW EXPERIMENTS
"""
from __future__ import annotations

import logging
from typing import Any

from hwdrivers.instrumentsession import Session

logger = logging.getLogger(__name__)


class GenericExp:
    """
    Master experiment class.
    All experiment classes derive from this class, and implement their particular version of "setup", "run", and "plot".
    The "setup" method is used to initialize the experiment parameters and define the experiment variables
    The "run" method is the main method that performs the experimental protocol.
    The "plot" method is used to plot the results of the experiment. It uses save_to_html from the toolbox to save the plots to a html journal.
    The "save" method is used to save the results of the experiment, e.g. to save the data to a file.

    Every experiment class must have a compatible/matching datastructure class to save the experiment data.
    """

    required_instruments: list[str] = []

    def __init__(self, session: Session) -> None:
        self.session = session
        self.setup()
        self.confirm_instruments()

    def confirm_instruments(self) -> None:
        """Ensure every name in ``required_instruments`` is reachable via ``session.get``."""
        if self.required_instruments is None:
            logger.error("GenericExp.confirm_instruments: Required instruments list is not set.")
            raise 
        for name in self.required_instruments:
            try:
                self.session.get(name)
            except KeyError:
                logger.error(
                    "Required instrument %r is not in the session config (check instr_config.toml).",
                    name,
                )
                raise

    def setup(self) -> None:
        """Prepare attributes before ``run``. Overwrite or complement in subclasses (e.g. construct ``data``)."""
        self.required_instruments = None
        self.data = None
        self.result_figs: list[Any] = []

    def run(self) -> None:
        """Experimental protocol. Override in subclasses."""
        pass

    def save(self, overwrite: bool = False) -> None:
        """Delegate to ``self.data.save`` if ``data`` is set."""
        if self.data is None:
            logger.error("Cannot save: ``data`` is None (call ``setup()`` on a subclass that sets it).")
            raise RuntimeError("GenericExp.save: self.data is None")
        self.data.save(overwrite=overwrite)

    def plot(self) -> None:
        """Build figures into ``self.result_figs`` or display. Override in subclasses."""
        pass
