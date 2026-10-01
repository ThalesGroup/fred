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

"""Matplotlib fallback recipes for the chart kinds `python-pptx` cannot
express natively (RFC §4.3, §9 item 4): heatmap, waterfall, funnel, Gantt.

Each function is a pure, synchronous transform (typed input -> PNG bytes) —
no capability state, no I/O. `deck_builder.py` calls these from inside its
own `asyncio.to_thread` worker (one call per deck generation), so nothing
here needs its own thread-offload.

Uses the object-oriented `Figure`/`FigureCanvasAgg` API rather than
`matplotlib.pyplot`: pyplot keeps a global "current figure" registry that is
not safe to share across the bounded-but-concurrent generation workers this
capability runs (`concurrency.py`); a `Figure` built directly has no shared
state with any other in-flight render.
"""

from __future__ import annotations

from collections.abc import Sequence

import matplotlib

matplotlib.use("Agg")  # headless: no display server in the pod

from matplotlib.figure import Figure

from fred_capability_pptx_generator._matplotlib_render import figure_to_png_bytes
from fred_capability_pptx_generator.models import GanttTask

_DPI = 150
_POSITIVE_COLOR = "#2e7d32"
_NEGATIVE_COLOR = "#c62828"
_BAR_COLOR = "#1565c0"
_GANTT_COLOR = "#00695c"


def render_heatmap(
    row_labels: Sequence[str],
    col_labels: Sequence[str],
    matrix: Sequence[Sequence[float]],
    *,
    title: str | None = None,
) -> bytes:
    """One row per `row_labels` entry, one column per `col_labels` entry."""

    if not row_labels or not col_labels or not matrix:
        raise ValueError("heatmap chart needs at least one row and one column")
    if len(matrix) != len(row_labels) or any(
        len(row) != len(col_labels) for row in matrix
    ):
        raise ValueError(
            "heatmap chart needs one row per series (matching the number of "
            "row labels) and each row's 'values' to match the number of "
            "'categories' (columns)"
        )

    fig = Figure(figsize=(8, max(3.0, 0.4 * len(row_labels) + 1.5)), dpi=_DPI)
    ax = fig.add_subplot(111)
    image = ax.imshow(matrix, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=45, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
    fig.colorbar(image, ax=ax)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return figure_to_png_bytes(fig)


def render_waterfall(
    categories: Sequence[str],
    values: Sequence[float],
    *,
    title: str | None = None,
) -> bytes:
    """Offset bar chart: each bar starts where the running total left off."""

    if not categories or len(categories) != len(values):
        raise ValueError("waterfall chart needs matching categories and values")

    fig = Figure(figsize=(8, 5), dpi=_DPI)
    ax = fig.add_subplot(111)
    cumulative = 0.0
    bottoms: list[float] = []
    for value in values:
        bottoms.append(cumulative if value >= 0 else cumulative + value)
        cumulative += value
    colors = [_POSITIVE_COLOR if value >= 0 else _NEGATIVE_COLOR for value in values]
    positions = range(len(categories))
    ax.bar(positions, [abs(value) for value in values], bottom=bottoms, color=colors)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(categories, rotation=45, ha="right")
    ax.axhline(0, color="black", linewidth=0.8)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return figure_to_png_bytes(fig)


def render_funnel(
    categories: Sequence[str],
    values: Sequence[float],
    *,
    title: str | None = None,
) -> bytes:
    """Decreasing-width horizontal bars, centered — the classic funnel look."""

    if not categories or len(categories) != len(values):
        raise ValueError("funnel chart needs matching categories and values")
    if any(value < 0 for value in values):
        raise ValueError(
            "funnel chart values must be non-negative (a funnel represents "
            "a narrowing sequence of quantities, e.g. visits/signups/"
            "purchases) — use a 'waterfall' chart instead for signed deltas"
        )

    fig = Figure(figsize=(8, max(3.0, 0.6 * len(categories) + 1.5)), dpi=_DPI)
    ax = fig.add_subplot(111)
    max_value = max(values) if any(values) else 1.0
    for index, (category, value) in enumerate(zip(categories, values)):
        left = (max_value - value) / 2
        ax.barh(index, value, left=left, height=0.7, color=_BAR_COLOR)
        ax.text(
            max_value / 2,
            index,
            f"{category}: {value:g}",
            ha="center",
            va="center",
            color="white",
        )
    ax.set_yticks(range(len(categories)))
    ax.set_yticklabels(categories)
    ax.invert_yaxis()
    ax.set_xlim(0, max_value if max_value > 0 else 1.0)
    ax.get_xaxis().set_visible(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return figure_to_png_bytes(fig)


def render_gantt(
    tasks: Sequence[GanttTask],
    *,
    title: str | None = None,
) -> bytes:
    """One horizontal bar per task, `(start, start + duration)`."""

    if not tasks:
        raise ValueError("gantt chart needs at least one task")

    fig = Figure(figsize=(9, max(3.0, 0.5 * len(tasks) + 1.5)), dpi=_DPI)
    ax = fig.add_subplot(111)
    for index, task in enumerate(tasks):
        ax.broken_barh(
            [(task.start, task.duration)], (index - 0.4, 0.8), facecolors=_GANTT_COLOR
        )
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([task.name for task in tasks])
    ax.invert_yaxis()
    ax.set_xlabel("Time")
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return figure_to_png_bytes(fig)
