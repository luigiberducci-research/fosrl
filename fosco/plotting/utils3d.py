from typing import Callable

import numpy as np

import matplotlib as mpl

import plotly.graph_objects as go
from matplotlib import cm
from plotly.graph_objs import Surface

from fosco.common.domains import Set
from fosco.plotting.constants import FigureType


def plot_surface(
    func: Callable[[np.ndarray], np.ndarray],
    xrange: tuple[float, float],
    yrange: tuple[float, float],
    levels: list[float] = None,
    label: str = "",
    bins: int = 100,
    level_color: str = "black",
    opacity: float = 1.0,
    fig: FigureType = None,
):
    """
    Plot the surface of the function over 2d space.
    """
    fig = fig or go.Figure()
    levels = levels or []

    x = np.linspace(xrange[0], xrange[1], bins)
    y = np.linspace(yrange[0], yrange[1], bins)
    X, Y = np.meshgrid(x, y)
    Xflat = X.reshape(-1, 1)
    Yflat = Y.reshape(-1, 1)
    inputs = np.hstack([Xflat, Yflat])
    z = func(inputs).reshape(bins, bins)

    if isinstance(fig, mpl.figure.Figure):
        fig = plot_surface3d_mpl(X, Y, z, fig, label, color=None, opacity=opacity)
        fig.gca().contour(X, Y, z, levels=levels, colors=level_color, linewidths=2)
    elif isinstance(fig, go.Figure):
        fig = plot_surface3d_plotly(X, Y, z, fig, label, color=None, opacity=opacity)

        for level in levels:
            small_sz = 0.01
            fig.update_traces(
                contours_z=dict(
                    show=True,
                    color=level_color,
                    highlightcolor="limegreen",
                    project_z=False,
                    start=level,
                    end=level + small_sz,
                    size=small_sz,
                )
            )

    return fig


def plot_scattered_points3d(
    domain: Set,
    fig: FigureType,
    color: str,
    opacity: float = 1.0,
    dim_select: tuple[int, int] = None,
    label: str = "",
    z_start: float = 0.0,
) -> FigureType:
    data = domain.generate_data(500)
    dim_select = dim_select or (0, 1)

    X = data[:, dim_select[0]]
    Y = data[:, dim_select[1]]
    Z = z_start * np.ones_like(X)

    if isinstance(fig, mpl.figure.Figure):
        fig = scatter_points3d_mpl(
            xs=X, ys=Y, zs=Z, fig=fig, label=label, color=color, opacity=opacity
        )
    elif isinstance(fig, go.Figure):
        fig = scatter_points3d_plotly(
            xs=X, ys=Y, zs=Z, fig=fig, label=label, color=color, opacity=opacity
        )
    else:
        raise NotImplementedError(
            f"plot_scattered_points3d not implemented for {type(fig)}"
        )
    return fig


def plot_surface3d_plotly(
    xs, ys, zs, fig, label="", color=None, opacity=None
) -> FigureType:
    if color:
        color = [[0.0, color], [1.0, color]]

    surface = Surface(
        x=xs, y=ys, z=zs, colorscale=color, showscale=False, name=label, opacity=opacity
    )
    fig.add_trace(surface)
    return fig


def plot_surface3d_mpl(
    xs, ys, zs, fig, label="", color=None, opacity=None
) -> FigureType:
    fig.gca().plot_surface(
        xs, ys, zs, color=color, label=label, alpha=opacity, cmap=cm.plasma
    )
    return fig


def scatter_points3d_plotly(
    xs, ys, zs, fig, label="", color=None, opacity=1.0
) -> FigureType:
    fig.add_scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="markers",
        marker=dict(size=1, color=color, opacity=opacity),
        name=label,
    )
    return fig


def scatter_points3d_mpl(
    xs, ys, zs, fig, label="", color=None, opacity=1.0
) -> FigureType:
    fig.gca().scatter(xs, ys, zs, color=color, label=label, alpha=opacity)
    return fig


if __name__ == "__main__":

    def func(x):
        assert len(x.shape) == 2 and x.shape[1] == 2, "x must be a batch of 2d points"
        return np.sin(x[:, 0])  # + np.cos(x[:, 1])

    fig = plot_surface(func, (-10, 10), (-5, 5), levels=[0], label="test")

    fig.show()
