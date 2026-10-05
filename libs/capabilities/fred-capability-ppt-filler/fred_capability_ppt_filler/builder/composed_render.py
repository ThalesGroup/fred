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

"""Translation layer: the resolved composition becomes PowerPoint shapes.

This is the ONLY module that turns a composition into shapes, and it decides
nothing (design.md D8). Every colour, typeface, size and position arrives
already resolved from a token; what happens here is the writing.

Tokens are written as REFERENCES, not as copied values (D11): a theme colour
slot and the theme's font references, so a deck follows a later theme change
instead of quietly falling out of charter. A literal is written only where the
template gave no slot to point at, and the design system records that.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from lxml import etree  # pyright: ignore[reportAttributeAccessIssue]
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from fred_capability_ppt_filler.builder.components import ComposedSlide, Piece
from fred_capability_ppt_filler.builder.design_system import (
    ColorPair,
    ColorToken,
    DesignSystem,
)
from fred_capability_ppt_filler.builder.models import Pattern, Zone

#: A shape's colour map resolves these four; writing the theme name directly
#: would bypass the map the slide actually uses.
_MAPPED = {"dk1": "tx1", "lt1": "bg1", "dk2": "tx2", "lt2": "bg2"}


def _scheme_or_literal(token: ColorToken):
    """The XML for one colour: a reference when we have a slot, else a literal."""

    if token.ref:
        node = etree.SubElement(etree.Element("wrap"), qn("a:schemeClr"))
        node.set("val", _MAPPED.get(token.ref, token.ref))
        # A tint stays a reference: the deck still follows a theme change.
        if token.lum_mod is not None:
            etree.SubElement(node, qn("a:lumMod")).set("val", str(token.lum_mod))
        if token.lum_off is not None:
            etree.SubElement(node, qn("a:lumOff")).set("val", str(token.lum_off))
        return node
    node = etree.SubElement(etree.Element("wrap"), qn("a:srgbClr"))
    node.set("val", token.rgb or "000000")
    return node


def _set_solid_fill(shape, token: ColorToken) -> None:
    """Paint a shape by pointing at the theme rather than copying its value."""

    sp_pr = shape._element.spPr
    for tag in ("a:solidFill", "a:noFill", "a:gradFill", "a:blipFill", "a:pattFill"):
        existing = sp_pr.find(qn(tag))
        if existing is not None:
            sp_pr.remove(existing)
    fill = etree.SubElement(sp_pr, qn("a:solidFill"))
    fill.append(_scheme_or_literal(token))
    # `a:ln` must follow the fill in spPr's sequence; move it if it was there.
    line = sp_pr.find(qn("a:ln"))
    if line is not None:
        sp_pr.remove(line)
        sp_pr.append(line)


def _no_fill(shape) -> None:

    sp_pr = shape._element.spPr
    for tag in ("a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill"):
        existing = sp_pr.find(qn(tag))
        if existing is not None:
            sp_pr.remove(existing)
    if sp_pr.find(qn("a:noFill")) is None:
        line = sp_pr.find(qn("a:ln"))
        fill = etree.SubElement(sp_pr, qn("a:noFill"))
        if line is not None:
            line.addprevious(fill)


def _set_line(shape, token: ColorToken) -> None:
    """Outline a shape in a template colour, pointing at the theme (D11)."""

    sp_pr = shape._element.spPr
    line = sp_pr.find(qn("a:ln"))
    if line is None:
        line = etree.SubElement(sp_pr, qn("a:ln"))
    for child in list(line):
        line.remove(child)
    fill = etree.SubElement(line, qn("a:solidFill"))
    fill.append(_scheme_or_literal(token))


def _no_line(shape) -> None:

    sp_pr = shape._element.spPr
    line = sp_pr.find(qn("a:ln"))
    if line is None:
        line = etree.SubElement(sp_pr, qn("a:ln"))
    for child in list(line):
        line.remove(child)
    etree.SubElement(line, qn("a:noFill"))


def _style_run(run, token, pair: Optional[ColorPair]) -> None:
    """Size, weight, typeface reference and ink — all from the design system."""

    run.font.size = Pt(token.size_pt)
    run.font.bold = token.bold
    r_pr = run._r.get_or_add_rPr()
    if token.font_ref:
        for tag in ("a:latin", "a:cs"):
            existing = r_pr.find(qn(tag))
            if existing is not None:
                r_pr.remove(existing)
        latin = etree.SubElement(r_pr, qn("a:latin"))
        latin.set("typeface", token.font_ref)
    elif token.font_name:
        run.font.name = token.font_name
    if pair is not None:
        existing = r_pr.find(qn("a:solidFill"))
        if existing is not None:
            r_pr.remove(existing)
        fill = etree.Element(qn("a:solidFill"))
        fill.append(_scheme_or_literal(pair.on_surface))
        r_pr.insert(0, fill)


def _set_decorative(shape, decorative: bool) -> None:
    """Mark a shape decorative so assistive technology skips it (D15)."""
    nv = shape._element.nvSpPr.cNvPr if hasattr(shape._element, "nvSpPr") else None
    if nv is None:
        nv = shape._element.find(f".//{qn('p:cNvPr')}")
    if nv is None:
        return
    if decorative:
        nv.set("descr", "")
        nv.set("title", "")
    return


def _set_alt_text(shape, description: str) -> None:
    nv = shape._element.find(f".//{qn('p:cNvPr')}")
    if nv is not None:
        nv.set("descr", description)


_ANCHORS = {
    "top": MSO_ANCHOR.TOP,
    "middle": MSO_ANCHOR.MIDDLE,
    "bottom": MSO_ANCHOR.BOTTOM,
}


class ComposedDrawer:
    """Draws one resolved composition onto one slide."""

    def __init__(self, system: DesignSystem, slide_width: int, slide_height: int):
        self.system = system
        self.width = slide_width
        self.height = slide_height

    # -- geometry ------------------------------------------------------------

    def _emu(self, piece: Piece) -> Tuple[int, int, int, int]:
        box = piece.box
        return (
            round(box.x * self.width / 1000),
            round(box.y * self.height / 1000),
            max(1, round(box.w * self.width / 1000)),
            max(1, round(box.h * self.height / 1000)),
        )

    def _pad_emu(self, piece: Piece) -> int:
        shorter = min(self.width, self.height)
        return round(piece.padding * shorter / 1000)

    def _pair(self, name: str) -> Optional[ColorPair]:
        if name == "none":
            return None
        return self.system.usable_pair(name) or self.system.pair(name)

    # -- drawing -------------------------------------------------------------

    def draw(
        self, slide, composed: ComposedSlide
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Draw every piece in creation order.

        Returns (slot → shape key) for the content, and (piece name → shape
        key) for everything, which the repeated group needs to address the
        containers it removes.

        Creation order is z-order, so this loop must not be reordered: a Card
        drawn after its text would hide it.
        """
        keys: Dict[str, str] = {}
        shapes: Dict[str, str] = {}
        drawn: List[Tuple[Piece, Any]] = []
        for piece in sorted(composed.pieces, key=lambda p: p.order):
            shape = self._draw_piece(slide, piece)
            if shape is None:
                continue
            drawn.append((piece, shape))
            shapes[piece.name] = f"sp:{shape.shape_id}"
            if piece.slot:
                keys[piece.slot] = f"sp:{shape.shape_id}"
        self._set_reading_order(drawn)
        return keys, shapes

    def _draw_piece(self, slide, piece: Piece):
        left, top, width, height = self._emu(piece)
        if piece.kind in ("card", "chip", "bar", "divider"):
            return self._draw_panel(slide, piece, left, top, width, height)
        if piece.kind == "icon":
            return self._draw_icon_frame(slide, piece, left, top, width, height)
        if piece.kind == "image":
            return self._draw_frame(slide, piece, left, top, width, height)
        return self._draw_text(slide, piece, left, top, width, height)

    def _draw_panel(self, slide, piece: Piece, left, top, width, height):
        """A Card, Chip, Bar track or value, or Divider.

        A Card follows the template's own convention: painted where the
        template paints its blocks, an outline where it outlines them (D18).
        A Bar, Chip or Divider is always painted — outlined, a Bar would show
        nothing and a Divider would be two rules instead of one.
        """
        rounded = piece.kind in ("card", "chip", "bar")
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
            Emu(left),
            Emu(top),
            Emu(width),
            Emu(height),
        )
        shape.name = piece.name
        pair = self._pair(piece.surface)
        outline_only = piece.kind == "card" and not self.system.shapes.filled
        if pair is not None and not outline_only:
            _set_solid_fill(shape, pair.surface)
        if outline_only and pair is not None:
            _no_fill(shape)
            _set_line(shape, pair.surface)
        elif not self.system.shapes.stroked:
            _no_line(shape)
        if rounded:
            # A Bar is a pill; a Card follows whatever corner the template uses.
            adjustment = (
                0.5
                if piece.kind in ("bar", "chip")
                else (self.system.shapes.corner_radius)
            )
            try:
                shape.adjustments[0] = adjustment
            except (IndexError, ValueError):
                pass
        shape.text_frame.text = ""
        _set_decorative(shape, piece.decorative)
        return shape

    def _draw_icon_frame(self, slide, piece: Piece, left, top, width, height):
        """Where one of the template's own icons goes (D22).

        Painted with nothing: the renderer replaces it with the icon the plan
        named, and removes it when the plan named none. An empty box left
        behind would read as a missing image.
        """
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height)
        )
        shape.name = piece.name
        _no_fill(shape)
        _no_line(shape)
        _set_decorative(shape, True)
        return shape

    def _draw_frame(self, slide, piece: Piece, left, top, width, height):
        """An empty frame the fill path drops a picture into, cropped to fit."""
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height)
        )
        shape.name = piece.name
        pair = self._pair("surface-muted")
        if pair is not None:
            _set_solid_fill(shape, pair.surface)
        _no_line(shape)
        return shape

    def _draw_text(self, slide, piece: Piece, left, top, width, height):
        box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
        box.name = piece.name
        frame = box.text_frame
        frame.word_wrap = True
        # The format's own 0.1in inset silently defeats any padding computed
        # above this layer, so it is set here rather than guessed around (D6).
        pad = self._pad_emu(piece)
        frame.margin_left = frame.margin_right = Emu(pad)
        frame.margin_top = frame.margin_bottom = Emu(max(0, pad // 2))
        frame.vertical_anchor = _ANCHORS.get(piece.anchor, MSO_ANCHOR.TOP)
        drawn_as = piece.type_role or piece.role
        token = self.system.type_for(drawn_as) if drawn_as else None
        if token is not None:
            run = frame.paragraphs[0].add_run()
            run.text = ""
            _style_run(run, token, self._ink_for(piece))
        return box

    def _ink_for(self, piece: Piece) -> Optional[ColorPair]:
        """The ink a text piece takes: the pair of whatever it sits on (D12)."""
        return self._pair("surface")

    @staticmethod
    def _set_reading_order(drawn: List[Tuple[Piece, Any]]) -> None:
        """Reading order follows the composition, not the creation order (D15)."""
        readable = sorted(
            (pair for pair in drawn if not pair[0].decorative),
            key=lambda pair: pair[0].reading_order,
        )
        for position, (piece, shape) in enumerate(readable):
            nv = shape._element.find(f".//{qn('p:cNvPr')}")
            if nv is not None and piece.kind == "image":
                _set_alt_text(shape, piece.slot or piece.name)
            if nv is not None:
                nv.set("id", nv.get("id") or str(position + 1))


def rekey_pattern(
    pattern: Pattern,
    keys: Dict[str, str],
    shapes: Dict[str, str],
    composed: ComposedSlide,
) -> Pattern:
    """The pattern with every key addressing a shape that now exists.

    The projection named its zones after the pieces, because nothing was drawn
    yet. Here each name is bound to the shape that carries it, so the unchanged
    fill path — zones, repeated groups and the containers it removes — finds
    them all.
    """
    by_name = {piece.name: piece for piece in composed.pieces}

    def rekey(zone: Zone) -> Optional[Zone]:
        piece = by_name.get(zone.key.removeprefix("sp:"))
        key = keys.get(piece.slot) if piece is not None else None
        return zone.model_copy(update={"key": key}) if key else None

    zones = [z for z in (rekey(zone) for zone in pattern.zones) if z is not None]
    groups = []
    for group in pattern.groups:
        items = [
            [z for z in (rekey(zone) for zone in item) if z is not None]
            for item in group.items
        ]
        item_keys = [
            shapes.get(key.removeprefix("sp:"), key) for key in group.item_keys
        ]
        groups.append(group.model_copy(update={"items": items, "item_keys": item_keys}))
    return pattern.model_copy(update={"zones": zones, "groups": groups})
