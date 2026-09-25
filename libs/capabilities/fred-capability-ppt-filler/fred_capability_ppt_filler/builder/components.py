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

"""The component library: the pieces a slide is composed of, and the
compositions that arrange them.

Design layer (design.md D8). This module must never import ``pptx``: it names
components, slots, tokens and grid positions, and stops there. Turning any of
that into shapes is ``render.py``'s job alone, and a test enforces the ban.

Two constraints shape every definition here. The output has no automatic
layout — nothing reflows, an overfull box overlaps its neighbour instead of
pushing it — so a composition offers fixed VARIANTS (2-up, 3-up, 4-up) chosen
by item count, never a fluid stretch (D6). And a component states its own
degenerate cases, because a proportional corner radius makes some of them
visible: a Bar shorter than it is thick distorts into a blob.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from fred_capability_ppt_filler.builder import layout as L
from fred_capability_ppt_filler.builder.design_system import (
    Box,
    DesignSystem,
    ZoneRole,
)

#: The pieces. A composition places these; nothing else is ever drawn.
PieceKind = Literal["card", "chip", "stat", "bar", "divider", "image", "icon", "text"]

#: Which token pair a piece paints itself with. `none` draws no background.
Surface = Literal["none", "surface", "surface-muted", "accent", "inverse"]


class Piece(BaseModel):
    """One drawable element of a composition, resolved to the grid.

    ``order`` is the creation order the renderer must follow, because in the
    output format creation order IS z-order: a Card must exist before the text
    that sits on it (D6).
    """

    kind: PieceKind
    box: Box
    order: int = 0
    #: Fill pair, or "none" for a piece that paints nothing.
    surface: Surface = "none"
    #: Text role: WHAT content goes here, and how the plan binds to it.
    role: Optional[ZoneRole] = None
    #: Which step of the type scale draws it, when that differs from the role.
    #: A figure beside a bar is still a `number` semantically, but drawn at
    #: label size — the role binds, the token sizes.
    type_role: Optional[ZoneRole] = None
    #: Slot this piece is filled from, e.g. "title", "item:0:heading".
    slot: str = ""
    #: Shape name, so the fill path and the review surface can find it (D6).
    name: str = ""
    #: Decorative pieces are skipped by assistive technology (D15).
    decorative: bool = False
    #: Reading order, which follows the composition rather than creation (D15).
    reading_order: int = 0
    #: Inner padding, per-mille of the slide's shorter side. Set on the text
    #: frame rather than guessed around it, or the format's own 0.1in default
    #: silently wins (D6).
    padding: int = 0
    #: Fraction of the track a Bar fills, 0..1. Ignored by every other kind.
    value: Optional[float] = None
    #: Vertical anchor inside the box.
    anchor: Literal["top", "middle", "bottom"] = "top"
    #: How an image fills its frame. Never "stretch": a distorted logo is the
    #: classic failure of a composed deck (D6).
    fit: Literal["cover", "contain"] = "cover"
    #: How much text THIS box holds. Per piece, not per slide: a number box and
    #: the paragraph beside it do not have the same room. Both numbers are
    #: needed together — given only one, the fitting re-estimates and disagrees.
    max_chars: Optional[int] = None
    max_lines: Optional[int] = None
    #: The size it is drawn at, so nothing downstream has to guess it back.
    font_pt: Optional[float] = None


class Capacity(BaseModel):
    """What a variant can carry. Exceeded, the slide splits (D14)."""

    items: int = 0
    heading_chars: int = 0
    text_chars: int = 0
    title_chars: int = 0


class Variant(BaseModel):
    """One fixed arrangement of a composition — a 3-up card row, say."""

    name: str
    items: int
    capacity: Capacity


class ComposedSlide(BaseModel):
    """A composition resolved against one design system and one item count."""

    composition: str
    variant: str
    pieces: List[Piece] = Field(default_factory=list)
    capacity: Capacity
    #: Warnings the author or the agent should see (a dropped accent, a Bar
    #: below its minimum). Never silent.
    notes: List[str] = Field(default_factory=list)


# -- geometry helpers ----------------------------------------------------------
#
# All of it per-mille, all of it from the design system. Nothing here picks a
# value of its own: that is the whole point of the layer.


def _title_band(system: DesignSystem) -> Box:
    """The title's box, anchored where the template puts its titles (D13)."""
    grid = system.grid
    anchors = system.anchors
    assert grid is not None and anchors is not None
    title = system.type_for("title")
    height = _text_height(system, title.size_pt if title else 30.0, lines=2)
    return Box(x=grid.area.x, y=anchors.title_y, w=grid.area.w, h=height)


def _content_band(system: DesignSystem) -> Box:
    """What is left below the title, down to the footer the template uses."""
    grid = system.grid
    anchors = system.anchors
    assert grid is not None and anchors is not None
    bottom = anchors.footer_y or (grid.area.y + grid.area.h)
    top = anchors.content_y
    return Box(x=grid.area.x, y=top, w=grid.area.w, h=max(40, bottom - top))


def _line_height(system: DesignSystem, size_pt: float) -> int:
    """Height in per-mille of ONE line at `size_pt`, on this slide."""
    height = system.slide_height or 1
    return max(20, round(size_pt * 12700 * 1.25 * 1000 / height))


def _text_height(system: DesignSystem, size_pt: float, *, lines: int) -> int:
    """Height in per-mille for `lines` lines.

    A multiple of the single-line height, never the rounded product: rounding
    the whole block instead lands a hair under N lines and the box silently
    holds N-1.
    """
    return _line_height(system, size_pt) * max(1, lines)


def _chars_width(system: DesignSystem, role: ZoneRole, chars: int) -> int:
    """Per-mille width that holds `chars` characters at `role`'s size.

    A box sized by hand is a box that truncates on the first template whose
    type scale is larger than the one it was eyeballed against.
    """
    token = system.type_for(role)
    size = token.size_pt if token is not None else 18.0
    emu = chars * size * 12700 * 0.6
    return max(20, round(emu * 1000 / (system.slide_width or 1)))


def _columns(system: DesignSystem, count: int) -> List[Box]:
    """`count` equal columns of the grid, inside the content band."""
    grid = system.grid
    assert grid is not None
    band = _content_band(system)
    per = max(1, grid.columns // max(1, count))
    boxes: List[Box] = []
    for index in range(count):
        x, w = grid.span(index * per, per, shorter_to_x=system.shorter_to_x)
        boxes.append(Box(x=x, y=band.y, w=w, h=band.h))
    return boxes


#: How much text a piece must hold before its size steps down the scale. A
#: card heading that fits eight characters truncates on the first real title.
_MIN_CHARS: Dict[str, int] = {
    "title": 30,
    "subtitle": 28,
    "heading": 16,
    "body": 60,
    "caption": 30,
    "number": 4,
    "label": 12,
}


def _size(system: DesignSystem, role: ZoneRole) -> float:
    """The size the template's scale gives a role, before any stepping down."""
    token = system.type_for(role)
    return token.size_pt if token is not None else 18.0


def fitting_size(
    system: DesignSystem, role: ZoneRole, *, width: int, lines: int = 1
) -> float:
    """`_fitting_size` for a box described by its width and its line budget.

    The layout engine knows a width before it knows a height — the height is
    what the chosen size decides — so it cannot pass a box.
    """
    height = _line_height(system, _size(system, role)) * max(1, lines)
    return _fitting_size(system, role, box=Box(x=0, y=0, w=width, h=height))


def _fitting_size(system: DesignSystem, role: ZoneRole, *, box: Box) -> float:
    """The largest step of the TEMPLATE's scale whose text fits `width` (D18).

    No size is invented: the ladder is the template's own scale and a piece
    takes the highest rung its box can carry. A scale read off a master's body
    style is sized for a full-width placeholder, so a third of a slide has to
    step down or truncate on every card.
    """
    start = _size(system, role)
    steps = sorted({token.size_pt for token in system.type_scale}, reverse=True)
    ladder = [size for size in steps if size <= start]
    if not ladder:
        return start
    want = _MIN_CHARS.get(str(role), 30)
    for size in ladder:
        # The whole box, not one line: a smaller size buys lines as well as
        # characters, and judging on a single line throws that away.
        lines = max(1, box.h // _line_height(system, size))
        if _capacity_for(system, box, role=role, lines=lines, size_pt=size) >= want:
            return size
    return ladder[-1]


def _capacity_for(
    system: DesignSystem,
    box: Box,
    *,
    role: ZoneRole,
    lines: int,
    size_pt: Optional[float] = None,
) -> int:
    """Roughly how many characters of `role` fit in `box` over `lines` lines.

    Deliberately an estimate: the exact fitting still happens downstream, this
    only has to be honest enough to pick a variant and to know when to split.
    """
    token = system.type_for(role)
    size = size_pt if size_pt is not None else (token.size_pt if token else 0.0)
    if not size:
        return 0
    width_emu = box.w * (system.slide_width or 1) / 1000
    # ~0.5 em per character is the usual average for latin text.
    char_emu = size * 12700 * 0.5
    per_line = max(1, int(width_emu / char_emu)) if char_emu else 1
    return per_line * max(1, lines)


# -- the pieces ----------------------------------------------------------------


def card(
    box: Box, *, order: int, name: str, surface: Surface = "surface-muted"
) -> Piece:
    """A panel behind content — painted or outlined as the template paints its
    own (D18). Decorative either way: it carries no meaning."""
    return Piece(
        kind="card",
        box=box,
        order=order,
        surface=surface,
        name=name,
        decorative=True,
    )


def text(
    box: Box,
    *,
    role: ZoneRole,
    slot: str,
    order: int,
    name: str,
    reading_order: int,
    padding: int = 0,
    anchor: Literal["top", "middle", "bottom"] = "top",
    type_role: Optional[ZoneRole] = None,
) -> Piece:
    return Piece(
        kind="text",
        box=box,
        role=role,
        type_role=type_role,
        slot=slot,
        order=order,
        name=name,
        reading_order=reading_order,
        padding=padding,
        anchor=anchor,
    )


def chip(
    box: Box, *, slot: str, order: int, name: str, reading_order: int, padding: int
) -> List[Piece]:
    """A label on a filled pill: the Card's small sibling, same two shapes."""
    return [
        Piece(
            kind="chip",
            box=box,
            order=order,
            surface="surface-muted",
            name=f"{name}-fill",
            decorative=True,
        ),
        text(
            box,
            role="label",
            slot=slot,
            order=order + 1,
            name=name,
            reading_order=reading_order,
            padding=padding,
            anchor="middle",
        ),
    ]


def divider(box: Box, *, order: int, name: str) -> Piece:
    """A rule between blocks. Carries no meaning, so it is decorative."""
    return Piece(
        kind="divider",
        box=box,
        order=order,
        surface="surface-muted",
        name=name,
        decorative=True,
    )


#: A Bar shorter than it is thick has its corner radius computed off its WIDTH
#: instead of its height, and distorts into a blob wider than it is long (D6).
BAR_MIN_RATIO = 1.0


def bar(
    box: Box, *, value: float, order: int, name: str, reading_order: int
) -> List[Piece]:
    """A track and its value: two rounded rectangles, never a chart (D10).

    Below the minimum legible length the value is drawn at that minimum, and
    below a hair of it, not at all — an honest empty track beats a blob.
    """
    fraction = max(0.0, min(1.0, value))
    pieces = [
        Piece(
            kind="bar",
            box=box,
            order=order,
            surface="surface-muted",
            name=f"{name}-track",
            decorative=True,
            value=0.0,
        )
    ]
    minimum = box.h
    filled = round(box.w * fraction)
    if filled >= minimum * BAR_MIN_RATIO or fraction > 0.01:
        pieces.append(
            Piece(
                kind="bar",
                box=Box(x=box.x, y=box.y, w=max(filled, minimum), h=box.h),
                order=order + 1,
                surface="accent",
                name=f"{name}-value",
                reading_order=reading_order,
                value=fraction,
            )
        )
    return pieces


# -- the compositions ----------------------------------------------------------


def _variants(name: str, counts: Sequence[int]) -> List[int]:
    return list(counts)


#: Every composition, with the item counts its variants cover. A composition
#: with no item count is a single-block one (statement, prose).
COMPOSITIONS: Dict[str, List[int]] = {
    "card_row": [2, 3, 4],
    "stat_band": [2, 3, 4],
    "comparison": [2],
    "steps": [3, 4, 5],
    "agenda": [4, 5, 6],
    "progress": [2, 3, 4, 5],
    "statement": [1],
    "figure_caption": [1],
    "prose": [1],
    "framed_cards": [2, 3, 4],
    "lead_and_cards": [2, 3, 4],
    "icon_cards": [2, 3, 4],
    "rich_cards": [2, 3],
}


def variant_for(composition: str, count: int) -> Optional[int]:
    """The variant that carries `count` items, or None when none can.

    Fixed variants, no stretching: a 5-item card row is not a wider 4-up, it is
    a slide that has to split.
    """
    counts = COMPOSITIONS.get(composition)
    if not counts:
        return None
    fitting = [c for c in counts if c >= count]
    return min(fitting) if fitting else None


def _title_piece(system: DesignSystem, order: int) -> Piece:
    """Every composition starts here, at the ordinate the template uses."""
    return text(
        _title_band(system),
        role="title",
        slot="title",
        order=order,
        name="composed-title",
        reading_order=0,
    )


# -- compositions, declared as trees (D21) ------------------------------------
#
# A composition is a tree over the box model, not geometry computed by hand.
# That is what makes a panel of cards expressible at all, and what makes adding
# one cheap enough that the library can grow.


def _node(
    name: str,
    role: ZoneRole,
    slot: str,
    *,
    lines: int = 1,
    type_role: Optional[ZoneRole] = None,
    **fields: object,
) -> L.Node:
    fields.setdefault("height", "hug")
    return L.Node(
        kind="text",
        name=name,
        role=role,
        type_role=type_role,
        slot=slot,
        lines=lines,
        **fields,  # type: ignore[arg-type]
    )


def _card_node(system: DesignSystem, index: int, *, lines: int) -> L.Node:
    """A panel holding a heading over its paragraph — the shape of every real
    corporate card, and now literally that tree."""
    return L.stack(
        _node(f"composed-heading-{index}", "heading", f"item:{index}:heading"),
        _node(f"composed-text-{index}", "body", f"item:{index}:text", lines=lines),
        gap=0,
        # The air the template gives its own blocks, not a rung we picked (D18).
        padding_pm=system.block_padding,
        surface="surface-muted",
        name=f"composed-card-{index}",
        height="hug",
    )


def _stat_node(system: DesignSystem, index: int) -> L.Node:
    """A figure and the label naming it, stacked the way the template stacks
    its own (D18) — and the figure read first either way, because it is the
    point of the slide."""
    number = _node(
        f"composed-stat-number-{index}",
        "number",
        f"item:{index}:number",
        reading_rank=0,
    )
    label = _node(
        f"composed-stat-label-{index}", "label", f"item:{index}:heading", reading_rank=1
    )
    stacked = (number, label) if system.shapes.figure_above_label else (label, number)
    return L.stack(*stacked, gap=0, height="hug")


def _step_row(system: DesignSystem, index: int, *, numbered: bool) -> L.Node:
    children: List[L.Node] = []
    if numbered:
        children.append(
            _node(
                f"composed-number-{index}",
                "number",
                f"item:{index}:number",
                fixed_w=_chars_width(system, "number", 3),
                width="hug",
                anchor="middle",
            )
        )
    children.append(
        _node(
            f"composed-heading-{index}",
            "heading",
            f"item:{index}:heading",
            anchor="middle",
        )
    )
    return L.stack(*children, direction="row", gap=1, height="fill")


def _progress_row(system: DesignSystem, index: int) -> L.Node:
    """A label, the Bar, and the figure the Bar illustrates (D10)."""
    thickness = max(8, round(system.spacing.step(1) * system.shorter_to_y))
    return L.stack(
        _node(
            f"composed-progress-label-{index}",
            "heading",
            f"item:{index}:heading",
            fixed_w=round(_content_band(system).w * 0.3),
            width="hug",
            anchor="middle",
        ),
        L.Node(
            kind="bar",
            name=f"composed-progress-{index}",
            fixed_h=thickness,
            align="center",
        ),
        _node(
            f"composed-progress-value-{index}",
            "number",
            f"item:{index}:number",
            type_role="label",
            fixed_w=_chars_width(system, "label", 5),
            width="hug",
            anchor="middle",
        ),
        direction="row",
        gap=1,
        height="fill",
    )


def _icon_card(system: DesignSystem, index: int, *, lines: int) -> L.Node:
    """A card led by one of the template's own icons (D22).

    The icon is a slot like any other: unfilled, the frame is removed and the
    card is the plain one. So a template with no named icon loses nothing.
    """
    side = _chars_width(system, "number", 2)
    return L.stack(
        L.Node(
            kind="icon",
            name=f"composed-icon-{index}",
            slot=f"item:{index}:icon",
            fixed_w=side,
            fixed_h=round(side * system.shorter_to_y / max(system.shorter_to_x, 0.01)),
            width="hug",
            height="hug",
        ),
        _node(f"composed-heading-{index}", "heading", f"item:{index}:heading"),
        _node(f"composed-text-{index}", "body", f"item:{index}:text", lines=lines),
        gap=0,
        padding_pm=system.block_padding,
        surface="surface-muted",
        name=f"composed-card-{index}",
        height="hug",
    )


def _rich_card(system: DesignSystem, index: int) -> L.Node:
    """The card a real deck is full of: an icon, a title, the line that
    qualifies it, and the paragraph under both.

    Every row is a slot: an item that fills only its heading gets a card with
    only a heading, because the unfilled zones are removed as they always were.
    """
    rows: List[L.Node] = []
    if system.icons:
        side = _chars_width(system, "number", 2)
        rows.append(
            L.Node(
                kind="icon",
                name=f"composed-icon-{index}",
                slot=f"item:{index}:icon",
                fixed_w=side,
                fixed_h=round(
                    side * system.shorter_to_y / max(system.shorter_to_x, 0.01)
                ),
                width="hug",
                height="hug",
            )
        )
    rows.extend(
        [
            _node(f"composed-heading-{index}", "heading", f"item:{index}:heading"),
            _node(f"composed-label-{index}", "label", f"item:{index}:label"),
            _node(f"composed-text-{index}", "body", f"item:{index}:text", lines=4),
        ]
    )
    return L.stack(
        *rows,
        gap=0,
        padding_pm=system.block_padding,
        surface="surface-muted",
        name=f"composed-card-{index}",
        height="hug",
    )


def _framed_cards(system: DesignSystem, count: int) -> L.Node:
    """A framed panel holding a row of cards — the commonest shape of a real
    corporate slide, and the one nothing flat could express (D21)."""
    return L.stack(
        L.stack(
            *[_card_node(system, index, lines=4) for index in range(count)],
            direction="row",
            gap_pm=system.grid.gutter,
            height="hug",
        ),
        padding_pm=system.block_padding,
        surface="surface",
        name="composed-panel",
        height="hug",
    )


def _lead_and_cards(system: DesignSystem, count: int) -> L.Node:
    """A lead block on the left, a column of cards on the right.

    The other shape every deck uses: a statement that frames the slide, and
    the points that support it beside rather than below.
    """
    lead = L.stack(
        _node("composed-lead-heading", "heading", "subtitle"),
        _node("composed-lead-text", "body", "statement", lines=6),
        gap=0,
        padding_pm=system.block_padding,
        surface="surface-muted",
        name="composed-lead",
        height="hug",
    )
    return L.stack(
        lead,
        L.stack(
            *[_card_node(system, index, lines=2) for index in range(count)],
            gap=1,
            height="hug",
        ),
        direction="row",
        gap_pm=system.grid.gutter,
    )


def _body_tree(system: DesignSystem, composition: str, count: int) -> Optional[L.Node]:
    """The tree a composition is, below its title."""
    if composition == "rich_cards":
        return L.stack(
            *[_rich_card(system, index) for index in range(count)],
            direction="row",
            gap_pm=system.grid.gutter,
            height="hug",
        )
    if composition == "icon_cards":
        if not system.icons:
            return None
        return L.stack(
            *[_icon_card(system, index, lines=4) for index in range(count)],
            direction="row",
            gap_pm=system.grid.gutter,
            height="hug",
        )
    if composition == "framed_cards":
        return _framed_cards(system, count)
    if composition == "lead_and_cards":
        return _lead_and_cards(system, count)
    if composition in ("card_row", "comparison"):
        lines = 5 if composition == "card_row" else 6
        return L.stack(
            *[_card_node(system, index, lines=lines) for index in range(count)],
            direction="row",
            gap_pm=system.grid.gutter,
            height="hug",
        )
    if composition == "stat_band":
        return L.stack(
            *[_stat_node(system, index) for index in range(count)],
            direction="row",
            gap_pm=system.grid.gutter,
            height="hug",
        )
    if composition in ("steps", "agenda"):
        return L.stack(
            *[
                _step_row(system, index, numbered=composition == "steps")
                for index in range(count)
            ],
            gap=1,
            height="fill",
        )
    if composition == "progress":
        return L.stack(
            *[_progress_row(system, index) for index in range(count)],
            gap=1,
            height="fill",
        )
    if composition == "statement":
        # `body` binds to the plan's bullets; `subtitle` is only how big it is
        # drawn. A statement reading `subtitle` would never receive a sentence.
        return L.stack(
            _node(
                "composed-statement",
                "body",
                "statement",
                type_role="subtitle",
                anchor="middle",
                height="fill",
            ),
            height="fill",
        )
    if composition == "prose":
        return L.stack(
            _node("composed-body", "body", "body", height="fill"), height="fill"
        )
    if composition == "figure_caption":
        return L.stack(
            L.Node(kind="image", name="composed-image", slot="image", height="fill"),
            _node("composed-caption", "caption", "caption", lines=2),
            gap=1,
            height="fill",
        )
    return None


def _from_tree(system: DesignSystem, tree: L.Node, band: Box) -> List[Piece]:
    """Lay the tree out and turn what it placed into drawable pieces.

    Creation order follows the arrangement, which places a container before
    the children drawn on it — and in the output format creation order IS
    z-order (D6).
    """
    pieces: List[Piece] = []
    ranked: List[Tuple[Piece, int]] = []
    order = 1
    reading = 1
    for item in L.resolve(system, tree, band):
        node, box = item.node, item.box
        if node.kind == "stack":
            pieces.append(card(box, order=order, name=node.name, surface=node.surface))
            order += 1
        elif node.kind == "bar":
            # The Bar illustrates a figure the text beside it states, so it
            # adds nothing for a reader who cannot see it (D15).
            drawn = bar(box, value=1.0, order=order, name=node.name, reading_order=0)
            for piece in drawn:
                piece.decorative = True
                piece.reading_order = 0
            pieces.extend(drawn)
            order += len(drawn)
        elif node.kind == "chip":
            drawn = chip(
                box,
                slot=node.slot,
                order=order,
                name=node.name,
                reading_order=reading,
                padding=0,
            )
            pieces.extend(drawn)
            order += len(drawn)
            reading += 1
        elif node.kind == "divider":
            pieces.append(divider(box, order=order, name=node.name))
            order += 1
        elif node.kind == "icon":
            pieces.append(
                Piece(
                    kind="icon",
                    box=box,
                    order=order,
                    slot=node.slot,
                    name=node.name,
                    reading_order=0,
                    decorative=True,
                )
            )
            order += 1
        elif node.kind == "image":
            pieces.append(
                Piece(
                    kind="image",
                    box=box,
                    role="image",
                    order=order,
                    slot=node.slot,
                    name=node.name,
                    reading_order=reading,
                    fit=node.fit,
                )
            )
            order += 1
            reading += 1
        elif node.role is not None:
            piece = text(
                box,
                role=node.role,
                type_role=node.type_role,
                slot=node.slot,
                order=order,
                name=node.name,
                reading_order=reading,
                anchor=node.anchor,
            )
            pieces.append(piece)
            if node.reading_rank is not None:
                ranked.append((piece, node.reading_rank))
            order += 1
            reading += 1
    _apply_reading_ranks(ranked)
    return pieces


def _apply_reading_ranks(ranked: Sequence[Tuple[Piece, int]]) -> None:
    """Reorder, inside one item, the pieces that declared a reading rank.

    The numbers already allocated are kept and redistributed, so the item's
    place in the slide's reading order does not move — only the order within.
    """
    groups: Dict[str, List[Tuple[Piece, int]]] = {}
    for piece, rank in ranked:
        if piece.slot.startswith("item:"):
            groups.setdefault(piece.slot.split(":")[1], []).append((piece, rank))
    for members in groups.values():
        numbers = sorted(piece.reading_order for piece, _ in members)
        for (piece, _), number in zip(
            sorted(members, key=lambda pair: pair[1]), numbers
        ):
            piece.reading_order = number


def _capacity_of(pieces: Sequence[Piece], count: int) -> Capacity:
    """What the composition declares it can carry, read off its own boxes."""

    def chars(*slots: str) -> int:
        for slot in slots:
            piece = next((p for p in pieces if p.slot == slot), None)
            if piece is not None and piece.max_chars:
                return piece.max_chars
        return 0

    return Capacity(
        items=count,
        heading_chars=chars("item:0:heading"),
        text_chars=chars("item:0:text", "statement", "body", "caption"),
        title_chars=chars("title"),
    )


def compose(
    system: DesignSystem, composition: str, *, items: int = 1
) -> Optional[ComposedSlide]:
    """Resolve one composition against this template, or None when it cannot.

    Returns the pieces in creation order, each already on the grid and already
    bound to a token. Nothing downstream may add a value of its own.
    """
    if not system.complete:
        return None
    count = variant_for(composition, items)
    if count is None:
        return None
    tree = _body_tree(system, composition, count)
    if tree is None:
        return None

    pieces: List[Piece] = [_title_piece(system, order=0)]
    pieces.extend(_from_tree(system, tree, _content_band(system)))
    _measure(system, pieces)
    _renumber(pieces)
    return ComposedSlide(
        composition=composition,
        variant=f"{count}-up" if count > 1 else "single",
        pieces=pieces,
        capacity=_capacity_of(pieces, count),
        notes=[],
    )


def _measure(system: DesignSystem, pieces: List[Piece]) -> None:
    """Give each text piece the size its box can carry, and that box's capacity.

    The size comes from the template's scale, stepped down until the text fits
    (D18): a scale read off a full-width placeholder does not fit a card.
    """
    for piece in pieces:
        if piece.kind != "text" or piece.role is None:
            continue
        drawn_as = piece.type_role or piece.role
        size = _fitting_size(system, drawn_as, box=piece.box)
        lines = max(1, piece.box.h // _line_height(system, size))
        piece.font_pt = size
        piece.max_lines = lines
        piece.max_chars = _capacity_for(
            system, piece.box, role=drawn_as, lines=lines, size_pt=size
        )
    _hold_hierarchy(system, pieces)


#: Reading weight of each role: a figure outranks a title, a title a heading,
#: a heading the body under it. Used to keep the hierarchy when sizes step down.
_ROLE_RANK: Dict[str, int] = {
    "number": 0,
    "title": 1,
    "subtitle": 2,
    "heading": 3,
    "body": 4,
    "caption": 5,
    "label": 6,
}


def _hold_hierarchy(system: DesignSystem, pieces: List[Piece]) -> None:
    """A heading the same size as the text under it has lost the hierarchy the
    scale exists for. Step it back up one rung of the template's own scale.

    Stepping down to fit (D18) is per box, so two roles in the same card can
    land on the same rung — 16pt over 15pt reads as one undifferentiated block.
    """
    steps = sorted({token.size_pt for token in system.type_scale})
    groups: Dict[str, List[Piece]] = {}
    for piece in pieces:
        if piece.kind == "text" and piece.slot.startswith("item:"):
            groups.setdefault(piece.slot.split(":")[1], []).append(piece)
    for members in groups.values():
        members.sort(key=lambda p: _ROLE_RANK.get(str(p.type_role or p.role), 9))
        # From the BOTTOM up: raising a middle row after the one above it has
        # been settled puts them level again, which is how a card with three
        # rows lost its hierarchy while a card with two kept it.
        for higher, lower in reversed(list(zip(members, members[1:]))):
            if higher.font_pt is None or lower.font_pt is None:
                continue
            if higher.font_pt <= lower.font_pt:
                above = [step for step in steps if step > lower.font_pt]
                if above:
                    higher.font_pt = above[0]
                    _recapacity(system, higher)


def _recapacity(system: DesignSystem, piece: Piece) -> None:
    role = piece.type_role or piece.role
    if role is None or piece.font_pt is None:
        return
    lines = max(1, piece.box.h // _line_height(system, piece.font_pt))
    piece.max_lines = lines
    piece.max_chars = _capacity_for(
        system, piece.box, role=role, lines=lines, size_pt=piece.font_pt
    )


def _renumber(pieces: List[Piece]) -> None:
    """Creation order is z-order, so it must be contiguous and start at zero."""
    for index, piece in enumerate(sorted(pieces, key=lambda p: p.order)):
        piece.order = index
