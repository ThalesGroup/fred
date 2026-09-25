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

Design layer: no ``pptx`` here. A **node** is either a leaf that draws
something or a **stack** that arranges children in a row or a column. Sizing is
``hug`` (as big as its content) or ``fill`` (share what is left) — flexbox's
content-size and grow, and nothing more exotic.

Resolution is the two passes every layout engine runs: *measure* bottom-up,
each node reporting its natural size, then *arrange* top-down, each parent
handing its children a box. The output is absolute per-mille geometry, because
the output format has no flow.

The engine decides WHERE the boxes go and nothing else: every gap comes from
the template's spacing scale, every size from its type ladder, every colour
from one of its token pairs. There are no free values here (D7, D11, D18).
"""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from fred_capability_ppt_filler.builder.design_system import (
    Box,
    DesignSystem,
    ZoneRole,
)

Direction = Literal["row", "column"]
Sizing = Literal["hug", "fill"]
Align = Literal["start", "center", "end", "stretch"]
#: What a leaf draws. "stack" is the container; the rest map to a Piece kind.
NodeKind = Literal[
    "stack", "text", "card", "chip", "bar", "divider", "image", "icon", "spacer"
]
Surface = Literal["none", "surface", "surface-muted", "accent", "inverse"]


class Node(BaseModel):
    """One box of the tree: a stack of children, or something drawn."""

    kind: NodeKind = "stack"
    children: List["Node"] = Field(default_factory=list)

    # -- arrangement, for a stack -------------------------------------------
    direction: Direction = "column"
    #: Index into the template's spacing scale, never a value of our own.
    #: None is no gap at all — 0 is the scale's TIGHTEST step, which is not
    #: the same thing and reads as if it were.
    gap: Optional[int] = None
    padding: Optional[int] = None
    #: A gap the template states directly rather than by scale rung — the grid
    #: gutter it was measured to use, the inset its own blocks give their text.
    #: Per-mille of the shorter side, like the scale. Wins over `gap`/`padding`.
    gap_pm: Optional[int] = None
    padding_pm: Optional[int] = None
    align: Align = "stretch"

    # -- sizing, for any node ------------------------------------------------
    width: Sizing = "fill"
    height: Sizing = "hug"
    #: Share of the leftover main-axis room among `fill` siblings.
    grow: int = 1
    #: Fixed size in per-mille of the slide, for what the content cannot say:
    #: a Bar's thickness, the column a label is given, a Divider's rule.
    fixed_w: Optional[int] = None
    fixed_h: Optional[int] = None
    #: Reading order inside its item, when it differs from the visual order.
    #: A stat band printing the label first still reads the figure first: the
    #: figure is the point (D15).
    reading_rank: Optional[int] = None

    # -- what a leaf carries --------------------------------------------------
    surface: Surface = "none"
    role: Optional[ZoneRole] = None
    type_role: Optional[ZoneRole] = None
    slot: str = ""
    name: str = ""
    decorative: bool = False
    #: How many lines of text this leaf is designed to carry.
    lines: int = 1
    value: Optional[float] = None
    anchor: Literal["top", "middle", "bottom"] = "top"
    fit: Literal["cover", "contain"] = "cover"


Node.model_rebuild()


class Placed(BaseModel):
    """A node and the box the arrangement gave it, in creation order."""

    node: Node
    box: Box
    depth: int = 0


def stack(
    *children: Node,
    direction: Direction = "column",
    gap: Optional[int] = None,
    padding: Optional[int] = None,
    **fields: object,
) -> Node:
    """A container. Reads as the tree it is, which is the point of D21."""
    return Node(
        kind="stack",
        children=list(children),
        direction=direction,
        gap=gap,
        padding=padding,
        **fields,  # type: ignore[arg-type]
    )


# -- measure -------------------------------------------------------------------


def _gap_main(system: DesignSystem, node: Node) -> int:
    """A gap is optically equal in both directions, so it converts per axis."""
    if node.gap_pm is not None:
        return (
            round(node.gap_pm * system.shorter_to_x)
            if node.direction == "row"
            else round(node.gap_pm * system.shorter_to_y)
        )
    if node.gap is None:
        return 0
    return system.gap_x(node.gap) if node.direction == "row" else system.gap_y(node.gap)


def _pad(system: DesignSystem, node: Node) -> Tuple[int, int]:
    """(horizontal, vertical) padding of a node, in per-mille of each axis."""
    if node.padding_pm is not None:
        return (
            round(node.padding_pm * system.shorter_to_x),
            round(node.padding_pm * system.shorter_to_y),
        )
    if node.padding is None:
        return 0, 0
    return system.gap_x(node.padding), system.gap_y(node.padding)


def _line_height(system: DesignSystem, size_pt: float) -> int:
    height = system.slide_height or 1
    return max(20, round(size_pt * 12700 * 1.25 * 1000 / height))


def natural(system: DesignSystem, node: Node, *, avail_w: int) -> Tuple[int, int]:
    """The size `node` wants, given the width it may occupy.

    Bottom-up: a stack cannot know its height before its children report
    theirs, and a text leaf cannot report its height before it knows how wide
    it will be, because that is what decides how many lines it takes.
    """
    from fred_capability_ppt_filler.builder.components import fitting_size

    pad_x, pad_y = _pad(system, node)
    inner_w = max(1, avail_w - 2 * pad_x)

    if node.kind == "stack" and node.children:
        gap = _gap_main(system, node)
        sizes = []
        if node.direction == "row":
            share = max(
                1, (inner_w - gap * (len(node.children) - 1)) // len(node.children)
            )
            sizes = [natural(system, child, avail_w=share) for child in node.children]
            width = sum(w for w, _ in sizes) + gap * (len(sizes) - 1)
            height = max(h for _, h in sizes)
        else:
            sizes = [natural(system, child, avail_w=inner_w) for child in node.children]
            width = max(w for w, _ in sizes)
            height = sum(h for _, h in sizes) + gap * (len(sizes) - 1)
        return width + 2 * pad_x, height + 2 * pad_y

    if node.kind == "text" and node.role is not None:
        width = node.fixed_w if node.fixed_w is not None else avail_w
        role = node.type_role or node.role
        size = fitting_size(
            system, role, width=max(1, width - 2 * pad_x), lines=node.lines
        )
        height = _line_height(system, size) * max(1, node.lines) + 2 * pad_y
        return width, node.fixed_h if node.fixed_h is not None else height

    return (
        node.fixed_w if node.fixed_w is not None else avail_w,
        node.fixed_h if node.fixed_h is not None else 2 * pad_y,
    )


# -- arrange -------------------------------------------------------------------


def arrange(system: DesignSystem, node: Node, box: Box, depth: int = 0) -> List[Placed]:
    """Hand `node` `box`, and its children what is left, top-down.

    Creation order IS z-order in the output format, so a container is placed
    before the children drawn on it (D6). That is why the list is flat and
    ordered rather than a tree.
    """
    placed = [Placed(node=node, box=box, depth=depth)]
    if node.kind != "stack" or not node.children:
        return placed

    pad_x, pad_y = _pad(system, node)
    gap = _gap_main(system, node)
    inner = Box(
        x=box.x + pad_x,
        y=box.y + pad_y,
        w=max(1, box.w - 2 * pad_x),
        h=max(1, box.h - 2 * pad_y),
    )
    row = node.direction == "row"
    span = inner.w if row else inner.h
    total_gap = gap * (len(node.children) - 1)

    wants = [
        natural(
            system,
            child,
            avail_w=inner.w
            if not row
            else max(1, (inner.w - total_gap) // len(node.children)),
        )
        for child in node.children
    ]
    # Indices, not the nodes themselves: two children can be identical trees,
    # and a Pydantic model compares by value, so `child in growers` would pick
    # the wrong one.
    hugging = [
        index
        for index, child in enumerate(node.children)
        if (child.width if row else child.height) == "hug"
    ]
    fixed = sum(wants[index][0 if row else 1] for index in hugging)
    growers = [index for index in range(len(node.children)) if index not in hugging]
    spare = max(0, span - total_gap - fixed)
    weights = sum(max(1, node.children[index].grow) for index in growers) or 1

    cursor = inner.x if row else inner.y
    for index, (child, (want_w, want_h)) in enumerate(zip(node.children, wants)):
        along = want_w if row else want_h
        if index in growers:
            along = round(spare * max(1, child.grow) / weights)
        across = inner.h if row else inner.w
        if row:
            child_box = Box(x=cursor, y=inner.y, w=max(1, along), h=across)
        else:
            child_box = Box(x=inner.x, y=cursor, w=across, h=max(1, along))
        child_box = _cross(system, child, child_box, row=row)
        placed.extend(arrange(system, child, child_box, depth + 1))
        cursor += along + gap
    return placed


def _cross(system: DesignSystem, child: Node, box: Box, *, row: bool) -> Box:
    """Place the child across the track it was given.

    `stretch` fills it. A child that HUGS across — a card in a row of cards —
    takes the size its content asks for and sits where `align` says, which is
    the start unless it says otherwise. Without this a card in a row inherits
    the whole band's height and stretches, whatever its content (D20).
    """
    hugs = (child.height if row else child.width) == "hug"
    if child.align == "stretch" and not hugs:
        return box
    want_w, want_h = natural(system, child, avail_w=box.w)
    size = min(box.h if row else box.w, max(1, want_h if row else want_w))
    slack = max(0, (box.h if row else box.w) - size)
    align = "start" if child.align == "stretch" else child.align
    offset = 0 if align == "start" else (slack // 2 if align == "center" else slack)
    if row:
        return Box(x=box.x, y=box.y + offset, w=box.w, h=size)
    return Box(x=box.x + offset, y=box.y, w=size, h=box.h)


def resolve(system: DesignSystem, root: Node, box: Box) -> List[Placed]:
    """Lay `root` out inside `box` and return everything drawn, in order.

    A stack that paints a surface is kept: it is the Card a designer draws
    round a column, and it must exist before what sits on it.

    A root that hugs gets the height its content asks for, not the whole band:
    a framed panel round three short cards must not run to the footer.
    """
    if root.height == "hug":
        wanted = natural(system, root, avail_w=box.w)[1]
        box = Box(x=box.x, y=box.y, w=box.w, h=max(1, min(box.h, wanted)))
    placed = arrange(system, root, box)
    return [
        item
        for item in placed
        if item.node.kind != "spacer"
        and (item.node.kind != "stack" or item.node.surface != "none")
    ]


__all__ = [
    "Align",
    "Direction",
    "Node",
    "Placed",
    "Sizing",
    "Surface",
    "arrange",
    "natural",
    "resolve",
    "stack",
]
