# author: yannik fontana, creation date: 18.05.2026
"""
Oneway relock helper routines (uses DAC and OPX).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from toolbox.software.common_mathfuns import lorentzian

logger = logging.getLogger(__name__)


def oneway_relock_fit(
    opx: Any,
    dac: Any,
    z_targets: np.ndarray,
    t: float,
    *,
    AOMg1: float | None = 1.0,
    AOMr1: float | None = None,
    AOMr2: float | None = None,
    EOMr2: float | None = None,
    apd: int | None = None,
) -> tuple[np.ndarray, float]:
    """
    Sweep cavity z voltage, collect fluorescence counts, and fit a Lorentzian.

    At each voltage step the cavity is ramped on the DAC, then selected laser(s)
    are driven for duration ``t`` while APD counts are accumulated via
    ``opx.quasicw_counts`` (quasi-CW: count during optical drive, chunked on OPX).

    Parameters
    ----------
    opx:
        OPX driver (``Opx``) with open QM and ``quasicw_counts``.
    dac:
        DAC driver with ``dac.voltage.smooth_ramp``.
    z_targets:
        1D array of target z voltages (V).
    t:
        Optical drive and counting duration (s). Passed to ``quasicw_counts``
        (integer ns, divisible by 4 ns, minimum 16 ns).
    AOMg1, AOMr1, AOMr2, EOMr2:
        Relative amplitudes for each element; ``None`` skips that channel.
        Default: green on at full scale (``AOMg1=1.0``).
    apd:
        ``None`` sum both APDs; ``1`` or ``2`` for a single analog input.

    Returns
    -------
    counts:
        1D array of total photon counts at each ``z_targets`` point.
    center_v:
        Fitted Lorentzian center (V), or voltage at max signal if the fit fails.
    """
    try:
        _ = opx.qm
    except Exception as exc:
        logger.error("oneway_relock_fit: OPX quantum machine is not open: %s", exc)
        raise RuntimeError("OPX quantum machine is not open.") from exc

    z = np.asarray(z_targets, dtype=float).reshape(-1)
    if z.size == 0:
        logger.error("oneway_relock_fit: z_targets is empty.")
        raise ValueError("z_targets must be a non-empty 1D array.")

    counts = np.zeros(z.size, dtype=float)
    for i, v in enumerate(z):
        dac.voltage.smooth_ramp("1", float(v))
        counts[i] = float(
            opx.quasicw_counts(
                t,
                AOMg1=AOMg1,
                AOMr1=AOMr1,
                AOMr2=AOMr2,
                EOMr2=EOMr2,
                apd=apd,
            )
        )

    baseline_guess = 200.0 * t
    amplitude_guess = float(np.max(counts - baseline_guess))
    position_guess = float(z[int(np.argmax(counts))])
    fwhm_guess = 1e-3

    p0 = np.array([position_guess, fwhm_guess, amplitude_guess, baseline_guess], dtype=float)

    try:
        popt, _ = curve_fit(
            lorentzian,
            z,
            counts,
            p0=p0,
            maxfev=10000,
        )
        center_v = float(popt[0])
    except Exception as exc:
        center_v = position_guess
        logger.warning(
            "oneway_relock_fit: Lorentzian fit failed, fallback to max signal position %.6f V: %s",
            center_v,
            exc,
        )

    return counts, center_v
