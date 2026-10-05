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

"""The box model composed slides are laid out with (design.md D21).

The engine only decides where boxes go. So the tests below are about that:
that a container hugs what it holds, that `fill` shares what is left, that
nesting works to any depth, that a parent is placed before the children drawn
on it, and that every gap still comes from the template's own scale.
"""

from __future__ import annotations

import pytest
from fred_capability_ppt_filler.builder import layout as L
from fred_capability_ppt_filler.builder.design_system import Box
from fred_capability_ppt_filler.builder.theme import default_theme


@pytest.fixture(scope="module")
def system():
    _, inventory = default_theme()
    return inventory.design_system


BAND = Box(x=100, y=200, w=800, h=600)


def _text(name: str, role: str = "body", lines: int = 1, **fields) -> L.Node:
    return L.Node(
        kind="text",
        role=role,
        slot=name,
        name=name,
        lines=lines,
        height="hug",
        **fields,
    )


def _by_name(placed):
    return {item.node.name: item.box for item in placed}


# -- the layer boundary holds (D8) --------------------------------------------


def test_the_engine_never_imports_the_output_format():
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "fred_capability_ppt_filler/builder/layout.py"
    ).read_text()

    assert "import pptx" not in source and "from pptx" not in source


# -- hugging and filling -------------------------------------------------------


def test_a_column_hugs_the_children_it_holds(system):
    root = L.stack(_text("a"), _text("b"), gap=1, height="hug")

    placed = L.arrange(system, root, BAND)
    boxes = _by_name(placed)

    total = boxes["a"].h + boxes["b"].h + system.gap_y(1)
    assert L.natural(system, root, avail_w=BAND.w)[1] == total
    assert boxes["a"].y == BAND.y
    assert boxes["b"].y == BAND.y + boxes["a"].h + system.gap_y(1)


def test_a_filling_child_takes_what_is_left(system):
    root = L.stack(
        _text("fixed"),
        L.Node(kind="card", name="rest", height="fill"),
        gap=1,
    )

    boxes = _by_name(L.arrange(system, root, BAND))

    assert boxes["rest"].h == BAND.h - boxes["fixed"].h - system.gap_y(1)


def test_two_filling_children_share_by_their_weight(system):
    root = L.stack(
        L.Node(kind="card", name="one", height="fill", grow=1),
        L.Node(kind="card", name="two", height="fill", grow=3),
    )

    boxes = _by_name(L.arrange(system, root, BAND))

    assert boxes["two"].h == pytest.approx(3 * boxes["one"].h, abs=2)
    assert boxes["one"].h + boxes["two"].h == pytest.approx(BAND.h, abs=2)


def test_a_row_lays_its_children_left_to_right_without_overlapping(system):
    root = L.stack(
        *[L.Node(kind="card", name=f"c{i}", height="fill") for i in range(4)],
        direction="row",
        gap=2,
    )

    boxes = [_by_name(L.arrange(system, root, BAND))[f"c{i}"] for i in range(4)]

    for left, right in zip(boxes, boxes[1:]):
        assert left.x + left.w <= right.x
    assert boxes[0].x == BAND.x
    assert boxes[-1].x + boxes[-1].w <= BAND.x + BAND.w + 1


# -- gaps and padding come from the scale, and nowhere else -------------------


def test_no_gap_means_no_gap_and_zero_means_the_tightest_step(system):
    """`padding=0` reads as "none" and is not: it is the scale's first rung.
    The API says so by making None the empty one."""
    none = L.stack(_text("a"), padding=None)
    tight = L.stack(_text("b"), padding=0)

    assert _by_name(L.arrange(system, none, BAND))["a"].x == BAND.x
    assert _by_name(L.arrange(system, tight, BAND))["b"].x == BAND.x + system.gap_x(0)


@pytest.mark.parametrize("step", [0, 1, 2, 3])
def test_every_gap_is_a_step_of_the_template_scale(system, step):
    root = L.stack(_text("a"), _text("b"), gap=step)

    boxes = _by_name(L.arrange(system, root, BAND))
    measured = boxes["b"].y - (boxes["a"].y + boxes["a"].h)

    assert measured == system.gap_y(step)


def test_padding_is_optically_equal_on_both_axes(system):
    """A gap of one step looks the same across and down, which on a 16:9 slide
    means different per-mille values."""
    root = L.stack(_text("a"), padding=2)

    box = _by_name(L.arrange(system, root, BAND))["a"]

    assert box.x - BAND.x == system.gap_x(2)
    assert box.y - BAND.y == system.gap_y(2)
    assert system.gap_x(2) != system.gap_y(2)


# -- nesting, which is the point (D21) ----------------------------------------


def test_a_panel_of_cards_of_rows_resolves_to_absolute_boxes(system):
    """Three levels deep: the shape every real corporate slide turns out to be."""
    card = lambda i: L.stack(  # noqa: E731 - reads as the tree it builds
        _text(f"h{i}", role="heading"),
        _text(f"t{i}", lines=3),
        padding=1,
        gap=0,
        surface="surface-muted",
        name=f"card{i}",
        height="hug",
    )
    root = L.stack(
        _text("title", role="title"),
        L.stack(card(0), card(1), card(2), direction="row", gap=2, height="hug"),
        gap=3,
    )

    placed = L.resolve(system, root, BAND)
    boxes = _by_name(placed)

    assert {"title", "card0", "h0", "t0", "card2", "t2"} <= set(boxes)
    for index in range(3):
        card_box, heading = boxes[f"card{index}"], boxes[f"h{index}"]
        assert card_box.x <= heading.x
        assert card_box.y <= heading.y
        assert heading.x + heading.w <= card_box.x + card_box.w
        assert heading.y + heading.h <= card_box.y + card_box.h


def test_a_container_is_placed_before_what_is_drawn_on_it(system):
    """Creation order IS z-order: a card after its text hides the text."""
    root = L.stack(
        L.stack(_text("h0"), padding=1, surface="surface-muted", name="card0"),
        gap=1,
    )

    order = [item.node.name for item in L.resolve(system, root, BAND)]

    assert order.index("card0") < order.index("h0")


def test_a_transparent_container_draws_nothing(system):
    """Only a stack that paints a surface reaches the slide; the rest is scaffolding."""
    root = L.stack(L.stack(_text("a"), name="invisible"), name="outer")

    names = {item.node.name for item in L.resolve(system, root, BAND)}

    assert names == {"a"}


# -- a card hugs what it holds (D20) ------------------------------------------


def test_a_card_hugs_its_content_instead_of_filling_the_band(system):
    card = L.stack(
        _text("h", role="heading"),
        _text("t", lines=2),
        padding=1,
        gap=0,
        surface="surface-muted",
        name="card",
        height="hug",
    )
    root = L.stack(card, gap=1)

    boxes = _by_name(L.resolve(system, root, BAND))

    assert boxes["card"].h < BAND.h * 0.8
    assert boxes["card"].h >= boxes["t"].y + boxes["t"].h - boxes["card"].y


def test_more_lines_asked_for_means_a_taller_card(system):
    def card(lines: int) -> Box:
        node = L.stack(
            _text("t", lines=lines),
            padding=1,
            surface="surface-muted",
            name="card",
            height="hug",
        )
        return _by_name(L.resolve(system, L.stack(node), BAND))["card"]

    assert card(1).h < card(4).h


# -- cross-axis alignment ------------------------------------------------------


def test_a_centred_child_sits_in_the_middle_of_its_track(system):
    root = L.stack(
        L.Node(kind="chip", name="pill", height="hug", align="center", fixed_h=60),
        direction="row",
    )

    box = _by_name(L.arrange(system, root, BAND))["pill"]

    assert box.h == 60
    assert box.y > BAND.y
    assert abs((box.y - BAND.y) - (BAND.y + BAND.h - (box.y + box.h))) <= 2
