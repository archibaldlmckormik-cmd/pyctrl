# author: yannik fontana, creation date: 19.05.2026
"""
Interactive 2D slice viewer for a 3D array (index axes only).
"""

from __future__ import annotations

import numpy as np
import plotly.express as px
import plotly.graph_objects as go

_AXIS_NAMES = ("y", "x", "z")
_COLORSCALE = px.colors.sequential.ice


def cuboid_slice_view(volume: np.ndarray, axis: int) -> go.Figure:
    """
    Build an interactive heatmap of 2D slices through a 3D volume.

    The volume is indexed as ``volume[y, x, z]`` (axis 0 = y, 1 = x, 2 = z).
    Slices are taken perpendicular to ``axis``; the other two axes are shown as
    pixel indices (0, 1, …). In-plane orientation:

    - ``axis=0`` (y): horizontal = x, vertical = z
    - ``axis=1`` (x): horizontal = z, vertical = y
    - ``axis=2`` (z): horizontal = x, vertical = y

    Interaction uses a Plotly slider (browser or HTML); no Qt/Tk required.
    Color limits are fixed to the min and max of the full volume (same for every slice).
    Colormap is Plotly Express ``ice`` (``px.colors.sequential.ice``).

    Parameters
    ----------
    volume:
        Three-dimensional array of real values, shape ``(ny, nx, nz)``.
    axis:
        Which axis the slider moves along: ``0`` (y), ``1`` (x), or ``2`` (z).

    Returns
    -------
    plotly.graph_objects.Figure
        Figure with a slider; call ``fig.show()`` or pass to HTML export.

    Example
    -------
    >>> import numpy as np
    >>> from toolbox.software.cuboid_slice_view import cuboid_slice_view
    >>> vol = np.random.rand(4, 5, 6)
    >>> fig = cuboid_slice_view(vol, axis=2)  # slide along z, view x–y planes
    >>> fig.show()
    """
    data = np.asarray(volume, dtype=float)
    if data.ndim != 3:
        raise ValueError(f"volume must be 3D, got ndim={data.ndim}")

    axis = int(axis)
    if axis not in (0, 1, 2):
        raise ValueError("axis must be 0 (y), 1 (x), or 2 (z)")

    ny, nx, nz = data.shape
    n_slices = (ny, nx, nz)[axis]
    if n_slices == 0:
        raise ValueError("volume must have a positive length along every axis")

    h_name, v_name, x_len, y_len = _plane_axes(axis, ny, nx, nz)
    x_idx = np.arange(x_len)
    y_idx = np.arange(y_len)
    slider_name = _AXIS_NAMES[axis]

    zmin = float(np.nanmin(data))
    zmax = float(np.nanmax(data))
    if zmin == zmax:
        zmax = zmin + 1.0

    heatmap_kw = dict(
        x=x_idx,
        y=y_idx,
        zauto=False,
        zmin=zmin,
        zmax=zmax,
        coloraxis="coloraxis",
    )

    def slice_2d(k: int) -> np.ndarray:
        if axis == 0:
            plane = data[k, :, :]
        elif axis == 1:
            plane = data[:, k, :]
        else:
            plane = data[:, :, k]
        return _plane_for_heatmap(plane, axis)

    fig = go.Figure(data=go.Heatmap(z=slice_2d(0), **heatmap_kw))

    fig.frames = [
        go.Frame(
            name=str(k),
            data=go.Heatmap(z=slice_2d(k), **heatmap_kw),
        )
        for k in range(n_slices)
    ]

    fig.update_layout(
        title=f"Slice view (slider: {slider_name}) — plane {h_name} × {v_name}",
        xaxis_title=f"{h_name} index",
        yaxis_title=f"{v_name} index",
        yaxis=dict(autorange="reversed"),
        coloraxis=dict(
            colorscale=_COLORSCALE,
            cmin=zmin,
            cmax=zmax,
            cauto=False,
            colorbar=dict(title="value"),
        ),
        sliders=[
            dict(
                active=0,
                pad=dict(t=30),
                currentvalue=dict(prefix=f"{slider_name} index: "),
                steps=[
                    dict(
                        label=str(k),
                        method="animate",
                        args=[
                            [str(k)],
                            dict(
                                frame=dict(duration=0, redraw=True),
                                mode="immediate",
                            ),
                        ],
                    )
                    for k in range(n_slices)
                ],
            )
        ],
    )
    return fig


def _plane_axes(axis: int, ny: int, nx: int, nz: int) -> tuple[str, str, int, int]:
    """Return horizontal axis name, vertical axis name, and heatmap x/y lengths."""
    if axis == 0:
        return "x", "z", nx, nz
    if axis == 1:
        return "z", "y", nz, ny
    return "x", "y", nx, ny


def _plane_for_heatmap(plane: np.ndarray, axis: int) -> np.ndarray:
    """
    Orient a 2D slice as plotly Heatmap ``z[y, x]`` with the horizontal axis along columns.
    """
    if axis == 0:
        return plane.T
    return plane
