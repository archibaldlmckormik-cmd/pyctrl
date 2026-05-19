# author: yannik fontana, creation date: 19.05.2026
"""
Common mathematical functions and distributions.
"""

from __future__ import annotations

import numpy as np

_LN2 = np.log(2.0)


def lorentzian(
    x: np.ndarray,
    center: float = 0.0,
    fwhm: float = 1.0,
    amplitude: float = 1.0,
    baseline: float = 0.0,
) -> np.ndarray:
    """
    Lorentzian peak on a constant baseline.

    ``baseline + amplitude / (1 + 4 * ((x - center) / fwhm) ** 2)``

    ``fwhm`` is the full width at half maximum of the peak above ``baseline``.
    """
    x = np.asarray(x, dtype=float)
    return baseline + amplitude / (1.0 + 4.0 * ((x - center) / fwhm) ** 2)


def gaussian(
    x: np.ndarray,
    center: float = 0.0,
    fwhm: float = 1.0,
    amplitude: float = 1.0,
    baseline: float = 0.0,
) -> np.ndarray:
    """
    Gaussian peak on a constant baseline, parameterized by FWHM.

    ``baseline + amplitude * exp(-4 * ln(2) * ((x - center) / fwhm) ** 2)``
    """
    x = np.asarray(x, dtype=float)
    return baseline + amplitude * np.exp(-4.0 * _LN2 * ((x - center) / fwhm) ** 2)


def fano(
    x: np.ndarray,
    center: float = 0.0,
    fwhm: float = 1.0,
    amplitude: float = 1.0,
    baseline: float = 0.0,
    q: float = 1.0,
) -> np.ndarray:
    """
    Fano line shape on a constant baseline.

    ``baseline + amplitude * (q + eps) ** 2 / (1 + eps ** 2)``

    with ``eps = 2 * (x - center) / fwhm``. The width uses the same reduced
    coordinate as :func:`lorentzian`. ``q`` controls asymmetry (``q=0`` gives a
    dip at ``center``; large ``|q|`` approaches a symmetric peak).
    """
    x = np.asarray(x, dtype=float)
    eps = 2.0 * (x - center) / fwhm
    return baseline + amplitude * (q + eps) ** 2 / (1.0 + eps**2)
