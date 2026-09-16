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

"""Render a :class:`DeckPlan` on a template into ``.pptx`` bytes.

Synchronous, CPU-bound: the caller runs it off the event loop under the
package's heavy-job slot. Works on a copy of the template: layout patterns
are instantiated, example-slide patterns are duplicated (shapes deep-copied,
picture/media relationships re-created on the new slide), every zone is
filled by role, unused zones are emptied or removed, and the template's own
slides are dropped at the end so the output holds the plan's slides only, in
plan order. Nothing is ever drawn: the corporate design cannot be broken.
"""

from __future__ import annotations

import copy
import io
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, cast

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Emu

from fred_capability_ppt_filler import text_metrics
from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.analysis import (
    _font_name_of,
    estimate_capacity,
    theme_fonts,
)
from fred_capability_ppt_filler.builder.models import (
    Pattern,
    RepeatGroup,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    SlidePlan,
    has_content,
    resolve,
)
from fred_capability_ppt_filler.images import fit_inside_box
from fred_capability_ppt_filler.inline_markdown import parse_inline_markdown
from fred_capability_ppt_filler.traversal import PlacedShape, walk_shapes

# Smallest font scale the overflow control applies before truncating.
MIN_FONT_SCALE = 0.7
# Sub-bullets get narrower lines: this factor per level in the capacity estimate.
_LEVEL_WIDTH_FACTOR = 0.85
# Slack over the measured width when sizing a box that must not wrap: the
# renderer's font is not always the one measured here (see `text_metrics`).
_NO_WRAP_MARGIN = 1.06

_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_SKIPPED_RELS = ("/slideLayout", "/notesSlide")

PreparedImage = Tuple[bytes, int, int]


@dataclass
class RenderResult:
    pptx: bytes
    # Human-readable notes for the agent: truncations, substitutions, unfilled images.
    warnings: List[str] = field(default_factory=list)
    slide_count: int = 0
    # The same deck adjusted for the PDF preview only (see `_widen_no_wrap_text`).
    preview_pptx: bytes = b""


_FILLS = ("a:solidFill", "a:gradFill", "a:pattFill", "a:blipFill")


def _is_bare_text_box(sp) -> bool:
    """A text box drawing nothing but its text: widening it moves no visible edge."""
    non_visual = sp.find(f"{qn('p:nvSpPr')}/{qn('p:cNvSpPr')}")
    props = sp.find(qn("p:spPr"))
    if non_visual is None or non_visual.get("txBox") != "1" or props is None:
        return False
    if sp.find(qn("p:style")) is not None:
        return False
    if any(props.find(qn(tag)) is not None for tag in _FILLS):
        return False
    line = props.find(qn("a:ln"))
    return line is None or line.find(qn("a:noFill")) is not None


def _widen_no_wrap_text(presentation) -> int:
    """Give every one-line text box the room it would take in PowerPoint.

    LibreOffice ignores "do not wrap" and breaks such a box as soon as its
    substitute font runs wider than the designer's ("Merc|i"). Widening it in
    the preview copy, anchored on its alignment, changes nothing a reader of the
    .pptx would see; the delivered file is never touched.
    """
    width = presentation.slide_width
    widened = 0
    parts = [slide for slide in presentation.slides]
    for master in presentation.slide_masters:
        parts.append(master)
        parts.extend(master.slide_layouts)
    for part in parts:
        for sp in part.shapes._spTree.iter(qn("p:sp")):
            body = sp.find(f"{qn('p:txBody')}/{qn('a:bodyPr')}")
            xfrm = sp.find(f"{qn('p:spPr')}/{qn('a:xfrm')}")
            if (
                body is None
                or body.get("wrap") != "none"
                or body.get("vert") not in (None, "horz")
                or xfrm is None
                or xfrm.get("rot") not in (None, "0")
                or sp.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}") is not None
                or not _is_bare_text_box(sp)
                or not "".join(t.text or "" for t in sp.iter(qn("a:t"))).strip()
            ):
                continue
            off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
            if off is None or ext is None:
                continue
            low, high = 0, width
            parent = sp.getparent()
            if parent is not None and parent.tag == qn("p:grpSp"):
                ch_off = parent.find(
                    f"{qn('p:grpSpPr')}/{qn('a:xfrm')}/{qn('a:chOff')}"
                )
                ch_ext = parent.find(
                    f"{qn('p:grpSpPr')}/{qn('a:xfrm')}/{qn('a:chExt')}"
                )
                if ch_off is None or ch_ext is None:
                    continue
                low = int(ch_off.get("x", "0"))
                high = low + int(ch_ext.get("cx", "0"))
            left, box = int(off.get("x", "0")), int(ext.get("cx", "0"))
            ppr = sp.find(f"{qn('p:txBody')}/{qn('a:p')}/{qn('a:pPr')}")
            align = ppr.get("algn") if ppr is not None else None
            if align == "ctr":
                center = left + box // 2
                half = min(center - low, high - center)
                new_left, new_box = center - half, 2 * half
            elif align == "r":
                new_left, new_box = low, left + box - low
            else:
                new_left, new_box = left, high - left
            if new_box > box:
                off.set("x", str(new_left))
                ext.set("cx", str(new_box))
                widened += 1
    return widened


@dataclass
class _Line:
    text: str
    level: int = 0
    # A column heading written into the body for want of a heading zone. It
    # drops the bullet glyph, so the reader can still tell it from the content.
    heading: bool = False


class RenderError(ValueError):
    """The plan cannot be rendered on this template (the agent's correctable mistake)."""


# --- slide creation -------------------------------------------------------------


def _all_layouts(presentation) -> list:
    return [
        layout
        for master in presentation.slide_masters
        for layout in master.slide_layouts
    ]


def _duplicate_slide(presentation, source):
    """Append a copy of ``source``: same layout, background, shapes and media."""
    dest = presentation.slides.add_slide(source.slide_layout)
    for shape in list(dest.shapes):
        shape._element.getparent().remove(shape._element)

    source_cSld = source._element.cSld
    background = source_cSld.find(qn("p:bg"))
    if background is not None:
        dest._element.cSld.insert(0, copy.deepcopy(background))

    # Re-create the relationships the copied XML points at, sharing the same
    # target parts (an image copied ten times stays one part in the package).
    rid_map: Dict[str, str] = {}
    for rId, rel in source.part.rels.items():
        if rel.reltype.endswith(_SKIPPED_RELS):
            continue
        if rel.is_external:
            rid_map[rId] = dest.part.rels.get_or_add_ext_rel(
                rel.reltype, rel.target_ref
            )
        else:
            rid_map[rId] = dest.part.relate_to(rel.target_part, rel.reltype)

    dest_tree = dest.shapes._spTree
    for element in source.shapes._spTree:
        if element.tag in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            continue
        clone = copy.deepcopy(element)
        if rid_map:
            for node in clone.iter():
                # Every relationship-namespace attribute (r:embed, r:link,
                # r:id, SmartArt's r:dm/r:lo/…), not a fixed list.
                for attr, old in list(node.attrib.items()):
                    if attr.startswith(_R_NS) and old in rid_map:
                        node.set(attr, rid_map[old])
        dest_tree.append(clone)
    return dest


def _remove_slides(presentation, slide_ids: Sequence[int]) -> None:
    wanted = set(slide_ids)
    id_list = presentation.slides._sldIdLst
    for sldId in list(id_list):
        if sldId.id in wanted:
            presentation.part.drop_rel(sldId.rId)
            id_list.remove(sldId)


# --- shape addressing -----------------------------------------------------------


def _shape_index(slide) -> Dict[str, PlacedShape]:
    """Zone key → shape for one slide (placeholder idx and shape-id path keys)."""
    index: Dict[str, PlacedShape] = {}
    for placed in walk_shapes(slide.shapes):
        shape = cast(Any, placed.shape)
        index["sp:" + "/".join(str(p) for p in placed.path)] = placed
        if shape.is_placeholder:
            index.setdefault(f"ph:{shape.placeholder_format.idx}", placed)
    return index


def _overlap_ratio(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    """Intersection area over the smaller box's area (0 when apart)."""
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return (width * height) / smaller if smaller else 0.0


def _box_of(placed: PlacedShape) -> Tuple[int, int, int, int]:
    return (
        placed.left,
        placed.top,
        placed.left + placed.width,
        placed.top + placed.height,
    )


def _axis_cover(low: int, high: int, other_low: int, other_high: int) -> float:
    span = high - low
    if span <= 0:
        # A connector is a line: zero-thick on one axis, and any area ratio
        # scores it 0 however squarely it sits inside the other shape.
        return 1.0 if other_low <= low <= other_high else 0.0
    return max(0, min(high, other_high) - max(low, other_low)) / span


def _covered(box: Tuple[int, int, int, int], other: Tuple[int, int, int, int]) -> float:
    """Share of ``box`` that lies inside ``other``, lines included."""
    return _axis_cover(box[0], box[2], other[0], other[2]) * _axis_cover(
        box[1], box[3], other[1], other[3]
    )


# Below this the shift is not worth the risk of nudging a deliberate alignment.
_RECENTRE_MIN_EMU = 91440


def _remove(placed: PlacedShape) -> None:
    element = cast(Any, placed.shape)._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


# --- text -----------------------------------------------------------------------------


def _lines_from_bullets(bullets: Sequence[str]) -> List[_Line]:
    lines: List[_Line] = []
    for raw in bullets:
        text = raw.rstrip()
        if not text.strip():
            continue
        level = 0
        stripped = text.lstrip()
        indent = len(text) - len(stripped)
        while stripped.startswith(("- ", "* ", "• ")):
            level += 1
            stripped = stripped[2:].lstrip()
        if level == 0 and indent >= 2:
            level = 1
        lines.append(_Line(stripped, min(level, 2)))
    return lines


def _write_lines(shape, lines: Sequence[_Line]) -> None:
    """Replace a text frame's content, inheriting the first paragraph's style.

    The first paragraph's ``pPr`` and its first run's ``rPr`` (or the paragraph's
    end-run properties) are the style templates; every new paragraph/run clones
    them, so the designer's font, size and colour carry over. Inline
    ``**bold**``/``*italic*`` is honoured per span.
    """
    text_frame = shape.text_frame
    txBody = text_frame._txBody
    paragraphs = txBody.findall(qn("a:p"))
    base_pPr = base_rPr = None
    if paragraphs:
        first = paragraphs[0]
        pPr = first.find(qn("a:pPr"))
        base_pPr = copy.deepcopy(pPr) if pPr is not None else None
        run = first.find(qn("a:r"))
        rPr = run.find(qn("a:rPr")) if run is not None else None
        if rPr is None:
            end = first.find(qn("a:endParaRPr"))
            if end is not None:
                rPr = copy.deepcopy(end)
                rPr.tag = qn("a:rPr")
        base_rPr = copy.deepcopy(rPr) if rPr is not None else None
    for paragraph in paragraphs:
        txBody.remove(paragraph)

    for line in lines or [_Line("")]:
        p = txBody.add_p()
        if base_pPr is not None:
            p.insert(0, copy.deepcopy(base_pPr))
        if line.level:
            p.get_or_add_pPr().set("lvl", str(line.level))
        if line.heading:
            pPr = p.get_or_add_pPr()
            for existing in pPr.findall(qn("a:buChar")) + pPr.findall(
                qn("a:buAutoNum")
            ):
                pPr.remove(existing)
            pPr.append(pPr.makeelement(qn("a:buNone"), {}))
        for span in parse_inline_markdown(line.text):
            r = p.add_r()
            if base_rPr is not None:
                r.insert(0, copy.deepcopy(base_rPr))
            r.text = span.text
            if span.bold or span.italic:
                rPr = r.get_or_add_rPr()
                if span.bold:
                    rPr.set("b", "1")
                if span.italic:
                    rPr.set("i", "1")


def _clear_text(shape) -> None:
    _write_lines(shape, [])


def _set_font_scale(shape, scale: float, base_pt: Optional[float] = None) -> None:
    """Shrink a text frame. With a known base size every run gets an explicit
    scaled size, which every renderer honours; otherwise fall back to
    ``normAutofit`` (``fontScale`` in 1/1000 %)."""
    txBody = shape.text_frame._txBody
    if base_pt:
        for tag in ("a:rPr", "a:endParaRPr"):
            for rPr in txBody.iter(qn(tag)):
                current = rPr.get("sz")
                size = int(current) / 100 if current else base_pt
                rPr.set("sz", str(max(600, int(size * scale * 100))))
        for run in txBody.iter(qn("a:r")):
            if run.find(qn("a:rPr")) is None:
                rPr = run.makeelement(
                    qn("a:rPr"), {"sz": str(max(600, int(base_pt * scale * 100)))}
                )
                run.insert(0, rPr)
        return
    bodyPr = txBody.find(qn("a:bodyPr"))
    if bodyPr is None:
        return
    for child in list(bodyPr):
        if child.tag in (qn("a:noAutofit"), qn("a:spAutoFit"), qn("a:normAutofit")):
            bodyPr.remove(child)
    autofit = bodyPr.makeelement(qn("a:normAutofit"), {})
    autofit.set("fontScale", str(int(scale * 100000)))
    autofit.set("lnSpcReduction", "10000")
    bodyPr.append(autofit)


# PowerPoint's default text inset, used when a box declares none.
_DEFAULT_INSET_EMU = 91440


def _text_insets(shape) -> int:
    """Left plus right padding of a text box: the text is laid inside them."""
    body = shape.text_frame._txBody.find(qn("a:bodyPr"))
    if body is None:
        return 2 * _DEFAULT_INSET_EMU
    return sum(int(body.get(side, _DEFAULT_INSET_EMU)) for side in ("lIns", "rIns"))


def _grows_with_text(shape, inherited=None) -> bool:
    """A box that does not wrap: its width follows its text, so it is sized
    rather than fitted.

    Auto-sizing the *height* is a different thing and must not come here: such a
    box still wraps inside its width, and widening it pushes the text out of the
    design (a cover title over the photo beside it). It grows downwards without
    complaint, which is exactly why its line budget has to be enforced — off the
    bottom of the slide is not "fitted".

    A placeholder cloned from a layout carries a bare ``bodyPr`` and draws with
    the layout's rule, so the layout's own is what decides.
    """
    for bodyPr in (shape.text_frame._txBody.find(qn("a:bodyPr")), inherited):
        if bodyPr is not None and bodyPr.get("wrap") == "none":
            return True
    return False


def _sibling_key(zone: Zone, pattern: Pattern) -> str:
    """Zones that play the same part on one slide: the same role, and for a
    repeated group the same position inside each item."""
    for group in pattern.groups:
        for item in group.items:
            for position, member in enumerate(item):
                if member.key == zone.key:
                    return f"{group.key}/{position}/{zone.role}"
    return f"slide/{zone.role}"


def _layout_body_props(slide) -> Dict[str, Any]:
    """``bodyPr`` of each layout placeholder, by the zone key it answers to."""
    props: Dict[str, Any] = {}
    try:
        placeholders = slide.slide_layout.placeholders
    except (AttributeError, KeyError):
        return props
    for shape in placeholders:
        if not shape.has_text_frame:
            continue
        body = shape.text_frame._txBody.find(qn("a:bodyPr"))
        if body is not None:
            props[f"ph:{shape.placeholder_format.idx}"] = body
    return props


def _fit(
    zone: Zone,
    lines: List[_Line],
    width: int,
    height: int,
    font_name: Optional[str] = None,
    bold: bool = False,
) -> Tuple[List[_Line], Optional[float], bool]:
    """Fit ``lines`` into ``zone``: returns ``(lines, font scale or None, truncated)``."""
    # The analysis already measured this zone through its box formatting, and
    # that is the number the agent was given: re-deriving it here is how the
    # two ended up disagreeing. Only an inventory saved without one is computed.
    if zone.max_chars and zone.max_lines:
        max_chars, max_lines = zone.max_chars, zone.max_lines
    else:
        max_chars, max_lines = estimate_capacity(
            zone.box, zone.font_pt, zone.role, width, height, font_name, bold
        )
    chars_per_line = max(1, max_chars // max(1, max_lines))
    # How many em of text one line holds: each line is measured in the real
    # font, so a line of capitals counts for what it draws.
    line_em = chars_per_line * text_metrics.char_em(font_name, bold)

    def needed(scale: float) -> int:
        room = line_em / scale
        return sum(
            max(
                1,
                math.ceil(
                    text_metrics.width_em(line.text, font_name, bold)
                    / (room * _LEVEL_WIDTH_FACTOR**line.level)
                ),
            )
            for line in lines
        )

    # A word longer than a line breaks in the middle: shrink until it fits.
    longest = max(
        (
            text_metrics.width_em(word, font_name, bold)
            for line in lines
            for word in line.text.split()
        ),
        default=0.0,
    )
    word_scale = min(1.0, line_em / longest) if longest else 1.0
    if needed(1.0) <= max_lines and word_scale >= 1.0:
        return lines, None, False
    scale = min(max_lines / needed(1.0), word_scale)
    if scale >= MIN_FONT_SCALE:
        return lines, round(scale, 2), False
    if needed(MIN_FONT_SCALE) <= max_lines:
        # A word longer than the line (a URL, an address) would drag the whole
        # zone below the floor on its own. It breaks instead: illegible text
        # helps nobody, and the break shows the agent what to shorten.
        return lines, MIN_FONT_SCALE, False

    capacity = max_lines / MIN_FONT_SCALE
    room_em = line_em / MIN_FONT_SCALE
    per_char = text_metrics.char_em(font_name, bold) or text_metrics.FALLBACK_CHAR_EM
    kept: List[_Line] = []
    used = 0.0
    dropped = False
    for line in lines:
        cost = max(
            1,
            math.ceil(
                text_metrics.width_em(line.text, font_name, bold)
                / (room_em * _LEVEL_WIDTH_FACTOR**line.level)
            ),
        )
        if used + cost > capacity:
            room = int((capacity - used) * room_em / per_char) - 1
            # Never leave the zone blank: a cut first line beats an empty box.
            if not kept:
                kept.append(_Line(_cut(line.text, max(room, 1)), line.level))
            dropped = True
            break
        kept.append(line)
        used += cost
    # Everything fitted once shrunk to the floor: shrinking is not truncating,
    # and saying it is sends the agent rewriting text that was never cut.
    return kept, MIN_FONT_SCALE, dropped


def _cut(text: str, room: int) -> str:
    if room >= len(text):
        return text
    cut = text[:room]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"


def _auto_number(sample: str, index: int) -> str:
    if re.fullmatch(r"0\d", sample.strip()):
        return f"{index + 1:02d}"
    if sample.strip().isdigit():
        return str(index + 1)
    return ""


# --- zone mapping -----------------------------------------------------------------------


def _reading_order(zones: Sequence[Zone]) -> List[Zone]:
    return sorted(zones, key=lambda z: (z.box.y // 150, z.box.x))


def _column_order(zones: Sequence[Zone]) -> List[Zone]:
    return sorted(zones, key=lambda z: (z.box.x // 150, z.box.y))


class _ZoneMap:
    def __init__(self, pattern: Pattern) -> None:
        zones = [z for z in pattern.zones if z.role != "keep"]
        self.titles = [z for z in zones if z.role == "title"]
        self.subtitles = [z for z in zones if z.role == "subtitle"]
        self.headings = _column_order([z for z in zones if z.role == "heading"])
        self.bodies = _column_order([z for z in zones if z.role == "body"])
        self.captions = _column_order([z for z in zones if z.role == "caption"])
        self.numbers = _column_order([z for z in zones if z.role == "number"])
        self.labels = _column_order([z for z in zones if z.role == "label"])
        self.images = _reading_order([z for z in zones if z.role == "image"])
        self.all_text = [z for z in zones if z.role != "image"]

    def body_like(self) -> List[Zone]:
        return self.bodies or self.captions or self.subtitles

    def stacked(self) -> List[Zone]:
        """Every non-title text line in reading order (contact cards)."""
        return sorted(
            (z for z in self.all_text if z.role not in ("title", "number")),
            key=lambda z: (z.box.y, z.box.x),
        )


def _assign_text(
    pattern: Pattern, plan: SlidePlan, lost: Optional[List[str]] = None
) -> Dict[str, List[_Line]]:
    """Decide which lines go into which text zone (by zone key). Plan content
    no zone receives is named in ``lost``, so the agent hears about it."""
    zmap = _ZoneMap(pattern)
    out: Dict[str, List[_Line]] = {}
    lost = lost if lost is not None else []

    def put(zone: Optional[Zone], lines: List[_Line], what: str) -> None:
        if not lines:
            return
        if zone is None or zone.key in out:
            lost.append(what)
            return
        out[zone.key] = lines

    title = _lines_from_bullets([plan.title]) if plan.title else []
    subtitle = _lines_from_bullets([plan.subtitle]) if plan.subtitle else []
    bullets = _lines_from_bullets(plan.bullets)

    if zmap.titles:
        put(zmap.titles[0], title, "title")
    elif zmap.headings and title and not plan.columns:
        put(zmap.headings[0], title, "title")
    else:
        put(None, title, "title")

    if pattern.intent in ("title", "section", "statement"):
        # Covers put their subtitle in whatever sits under the title.
        target = zmap.subtitles or zmap.body_like()
        put(
            target[0] if target else None,
            subtitle or bullets,
            "subtitle" if subtitle else "bullets",
        )
        if subtitle and bullets:
            lost.append("bullets")
        return out

    if zmap.subtitles:
        put(zmap.subtitles[0], subtitle, "subtitle")
    elif subtitle and not bullets and zmap.bodies and not plan.columns:
        bullets = subtitle
    elif subtitle:
        lost.append("subtitle")

    if plan.columns:
        for index, column in enumerate(plan.columns):
            body = zmap.bodies[index] if index < len(zmap.bodies) else None
            heading = zmap.headings[index] if index < len(zmap.headings) else None
            lines = _lines_from_bullets(column.bullets)
            if column.heading and heading is not None:
                put(
                    heading,
                    _lines_from_bullets([column.heading]),
                    f"column {index + 1}",
                )
            elif column.heading:
                lines = [_Line(f"**{column.heading}**", heading=True)] + lines
            put(body, lines, f"column {index + 1}")
        if bullets:
            lost.append("bullets")
        return out

    if pattern.intent == "contact" and bullets:
        zones = [z for z in zmap.stacked() if z.key not in out]
        for zone, line in zip(zones, bullets):
            put(zone, [line], "bullets")
        if len(bullets) > len(zones):
            lost.append(f"{len(bullets) - len(zones)} bullet(s)")
        return out
    bodies = zmap.body_like()
    if not bullets:
        return out
    if not bodies:
        lost.append("bullets")
        return out
    if len(bodies) > 1 and pattern.intent in ("two_columns", "comparison"):
        half = math.ceil(len(bullets) / 2)
        put(bodies[0], bullets[:half], "bullets")
        put(bodies[1], bullets[half:], "bullets")
    else:
        put(bodies[0], bullets, "bullets")
    return out


def _unused_item_fields(groups: Sequence[RepeatGroup], plan: SlidePlan) -> List[str]:
    """Item fields the plan fills that none of the slide's groups has a zone for
    (every group is fed the same items)."""
    roles = {role for group in groups for role in group.item_zones}
    lost: Dict[str, None] = {}
    for item in plan.items[: max((g.count for g in groups), default=0)]:
        heading_shown = bool(roles & {"heading", "title", "subtitle"}) or (
            "label" in roles and not item.label
        )
        checks = (
            ("number", item.number, "number" in roles),
            ("heading", item.heading, heading_shown),
            ("text", item.text, bool(roles & {"body", "caption"})),
            ("label", item.label, "label" in roles),
            ("image", item.image, "image" in roles),
        )
        for name, value, shown in checks:
            if value and not shown:
                lost[name] = None
    return [f"items' {name}" for name in lost]


def _assign_group(
    group: RepeatGroup, plan: SlidePlan
) -> Tuple[Dict[str, List[_Line]], Dict[str, Optional[str]], int]:
    """Lines and image ids per item zone key; returns ``(text, images, used items)``."""
    text: Dict[str, List[_Line]] = {}
    images: Dict[str, Optional[str]] = {}
    used = min(len(plan.items), group.count)
    for index in range(used):
        item = plan.items[index]
        zones = group.items[index]
        has_heading = any(z.role == "heading" for z in zones)
        for zone in zones:
            if zone.role == "number":
                value = item.number or _auto_number(zone.sample, index)
                text[zone.key] = _lines_from_bullets([value]) if value else []
            elif zone.role == "heading":
                text[zone.key] = _lines_from_bullets([item.heading or ""])
            elif zone.role in ("body", "caption"):
                text[zone.key] = _lines_from_bullets([item.text or ""])
            elif zone.role == "label":
                value = item.label or (item.heading if not has_heading else None) or ""
                text[zone.key] = _lines_from_bullets([value])
            elif zone.role == "image":
                images[zone.key] = item.image
            elif zone.role in ("title", "subtitle"):
                text[zone.key] = _lines_from_bullets([item.heading or ""])
    return text, images, used


# --- rendering ------------------------------------------------------------------------------


def _has_text_below(zone: Zone, siblings: Sequence[Zone]) -> bool:
    """Whether another text zone of the same item starts under this one: only
    then does a second line run into something."""
    bottom = zone.box.y + zone.box.h
    return any(
        other.key != zone.key
        and other.role not in ("image", "keep")
        and other.box.y >= zone.box.y + zone.box.h / 2
        and other.box.y <= bottom + zone.box.h
        and other.box.x < zone.box.x + zone.box.w
        and zone.box.x < other.box.x + other.box.w
        for other in siblings
    )


def _only_names_the_slide(plan: SlidePlan, pattern: Pattern) -> bool:
    """A fixed slide given only the title it already shows ("Merci" on "Merci",
    or any closing word on a closing slide) lost nothing."""
    title = plan.title or ""
    if not title or has_content(plan.model_copy(update={"title": None})):
        return False
    names = {lexicon.normalize(pattern.label), lexicon.normalize(pattern.name)}
    closing = lexicon.name_matches(
        pattern.label, lexicon.CLOSING_NAMES
    ) or lexicon.name_matches(pattern.name, lexicon.CLOSING_NAMES)
    return lexicon.normalize(title) in names or (
        closing and lexicon.name_matches(title, lexicon.CLOSING_NAMES)
    )


class _Renderer:
    def __init__(
        self,
        presentation,
        inventory: TemplateInventory,
        images: Mapping[str, PreparedImage],
    ) -> None:
        self.prs = presentation
        self.inventory = inventory
        self.images = images
        self.width = presentation.slide_width
        self.height = presentation.slide_height
        self.warnings: List[str] = []
        self.layouts = _all_layouts(presentation)
        self.theme = theme_fonts(presentation)
        self.slides_by_id = {slide.slide_id: slide for slide in presentation.slides}

    def render(self, plan: DeckPlan) -> RenderResult:
        original_ids = list(self.slides_by_id)
        rendered = 0
        # (position, topics) of each agenda: a deck that announces more topics
        # than it has slides left is one the agent meant to write and did not.
        announced: List[Tuple[int, int]] = []
        for position, slide_plan in enumerate(plan.slides, start=1):
            if slide_plan.invalid_entry is not None:
                self.warnings.append(
                    f"Entry {position} of 'slides' was not a slide object and was skipped "
                    f"({slide_plan.invalid_entry!r})."
                )
                continue
            if slide_plan.ignored_fields:
                self.warnings.append(
                    f"Slide {position}: {', '.join(sorted(slide_plan.ignored_fields))} "
                    "is not a field of a slide, and its content is not in the deck."
                )
            resolution = resolve(self.inventory, slide_plan)
            pattern = resolution.pattern
            if resolution.substitution:
                self.warnings.append(f"Slide {position}: {resolution.substitution}.")
            rendered += 1
            if pattern.intent == "agenda" and slide_plan.items:
                announced.append((rendered, len(slide_plan.items)))
            slide = self._create(pattern)
            if pattern.intent != "fixed":
                self._fill(slide, pattern, slide_plan, position)
            elif has_content(slide_plan) and not _only_names_the_slide(
                slide_plan, pattern
            ):
                self.warnings.append(
                    f"Slide {position}: '{pattern.label}' is a fixed slide used as is; the content "
                    "given for it was ignored (nothing to do unless that content matters)."
                )
            frame = (
                slide.notes_slide.notes_text_frame
                if slide_plan.notes
                or (slide.has_notes_slide and pattern.source == "slide")
                else None
            )
            if frame is not None:
                frame.text = slide_plan.notes or ""
        if rendered == 0:
            raise RenderError("The plan holds no usable slide.")
        for position, topics in announced:
            remaining = rendered - position
            # Only a wide gap: a deck may well cover five topics in three
            # slides, but not in none.
            if topics >= 3 and remaining * 2 < topics:
                self.warnings.append(
                    f"Slide {position} announces {topics} topics but only {remaining} slide(s) follow it. "
                    "The deck holds what was sent, not what was planned: if slides are missing, call again "
                    "with the complete list."
                )
        _remove_slides(self.prs, original_ids)
        buffer = io.BytesIO()
        self.prs.save(buffer)
        preview = buffer
        try:
            widened = _widen_no_wrap_text(self.prs)
        except (ValueError, TypeError):  # unexpected geometry: preview as delivered
            widened = 0
        if widened:
            preview = io.BytesIO()
            self.prs.save(preview)
        return RenderResult(
            pptx=buffer.getvalue(),
            warnings=self.warnings,
            slide_count=rendered,
            preview_pptx=preview.getvalue(),
        )

    def _create(self, pattern: Pattern):
        if pattern.source == "layout":
            if pattern.source_index >= len(self.layouts):
                raise RenderError(
                    f"Layout {pattern.source_index} no longer exists in the template."
                )
            return self.prs.slides.add_slide(self.layouts[pattern.source_index])
        slide_id = int(pattern.id.split(":", 1)[1])
        source = self.slides_by_id.get(slide_id)
        if source is None:
            raise RenderError(f"Slide {slide_id} no longer exists in the template.")
        return _duplicate_slide(self.prs, source)

    def _fill(self, slide, pattern: Pattern, plan: SlidePlan, position: int) -> None:
        index = _shape_index(slide)
        lost: List[str] = []
        text = _assign_text(pattern, plan, lost)
        image_ids: Dict[str, Optional[str]] = {}
        zmap = _ZoneMap(pattern)
        # Both fields are offered, so a model names the hero picture in `image`
        # and the rest in `images`; taking one or the other dropped the hero.
        plan_images = list(
            dict.fromkeys(([plan.image] if plan.image else []) + list(plan.images))
        )
        for zone, image_id in zip(zmap.images, plan_images + [None] * len(zmap.images)):
            image_ids[zone.key] = image_id
        if len(plan_images) > len(zmap.images):
            lost.append(f"{len(plan_images) - len(zmap.images)} image(s)")
        if plan.items and not pattern.groups:
            lost.append("items")
        lost.extend(_unused_item_fields(pattern.groups, plan))

        for group in pattern.groups:
            group_text, group_images, used = _assign_group(group, plan)
            text.update(group_text)
            image_ids.update(group_images)
            if len(plan.items) > group.count:
                self.warnings.append(
                    f"Slide {position}: '{pattern.label}' holds {group.count} items, "
                    f"{len(plan.items) - group.count} were dropped."
                )
            kept = [p for p in (index.get(k) for k in group.item_keys[:used]) if p]
            dropped = [p for p in (index.get(k) for k in group.item_keys[used:]) if p]
            if dropped and kept:
                self._remove_decoration(dropped, kept, index, pattern)
            elif dropped:
                # Nothing was kept, so nothing anchors the decoration: sweeping
                # by overlap here takes the slide's own background with it.
                self.warnings.append(
                    f"Slide {position}: '{pattern.label}' shows its content as items, "
                    f"and the plan gave none; use `items` (up to {group.count}) for it."
                )
            for placed in dropped:
                _remove(placed)
            if kept and dropped:
                self._recentre_items(kept, dropped, index, pattern)
            self._even_out_item_widths(group, index)
        if lost:
            self.warnings.append(
                f"Slide {position}: '{pattern.label}' has no place for {', '.join(lost)}; "
                "that content is not in the deck. Put it on a pattern that shows it, or drop it."
            )
        if pattern.groups:
            # Widths and removals changed the slide: re-read absolute geometry.
            index = _shape_index(slide)

        containers = {
            z.key: index.get(key)
            for g in pattern.groups
            for key, item in zip(g.item_keys, g.items)
            for z in item
        }
        siblings: Dict[str, Sequence[Zone]] = {
            z.key: pattern.zones for z in pattern.zones
        }
        siblings.update(
            {z.key: item for g in pattern.groups for item in g.items for z in item}
        )
        layout_body = _layout_body_props(slide)
        scaled: Dict[str, List[Tuple[Any, Zone, float]]] = {}
        for zone in self._fillable_text_zones(pattern):
            placed = index.get(zone.key)
            shape = cast(Any, placed.shape) if placed is not None else None
            if (
                placed is None
                or shape is None
                or not getattr(shape, "has_text_frame", False)
            ):
                continue
            lines = text.get(zone.key, [])
            if not lines:
                # An empty placeholder is not blank in PowerPoint: it shows its
                # prompt ("Click to add text") the moment the user opens the
                # deck to edit it. Dropping it leaves the slide clean, and the
                # layout can always put it back.
                if cast(Any, shape).is_placeholder:
                    _remove(placed)
                else:
                    _clear_text(shape)
                continue
            if zone.role == "number":
                # "1 200", "62 %", "4,2 M€" never break across lines.
                lines = [
                    _Line(line.text.replace(" ", " "), line.level) for line in lines
                ]
            font_name, bold = _font_name_of(
                shape, self.theme, is_title=zone.role == "title"
            )
            one_line_room: Optional[int] = None
            if _grows_with_text(shape, layout_body.get(zone.key)):
                scale, one_line_room = self._no_wrap_scale(
                    zone,
                    lines,
                    placed,
                    containers.get(zone.key),
                    _has_text_below(zone, siblings.get(zone.key, ())),
                    font_name,
                    bold,
                )
                truncated = False
            else:
                lines, scale, truncated = _fit(
                    zone, lines, self.width, self.height, font_name, bold
                )
            _write_lines(shape, lines)
            # Registered even when it needs no shrinking: a sibling that does is
            # what decides the size of the set.
            scaled.setdefault(_sibling_key(zone, pattern), []).append(
                (shape, zone, 1.0 if scale is None else scale)
            )
            if one_line_room is not None:
                self.warnings.append(
                    f"Slide {position}: the {zone.role} '{lines[0].text}' of '{pattern.label}' does not fit "
                    f"on one line and runs into the text below; keep it under {one_line_room} characters."
                )
            if truncated:
                self.warnings.append(
                    f"Slide {position}: text for the {zone.role} zone of '{pattern.label}' was too long "
                    f"and got truncated (about {zone.max_chars} characters fit)."
                )

        # Zones that play the same part on one slide are read as a set: two
        # column headings at 24 pt and 13 pt look like a mistake, even when each
        # was right on its own. They all take the smallest of their scales.
        for group_scales in scaled.values():
            smallest = min(scale for _, _, scale in group_scales)
            if smallest >= 1.0:
                continue
            for shape, zone, _ in group_scales:
                _set_font_scale(shape, smallest, zone.font_pt)

        for zone in [z for z in pattern.zones if z.role == "image"] + [
            z
            for g in pattern.groups
            for item in g.items
            for z in item
            if z.role == "image"
        ]:
            placed = index.get(zone.key)
            if placed is None:
                continue
            image_id = image_ids.get(zone.key)
            if not image_id:
                if cast(Any, placed.shape).is_placeholder:
                    _remove(placed)
                continue
            prepared = self.images.get(image_id)
            if prepared is None:
                # A bad image reference costs the picture, never the deck.
                self.warnings.append(
                    f"Slide {position}: image '{image_id}' is not a usable image document and was left out."
                )
                if cast(Any, placed.shape).is_placeholder:
                    _remove(placed)
                continue
            self._place_image(slide, placed, prepared)

    @staticmethod
    def _loose_decoration(
        index: Dict[str, PlacedShape], pattern: Pattern
    ) -> List[PlacedShape]:
        """Top-level shapes that carry no content: the icons, card frames and
        connectors a designer draws beside a group rather than inside it."""
        zone_keys = {z.key for z in pattern.zones}
        zone_keys.update(
            z.key for g in pattern.groups for item in g.items for z in item
        )
        # An item's own container is content, not decoration drawn beside it.
        zone_keys.update(key for g in pattern.groups for key in g.item_keys)
        loose = []
        for key, placed in index.items():
            if len(placed.path) != 1 or key in zone_keys or key.startswith("ph:"):
                continue
            shape = cast(Any, placed.shape)
            if (
                getattr(shape, "has_text_frame", False)
                and shape.text_frame.text.strip()
            ):
                continue
            loose.append(placed)
        return loose

    def _remove_decoration(
        self,
        dropped: List[PlacedShape],
        kept: List[PlacedShape],
        index: Dict[str, PlacedShape],
        pattern: Pattern,
    ) -> None:
        """Drop the loose decoration drawn with the unused items.

        A shape goes when it sits on one of them, or anywhere inside the area
        they occupied — a connector between two dropped slots overlaps neither
        by much and used to be left dangling over an empty half-slide. Anything
        that also serves a kept item stays, and so does a full-slide background:
        it reaches beyond the dropped area and touches what was kept.
        """
        dropped_boxes = [_box_of(p) for p in dropped]
        kept_boxes = [_box_of(p) for p in kept]
        area = (
            min(b[0] for b in dropped_boxes),
            min(b[1] for b in dropped_boxes),
            max(b[2] for b in dropped_boxes),
            max(b[3] for b in dropped_boxes),
        )
        for other in self._loose_decoration(index, pattern):
            if other in dropped:
                continue
            box = _box_of(other)
            on_dropped = any(_covered(box, b) >= 0.5 for b in dropped_boxes)
            if not on_dropped and _covered(box, area) < 0.9:
                continue
            if any(_covered(box, b) >= 0.2 for b in kept_boxes):
                continue
            _remove(other)

    def _recentre_items(
        self,
        kept: List[PlacedShape],
        dropped: List[PlacedShape],
        index: Dict[str, PlacedShape],
        pattern: Pattern,
    ) -> None:
        """Slide the used items back to the middle of the room the group had.

        Four cards of a six-card row left at the designer's coordinates hug the
        left edge with a third of the slide empty beside them. A translation
        only: the corporate spacing and sizing are untouched.
        """
        used = [_box_of(p) for p in kept]
        whole = used + [_box_of(p) for p in dropped]
        shift_x = ((min(b[0] for b in whole) + max(b[2] for b in whole)) // 2) - (
            (min(b[0] for b in used) + max(b[2] for b in used)) // 2
        )
        shift_y = ((min(b[1] for b in whole) + max(b[3] for b in whole)) // 2) - (
            (min(b[1] for b in used) + max(b[3] for b in used)) // 2
        )
        if abs(shift_x) < _RECENTRE_MIN_EMU and abs(shift_y) < _RECENTRE_MIN_EMU:
            return
        # The icons and frames drawn over a kept item belong to it and move with
        # it; anything else on the slide stays where the designer put it.
        movers = list(kept)
        for other in self._loose_decoration(index, pattern):
            box = _box_of(other)
            if any(_covered(box, b) >= 0.5 for b in used):
                movers.append(other)
        for placed in movers:
            shape = cast(Any, placed.shape)
            try:
                shape.left = Emu(shape.left + shift_x)
                shape.top = Emu(shape.top + shift_y)
            except (TypeError, ValueError):
                continue

    def _even_out_item_widths(
        self, group: RepeatGroup, index: Dict[str, PlacedShape]
    ) -> None:
        """Widen a text box narrower than its siblings of the same role: designers
        size sample boxes to their sample text, and the narrow one would wrap."""
        for position in range(len(group.item_zones)):
            zones = [item[position] for item in group.items if position < len(item)]
            if not zones or zones[0].role == "image":
                continue
            widest = max(z.box.w for z in zones)
            for zone in zones:
                if zone.box.w < widest * 0.8:
                    placed = index.get(zone.key)
                    if placed is not None and placed.width > 0:
                        # `placed.width` is absolute, `.width` is in the group's
                        # own units: scale the target through that ratio.
                        target = widest / 1000 * self.width
                        shape = cast(Any, placed.shape)
                        shape.width = Emu(round(target * shape.width / placed.width))

    def _no_wrap_scale(
        self,
        zone: Zone,
        lines: List[_Line],
        placed: PlacedShape,
        container: Optional[PlacedShape],
        text_below: bool = False,
        font_name: Optional[str] = None,
        bold: bool = False,
    ) -> Tuple[Optional[float], Optional[int]]:
        """Keep a box that grows with its text (a KPI figure, its caption)
        inside its card, identically in PowerPoint and in the PDF preview.

        The room runs to the card's right edge (or the slide's). A box too
        narrow for its text is widened to that room. A figure stays on one line
        and shrinks as needed; a one-line heading or label with text right below
        it shrinks down to the overflow floor, then wraps and returns how many
        characters would fit, so the agent shortens it; other text wraps between words and only shrinks
        for a word longer than the room. Returns ``(font scale, one-line room)``.
        """
        if not zone.font_pt or placed.width <= 0:
            return None, None
        right = (
            container.left + container.width
            if container is not None and container.width > 0
            else int(self.width * 0.95)
        )
        room = int((right - placed.left) * 0.95)
        if room <= 0:
            return None, None
        shape_width = getattr(cast(Any, placed.shape), "width", 0) or placed.width
        # `placed.width` is absolute, the insets are in the shape's own units:
        # inside a scaled group the two are not the same ruler.
        insets = _text_insets(cast(Any, placed.shape)) * placed.width / shape_width
        inner = placed.width - insets
        emu_per_em = zone.font_pt / 72 * 914400
        texts = [line.text for line in lines]
        needed = (
            max((text_metrics.width_em(t, font_name, bold) for t in texts), default=0.0)
            * emu_per_em
        )
        longest_word = (
            max(
                (
                    text_metrics.width_em(w, font_name, bold)
                    for t in texts
                    for w in t.split()
                ),
                default=0.0,
            )
            * emu_per_em
        )
        if needed * _NO_WRAP_MARGIN <= inner:
            return None, None
        shape = cast(Any, placed.shape)
        # The margin absorbs the difference between these metrics and the
        # renderer's own: without it a box sized to the exact text wraps anyway.
        target = min(needed * _NO_WRAP_MARGIN + insets, room)
        # Only ever widen. The room is capped below the container, so a box the
        # designer drew wider than that cap used to be cut back — the opposite
        # of what a text too wide for its box needs.
        if target > placed.width and shape.width:
            shape.width = Emu(round(target * shape.width / placed.width))
        fitted = needed * _NO_WRAP_MARGIN
        if zone.role == "number":
            return (round(max(0.4, room / fitted), 2) if fitted > room else None), None
        if fitted <= room:
            return None, None
        if (
            zone.role in ("heading", "label")
            and text_below
            and (zone.max_lines or 1) <= 1
            and len(texts) == 1
        ):
            if room / fitted >= MIN_FONT_SCALE:
                return round(room / fitted, 2), None
            shrunk = MIN_FONT_SCALE
            per_char = (
                text_metrics.char_em(font_name, bold) or text_metrics.FALLBACK_CHAR_EM
            ) * emu_per_em
            fits = int(room / (per_char * shrunk * _NO_WRAP_MARGIN))
        else:
            shrunk, fits = None, None
        bodyPr = shape.text_frame._txBody.find(qn("a:bodyPr"))
        if bodyPr is not None:
            bodyPr.set("wrap", "square")
        word_scale = room / (longest_word * _NO_WRAP_MARGIN) if longest_word else 1.0
        if word_scale < (shrunk or 1.0):
            # A single unbreakable token - an e-mail address, a URL - set the
            # size for its whole zone and took it down to 7 pt. Below the floor
            # the token overflows its measured box instead; it still fits the
            # card, and the text around it stays readable.
            floor = 0.4 if zone.role == "number" else MIN_FONT_SCALE
            shrunk = round(max(floor, word_scale), 2)
        return shrunk, fits

    @staticmethod
    def _fillable_text_zones(pattern: Pattern) -> List[Zone]:
        zones = [z for z in pattern.zones if z.role not in ("image", "keep")]
        for group in pattern.groups:
            for item in group.items:
                zones.extend(z for z in item if z.role not in ("image", "keep"))
        return zones

    def _place_image(self, slide, placed: PlacedShape, prepared: PreparedImage) -> None:
        image_bytes, img_w, img_h = prepared
        shape = cast(Any, placed.shape)
        if shape.is_placeholder and hasattr(shape, "insert_picture"):
            shape.insert_picture(io.BytesIO(image_bytes))
            return
        left, top, width, height = fit_inside_box(
            img_w, img_h, placed.left, placed.top, placed.width, placed.height
        )
        picture = slide.shapes.add_picture(
            io.BytesIO(image_bytes), Emu(left), Emu(top), Emu(width), Emu(height)
        )
        # `add_picture` appends, which puts the new picture in front of
        # everything: a replaced cover photo then hides the title drawn over it.
        # Put it back where the one it replaces sat in the drawing order.
        element = cast(Any, placed.shape)._element
        anchor = element
        while anchor.getparent() is not None and anchor.getparent().tag != qn(
            "p:spTree"
        ):
            anchor = anchor.getparent()
        tree = anchor.getparent()
        if tree is not None:
            new_element = picture._element
            new_element.getparent().remove(new_element)
            tree.insert(list(tree).index(anchor), new_element)
        _remove(placed)


def render_deck(
    template_bytes: bytes,
    inventory: TemplateInventory,
    plan: DeckPlan,
    images: Optional[Mapping[str, PreparedImage]] = None,
) -> RenderResult:
    """Render ``plan`` on the template (CPU-bound; call off the event loop).

    Raises :class:`RenderError` for a plan the template cannot honour
    (unknown or excluded pattern, missing image); anything else propagates.
    """
    presentation = Presentation(io.BytesIO(template_bytes))
    try:
        return _Renderer(presentation, inventory, images or {}).render(plan)
    except ValueError as exc:
        raise RenderError(str(exc)) from exc
