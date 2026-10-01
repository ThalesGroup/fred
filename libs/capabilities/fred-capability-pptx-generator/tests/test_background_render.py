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

"""Each procedural pattern-background recipe must produce a valid,
correctly-sized PNG (RFC §12.2c, §12.4) — `deck_builder.py` embeds these
directly as a full-bleed picture, so a malformed or mis-sized image would
break every pattern background kind."""

from __future__ import annotations

import io

import pytest
from fred_capability_pptx_generator import background_render
from PIL import Image

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _assert_valid_png(data: bytes, *, expected_aspect_ratio: float) -> None:
    assert data[:8] == _PNG_MAGIC
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    assert width > 0 and height > 0
    assert abs((width / height) - expected_aspect_ratio) < 0.02


@pytest.mark.parametrize(
    "render_fn",
    [
        background_render.render_soft_circles,
        background_render.render_diagonal_bands,
        background_render.render_dot_grid,
    ],
)
@pytest.mark.parametrize(
    ("base_color", "accent_color"),
    [("#101010", "#FF8800"), ("#FFFFFF", "#1565C0")],
)
def test_pattern_renders_valid_png_at_default_aspect_ratio(
    render_fn, base_color, accent_color
):
    data = render_fn(base_color, accent_color)
    _assert_valid_png(data, expected_aspect_ratio=16 / 9)


@pytest.mark.parametrize(
    "render_fn",
    [
        background_render.render_soft_circles,
        background_render.render_diagonal_bands,
        background_render.render_dot_grid,
    ],
)
def test_pattern_matches_requested_aspect_ratio(render_fn):
    # A 4:3 default presentation (python-pptx's own blank template) must not
    # get a 16:9-shaped pattern stretched/cropped onto it.
    data = render_fn("#202020", "#43A047", aspect_ratio=4 / 3)
    _assert_valid_png(data, expected_aspect_ratio=4 / 3)


@pytest.mark.parametrize(
    "render_fn",
    [
        background_render.render_soft_circles,
        background_render.render_diagonal_bands,
        background_render.render_dot_grid,
    ],
)
def test_pattern_is_deterministic_for_the_same_colors(render_fn):
    first = render_fn("#101010", "#FF8800")
    second = render_fn("#101010", "#FF8800")
    assert first == second


def test_pattern_renderers_catalog_covers_every_literal_pattern_name():
    assert set(background_render.PATTERN_RENDERERS) == {
        "soft_circles",
        "diagonal_bands",
        "dot_grid",
    }
