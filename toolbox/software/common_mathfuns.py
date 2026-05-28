# author: yannik fontana, creation date: 19.05.2026
"""
Common mathematical functions and distributions.
"""

from __future__ import annotations

from collections.abc import Sequence

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


def gaussian2d(
    x: np.ndarray,
    y: np.ndarray,
    center: float | Sequence[float] | np.ndarray = (0.0, 0.0),
    fwhm: float | Sequence[float] | np.ndarray = (1.0, 1.0),
    amplitude: float = 1.0,
    baseline: float = 0.0,
    angle: float = 0.0,
) -> np.ndarray:
    """
    2D Gaussian on a constant baseline, parameterized by FWHM along principal axes.

    At ``angle = 0``, the principal axes align with x and y: ``fwhm[0]`` is the
    FWHM along x, ``fwhm[1]`` along y (vertical). Rotating the ellipse uses a
    coordinate transform into the principal frame:

    ``baseline + amplitude * exp(-4 * ln(2) * ((u / fwhm_u)**2 + (v / fwhm_v)**2))``

    with ``(u, v)`` obtained by rotating ``(x - cx, y - cy)``. **Negative**
    ``angle`` (radians) rotates the principal axes counterclockwise in the lab frame.

    Parameters
    ----------
    x, y
        Coordinate arrays. If both are 1D with lengths M and N, they are combined
        with ``x[:, None]`` and ``y[None, :]`` (output shape ``(M, N)``). If they
        already share a grid shape, they are used as-is.
    center
        Peak center ``(cx, cy)``.
    fwhm
        FWHM along principal u and v axes at ``angle = 0``: ``(fwhm_u, fwhm_v)``.
    amplitude, baseline
        Peak height above baseline and constant offset (scalars).
    angle
        Rotation of principal axes w.r.t. x/y, in radians. Negative = CCW.

    Returns
    -------
    np.ndarray
        Evaluated surface, broadcast to the grid implied by ``x`` and ``y``.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    center_arr = np.asarray(center, dtype=float).ravel()
    if center_arr.size != 2:
        raise ValueError(f"center must have exactly 2 elements, got {center_arr.size}")
    cx, cy = float(center_arr[0]), float(center_arr[1])
    fwhm_arr = np.asarray(fwhm, dtype=float).ravel()
    if fwhm_arr.size != 2:
        raise ValueError(f"fwhm must have exactly 2 elements, got {fwhm_arr.size}")
    fwhm_u, fwhm_v = float(fwhm_arr[0]), float(fwhm_arr[1])

    if x.ndim == y.ndim == 1 and x.shape != y.shape:
        x_grid = x[:, np.newaxis]
        y_grid = y[np.newaxis, :]
    else:
        x_grid = x
        y_grid = y

    xp = x_grid - cx
    yp = y_grid - cy
    # Negative angle = CCW: use standard CCW rotation with theta = -angle.
    theta = -float(angle)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    u = cos_t * xp + sin_t * yp
    v = -sin_t * xp + cos_t * yp
    quad = (u / fwhm_u) ** 2 + (v / fwhm_v) ** 2
    return baseline + amplitude * np.exp(-4.0 * _LN2 * quad)


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


def addnoise(
    array: np.ndarray,
    *,
    relative_scale: bool = True,
    std_dev: float = 0.1,
) -> np.ndarray:
    """
    Add Gaussian noise to ``array`` and return a new float array of the same shape.

    Noise is drawn i.i.d. from ``Normal(0, sigma)`` with:

    - ``relative_scale=False``: ``sigma = abs(std_dev)``
    - ``relative_scale=True``: ``sigma = abs(std_dev) * (max(array) - min(array))``

    If the span is zero (constant input) and ``relative_scale=True``, ``sigma`` is 0
    and the returned values equal the input (up to dtype conversion).
    """
    arr = np.asarray(array, dtype=float)
    sigma = abs(std_dev)
    if relative_scale:
        sigma *= arr.max() - arr.min()
    if sigma == 0.0:
        return arr.copy()
    return arr + np.random.normal(0.0, sigma, size=arr.shape)
