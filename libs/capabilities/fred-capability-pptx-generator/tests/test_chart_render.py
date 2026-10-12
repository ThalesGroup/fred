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

"""Each matplotlib fallback recipe must produce valid, non-empty PNG bytes:
the deck builder embeds them via `add_picture`, so a bad image breaks that kind."""

from __future__ import annotations

import io

import pytest
from fred_capability_pptx_generator import chart_render
from fred_capability_pptx_generator.models import GanttTask
from PIL import Image

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _assert_valid_png(data: bytes) -> None:
    assert data[:8] == _PNG_MAGIC
    with Image.open(io.BytesIO(data)) as image:
        image.verify()


def test_render_heatmap_produces_valid_png():
    data = chart_render.render_heatmap(
        ["Row A", "Row B"],
        ["Col 1", "Col 2", "Col 3"],
        [[1, 2, 3], [4, 5, 6]],
        title="Heat",
    )
    _assert_valid_png(data)


def test_render_heatmap_rejects_empty_input():
    with pytest.raises(ValueError):
        chart_render.render_heatmap([], [], [])


def test_render_heatmap_rejects_row_count_mismatch():
    # 2 row_labels but only 1 matrix row.
    with pytest.raises(ValueError, match="one row per series"):
        chart_render.render_heatmap(["Row A", "Row B"], ["Col 1", "Col 2"], [[1, 2]])


def test_render_heatmap_rejects_row_length_mismatch():
    # A row with fewer values than there are column labels — previously
    # reached numpy's internals as a cryptic "inhomogeneous shape" error
    # instead of this clean, actionable one.
    with pytest.raises(ValueError, match="match the number of"):
        chart_render.render_heatmap(
            ["Row A", "Row B"], ["Col 1", "Col 2", "Col 3"], [[1, 2, 3], [4, 5]]
        )


def test_render_waterfall_produces_valid_png():
    data = chart_render.render_waterfall(
        ["Start", "Q1", "Q2", "End"], [100, 20, -10, 0], title="Waterfall"
    )
    _assert_valid_png(data)


def test_render_waterfall_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        chart_render.render_waterfall(["A", "B"], [1])


def test_render_funnel_produces_valid_png():
    data = chart_render.render_funnel(
        ["Visits", "Signups", "Purchases"], [1000, 400, 120]
    )
    _assert_valid_png(data)


def test_render_funnel_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        chart_render.render_funnel(["A"], [])


def test_render_funnel_rejects_negative_values():
    # A negative funnel value previously produced a blank/near-empty chart
    # (xlim math breaks down) instead of an actionable error.
    with pytest.raises(ValueError, match="non-negative"):
        chart_render.render_funnel(["Visits", "Signups"], [1000, -5])


def test_render_gantt_produces_valid_png():
    tasks = [
        GanttTask(name="Design", start=0, duration=3),
        GanttTask(name="Build", start=3, duration=5),
    ]
    data = chart_render.render_gantt(tasks, title="Plan")
    _assert_valid_png(data)


def test_render_gantt_rejects_empty_tasks():
    with pytest.raises(ValueError):
        chart_render.render_gantt([])
