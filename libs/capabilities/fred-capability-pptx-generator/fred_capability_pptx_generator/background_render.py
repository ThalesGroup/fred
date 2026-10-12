# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Procedural pattern backgrounds for `BackgroundSpec.kind == "pattern"`.

Same conventions as `chart_render.py` (pure, `Figure`-based, PNG bytes out).
Fixed geometry, no randomness: the same colors always render the same pattern.
"""

from __future__ import annotations

from collections.abc import Callable

import matplotlib

matplotlib.use("Agg")  # headless: no display server in the pod

from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from fred_capability_pptx_generator._matplotlib_render import figure_to_png_bytes

_DPI = 150
# Width derives from the caller's aspect_ratio so the picture matches the
# deck's actual slide dimensions.
_HEIGHT_IN = 5.625
_DEFAULT_ASPECT_RATIO = 16 / 9


def _new_full_bleed_axes(base_color: str, aspect_ratio: float):
    """A `Figure`/`Axes` pair filled edge-to-edge with `base_color`; patterns
    draw on it in unit axes coordinates."""

    width_in = _HEIGHT_IN * aspect_ratio
    fig = Figure(figsize=(width_in, _HEIGHT_IN), dpi=_DPI)
    fig.patch.set_facecolor(base_color)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_facecolor(base_color)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")
    return fig, ax


def render_soft_circles(
    base_color: str, accent_color: str, *, aspect_ratio: float = _DEFAULT_ASPECT_RATIO
) -> bytes:
    """A handful of large, soft (semi-transparent, overlapping) circles of
    `accent_color`, anchored toward the top-right and bottom-left corners so
    the visually busiest area stays away from centrally-placed slide text."""

    fig, ax = _new_full_bleed_axes(base_color, aspect_ratio)
    accent_rgb = to_rgb(accent_color)
    # (center_x, center_y, radius, alpha) in axes-fraction coordinates.
    circles = (
        (0.90, 0.88, 0.46, 0.30),
        (1.00, 0.55, 0.26, 0.28),
        (0.06, 0.08, 0.40, 0.28),
    )
    for cx, cy, radius, alpha in circles:
        ax.add_patch(
            Circle((cx, cy), radius, facecolor=accent_rgb, alpha=alpha, linewidth=0)
        )
    return figure_to_png_bytes(fig)


def render_diagonal_bands(
    base_color: str, accent_color: str, *, aspect_ratio: float = _DEFAULT_ASPECT_RATIO
) -> bytes:
    """A few subtle, angled semi-transparent bands of `accent_color`, light
    enough for text on top to stay legible."""

    fig, ax = _new_full_bleed_axes(base_color, aspect_ratio)
    accent_rgb = to_rgb(accent_color)
    # Thick lines drawn past the axes bounds (no edge gap on wide slides) and
    # clipped to the unit square; rising alphas read as layered ribbons.
    bands = (
        (-0.35, 0.55),
        (-0.05, 0.85),
        (0.25, 1.15),
    )
    for offset, alpha in zip(bands, (0.10, 0.16, 0.22)):
        start, end = offset
        ax.plot(
            [start - 0.5, end + 0.5],
            [-0.5, 1.5],
            color=accent_rgb,
            alpha=alpha,
            linewidth=260,
            solid_capstyle="butt",
            clip_on=True,
        )
    return figure_to_png_bytes(fig)


def render_dot_grid(
    base_color: str, accent_color: str, *, aspect_ratio: float = _DEFAULT_ASPECT_RATIO
) -> bytes:
    """A low-density, muted dot grid; density adapts to `aspect_ratio` so
    spacing stays roughly square."""

    fig, ax = _new_full_bleed_axes(base_color, aspect_ratio)
    accent_rgb = to_rgb(accent_color)
    n_cols = 22
    n_rows = max(2, round(n_cols / aspect_ratio))
    xs = [(i + 0.5) / n_cols for i in range(n_cols)]
    ys = [(j + 0.5) / n_rows for j in range(n_rows)]
    dot_x = [x for _y in ys for x in xs]
    dot_y = [y for y in ys for _x in xs]
    ax.scatter(dot_x, dot_y, s=7.0, color=accent_rgb, alpha=0.35, linewidths=0)
    return figure_to_png_bytes(fig)


PATTERN_RENDERERS: dict[str, Callable[..., bytes]] = {
    "soft_circles": render_soft_circles,
    "diagonal_bands": render_diagonal_bands,
    "dot_grid": render_dot_grid,
}
