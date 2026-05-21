# author: yannik fontana, creation date: 18.05.2026
"""
Oneway relock helper routines (uses DAC, OPX, and shutter).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from toolbox.software.common_mathfuns import lorentzian

logger = logging.getLogger(__name__)


def oneway_relock(
    opx: Any,
    dac: Any,
    shutter: Any,
    z_targets: np.ndarray,
    duration_s: float,
    *,
    AOMg1: float | None = 1.0,
    AOMr1: float | None = None,
    AOMr2: float | None = None,
    EOMr2: float | None = None,
    apd: int | None = None,
) -> np.ndarray:
    """
    Sweep cavity z voltage and collect fluorescence counts (no peak analysis).

    At each voltage step the cavity is ramped on the DAC, then selected laser(s)
    are driven for ``duration_s`` while APD counts are accumulated via
    ``opx.quasicw_counts`` (quasi-CW: count during optical drive, chunked on OPX).
    The shutter is opened for the sweep and closed afterward; DAC channel 1 returns
    to the first sweep voltage.

    Parameters
    ----------
    opx, dac, shutter:
        Hardware drivers (OPX must have open QM).
    z_targets:
        1D array of target z voltages (V).
    duration_s:
        Optical drive and counting duration (s). Validated with ``opx.seconds_to_cycles``.
    AOMg1, AOMr1, AOMr2, EOMr2:
        Relative amplitudes for each element; ``None`` skips that channel.
    apd:
        ``None`` sum both APDs; ``1`` or ``2`` for a single analog input.

    Returns
    -------
    np.ndarray
        Photon counts at each ``z_targets`` point.
    """
    try:
        _ = opx.qm
    except Exception as exc:
        logger.error("oneway_relock: OPX quantum machine is not open: %s", exc)
        raise RuntimeError("OPX quantum machine is not open.") from exc

    z = np.asarray(z_targets, dtype=float).reshape(-1)
    if z.size == 0:
        logger.error("oneway_relock: z_targets is empty.")
        raise ValueError("z_targets must be a non-empty 1D array.")

    opx.seconds_to_cycles(duration_s, name="duration")

    counts = np.zeros(z.size, dtype=float)
    shutter.open = True
    try:
        for i, v in enumerate(z):
            dac.voltage.smooth_ramp("1", float(v))
            counts[i] = float(
                opx.quasicw_counts(
                    duration_s,
                    AOMg1=AOMg1,
                    AOMr1=AOMr1,
                    AOMr2=AOMr2,
                    EOMr2=EOMr2,
                    apd=apd,
                )
            )
    finally:
        shutter.open = False
        dac.voltage.smooth_ramp("1", float(z[0]))

    return counts


def oneway_relock_fit(
    opx: Any,
    dac: Any,
    shutter: Any,
    z_targets: np.ndarray,
    duration_s: float,
    *,
    AOMg1: float | None = 1.0,
    AOMr1: float | None = None,
    AOMr2: float | None = None,
    EOMr2: float | None = None,
    apd: int | None = None,
) -> tuple[np.ndarray, float]:
    """
    One-way relock scan with Lorentzian fit for the resonance center voltage.

    Returns
    -------
    counts:
        1D array of photon counts at each ``z_targets`` point.
    center_v:
        Fitted Lorentzian center (V), or voltage at max signal if the fit fails.
    """
    # aquire the signal
    z = np.asarray(z_targets, dtype=float).reshape(-1)
    counts = oneway_relock(
        opx,
        dac,
        shutter,
        z,
        duration_s,
        AOMg1=AOMg1,
        AOMr1=AOMr1,
        AOMr2=AOMr2,
        EOMr2=EOMr2,
        apd=apd,
    )

    # fit the signal
    baseline_guess = 200.0 * duration_s
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


def oneway_relock_mass(
    opx: Any,
    dac: Any,
    shutter: Any,
    z_targets: np.ndarray,
    duration_s: float,
    *,
    AOMg1: float | None = 1.0,
    AOMr1: float | None = None,
    AOMr2: float | None = None,
    EOMr2: float | None = None,
    apd: int | None = None,
) -> tuple[np.ndarray, float]:
    """
    One-way relock scan with center-of-mass estimate of the peak voltage.

    ``center_v = sum(z * counts) / sum(counts)``. If the total counts are zero,
    falls back to the voltage at maximum signal.

    Returns
    -------
    counts:
        1D array of photon counts at each ``z_targets`` point.
    center_v:
        Center-of-mass voltage (V).
    """
    # aquire the signal
    z = np.asarray(z_targets, dtype=float).reshape(-1)
    counts = oneway_relock(
        opx,
        dac,
        shutter,
        z,
        duration_s,
        AOMg1=AOMg1,
        AOMr1=AOMr1,
        AOMr2=AOMr2,
        EOMr2=EOMr2,
        apd=apd,
    )

    # calculate the center-of-mass
    total = float(np.sum(counts))
    if total <= 0:
        center_v = float(z[int(np.argmax(counts))])
        logger.warning(
            "oneway_relock_mass: zero total counts, fallback to max signal position %.6f V",
            center_v,
        )
    else:
        center_v = float(np.dot(z, counts) / total)

    return counts, center_v
