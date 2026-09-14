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

from fred_capability_ppt_filler.builder.analysis import estimate_capacity
from fred_capability_ppt_filler.builder.models import (
    Pattern,
    RepeatGroup,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.plan import DeckPlan, SlidePlan, resolve
from fred_capability_ppt_filler.images import fit_inside_box
from fred_capability_ppt_filler.inline_markdown import parse_inline_markdown
from fred_capability_ppt_filler.traversal import PlacedShape, walk_shapes

# Smallest font scale the overflow control applies before truncating.
MIN_FONT_SCALE = 0.7
# Sub-bullets get narrower lines: this factor per level in the capacity estimate.
_LEVEL_WIDTH_FACTOR = 0.85

_R_ATTRS = (qn("r:embed"), qn("r:link"), qn("r:id"), qn("r:pict"))
_SKIPPED_RELS = ("/slideLayout", "/notesSlide")

PreparedImage = Tuple[bytes, int, int]


@dataclass
class RenderResult:
    pptx: bytes
    # Human-readable notes for the agent: truncations, substitutions, unfilled images.
    warnings: List[str] = field(default_factory=list)
    slide_count: int = 0


@dataclass
class _Line:
    text: str
    level: int = 0


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
                for attr in _R_ATTRS:
                    old = node.get(attr)
                    if old is not None and old in rid_map:
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


def _set_font_scale(shape, scale: float) -> None:
    """Shrink a text frame through ``normAutofit`` (``fontScale`` in 1/1000 %)."""
    bodyPr = shape.text_frame._txBody.find(qn("a:bodyPr"))
    if bodyPr is None:
        return
    for child in list(bodyPr):
        if child.tag in (qn("a:noAutofit"), qn("a:spAutoFit"), qn("a:normAutofit")):
            bodyPr.remove(child)
    autofit = bodyPr.makeelement(qn("a:normAutofit"), {})
    autofit.set("fontScale", str(int(scale * 100000)))
    autofit.set("lnSpcReduction", "10000")
    bodyPr.append(autofit)


def _grows_with_text(shape) -> bool:
    """A box that does not wrap, or auto-sizes to its text, has no capacity to enforce."""
    bodyPr = shape.text_frame._txBody.find(qn("a:bodyPr"))
    if bodyPr is None:
        return False
    return bodyPr.get("wrap") == "none" or bodyPr.find(qn("a:spAutoFit")) is not None


def _fit(
    zone: Zone, lines: List[_Line], width: int, height: int
) -> Tuple[List[_Line], Optional[float], bool]:
    """Fit ``lines`` into ``zone``: returns ``(lines, font scale or None, truncated)``."""
    max_chars, max_lines = estimate_capacity(
        zone.box, zone.font_pt, zone.role, width, height
    )
    chars_per_line = max(1, max_chars // max(1, max_lines))

    def needed(scale: float) -> int:
        cpl = chars_per_line / scale
        return sum(
            max(1, math.ceil(len(line.text) / (cpl * _LEVEL_WIDTH_FACTOR**line.level)))
            for line in lines
        )

    if needed(1.0) <= max_lines:
        return lines, None, False
    scale = max_lines / needed(1.0)
    if scale >= MIN_FONT_SCALE:
        return lines, round(scale, 2), False

    capacity = max_lines / MIN_FONT_SCALE
    cpl = chars_per_line / MIN_FONT_SCALE
    kept: List[_Line] = []
    used = 0.0
    for line in lines:
        cost = max(
            1, math.ceil(len(line.text) / (cpl * _LEVEL_WIDTH_FACTOR**line.level))
        )
        if used + cost > capacity:
            room = int((capacity - used) * cpl) - 1
            if room > 12 and not kept:
                kept.append(_Line(_cut(line.text, room), line.level))
            break
        kept.append(line)
        used += cost
    return kept, MIN_FONT_SCALE, True


def _cut(text: str, room: int) -> str:
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


def _assign_text(pattern: Pattern, plan: SlidePlan) -> Dict[str, List[_Line]]:
    """Decide which lines go into which text zone (by zone key)."""
    zmap = _ZoneMap(pattern)
    out: Dict[str, List[_Line]] = {}

    def put(zone: Optional[Zone], lines: List[_Line]) -> None:
        if zone is not None and lines:
            out[zone.key] = lines

    title = _lines_from_bullets([plan.title]) if plan.title else []
    subtitle = _lines_from_bullets([plan.subtitle]) if plan.subtitle else []
    bullets = _lines_from_bullets(plan.bullets)

    if zmap.titles:
        put(zmap.titles[0], title)
    elif zmap.headings and title and not plan.columns:
        put(zmap.headings[0], title)

    if pattern.intent in ("title", "section", "statement"):
        # Covers put their subtitle in whatever sits under the title.
        target = zmap.subtitles or zmap.body_like()
        put(target[0] if target else None, subtitle or bullets)
        return out

    if zmap.subtitles:
        put(zmap.subtitles[0], subtitle)
    elif subtitle and not bullets and zmap.bodies:
        bullets = subtitle

    if plan.columns:
        for index, column in enumerate(plan.columns):
            body = zmap.bodies[index] if index < len(zmap.bodies) else None
            heading = zmap.headings[index] if index < len(zmap.headings) else None
            lines = _lines_from_bullets(column.bullets)
            if column.heading and heading is not None:
                put(heading, _lines_from_bullets([column.heading]))
            elif column.heading:
                lines = [_Line(f"**{column.heading}**")] + lines
            put(body, lines)
        return out

    if pattern.intent == "contact" and bullets:
        for zone, line in zip(zmap.stacked(), bullets):
            put(zone, [line])
        return out
    bodies = zmap.body_like()
    if not bullets or not bodies:
        return out
    if len(bodies) > 1 and pattern.intent in ("two_columns", "comparison"):
        half = math.ceil(len(bullets) / 2)
        put(bodies[0], bullets[:half])
        put(bodies[1], bullets[half:])
    else:
        put(bodies[0], bullets)
    return out


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
        self.slides_by_id = {slide.slide_id: slide for slide in presentation.slides}

    def render(self, plan: DeckPlan) -> RenderResult:
        original_ids = list(self.slides_by_id)
        for position, slide_plan in enumerate(plan.slides, start=1):
            resolution = resolve(self.inventory, slide_plan.pattern)
            pattern = resolution.pattern
            if resolution.substituted_from:
                self.warnings.append(
                    f"Slide {position}: no '{resolution.substituted_from}' pattern in this template, "
                    f"used '{pattern.label}' ({pattern.intent}) instead."
                )
            slide = self._create(pattern)
            if pattern.intent != "fixed":
                self._fill(slide, pattern, slide_plan, position)
            if slide_plan.notes:
                slide.notes_slide.notes_text_frame.text = slide_plan.notes
            elif slide.has_notes_slide and pattern.source == "slide":
                slide.notes_slide.notes_text_frame.text = ""
        _remove_slides(self.prs, original_ids)
        buffer = io.BytesIO()
        self.prs.save(buffer)
        return RenderResult(
            pptx=buffer.getvalue(), warnings=self.warnings, slide_count=len(plan.slides)
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
        text = _assign_text(pattern, plan)
        image_ids: Dict[str, Optional[str]] = {}
        zmap = _ZoneMap(pattern)
        plan_images = list(plan.images) or ([plan.image] if plan.image else [])
        for zone, image_id in zip(zmap.images, plan_images + [None] * len(zmap.images)):
            image_ids[zone.key] = image_id

        for group in pattern.groups:
            group_text, group_images, used = _assign_group(group, plan)
            text.update(group_text)
            image_ids.update(group_images)
            if len(plan.items) > group.count:
                self.warnings.append(
                    f"Slide {position}: '{pattern.label}' holds {group.count} items, "
                    f"{len(plan.items) - group.count} were dropped."
                )
            kept_boxes = []
            for item_key in group.item_keys[:used]:
                kept = index.get(item_key)
                if kept is not None:
                    kept_boxes.append(
                        (
                            kept.left,
                            kept.top,
                            kept.left + kept.width,
                            kept.top + kept.height,
                        )
                    )
            for item_key in group.item_keys[used:]:
                placed = index.get(item_key)
                if placed is not None:
                    self._remove_with_decoration(placed, index, pattern, kept_boxes)
            self._even_out_item_widths(group, index)

        for zone in self._fillable_text_zones(pattern):
            placed = index.get(zone.key)
            shape = cast(Any, placed.shape) if placed is not None else None
            if shape is None or not getattr(shape, "has_text_frame", False):
                continue
            lines = text.get(zone.key, [])
            if not lines:
                _clear_text(shape)
                continue
            if _grows_with_text(shape):
                scale, truncated = None, False
            else:
                lines, scale, truncated = _fit(zone, lines, self.width, self.height)
            _write_lines(shape, lines)
            if scale is not None:
                _set_font_scale(shape, scale)
            if truncated:
                self.warnings.append(
                    f"Slide {position}: text for the {zone.role} zone of '{pattern.label}' was too long "
                    f"and got truncated (about {zone.max_chars} characters fit)."
                )

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
                raise RenderError(
                    f"Slide {position}: image '{image_id}' is not available; list the folder again and "
                    "pass a document_id returned by list_images_in_folder."
                )
            self._place_image(slide, placed, prepared)

    @staticmethod
    def _remove_with_decoration(
        placed: PlacedShape,
        index: Dict[str, PlacedShape],
        pattern: Pattern,
        kept_boxes: List[Tuple[int, int, int, int]],
    ) -> None:
        """Drop an unused item and the loose decoration drawn with it (an icon
        or a card frame the designer left outside the group). A shape survives
        when it is a zone, carries text, or also serves a kept item — a
        full-slide background touches every item and stays."""
        zone_keys = {z.key for z in pattern.zones}
        zone_keys.update(
            z.key for g in pattern.groups for item in g.items for z in item
        )
        item_box = (
            placed.left,
            placed.top,
            placed.left + placed.width,
            placed.top + placed.height,
        )
        for key, other in list(index.items()):
            if (
                other is placed
                or len(other.path) != 1
                or key in zone_keys
                or key.startswith("ph:")
            ):
                continue
            other_shape = cast(Any, other.shape)
            if (
                getattr(other_shape, "has_text_frame", False)
                and other_shape.text_frame.text.strip()
            ):
                continue
            other_box = (
                other.left,
                other.top,
                other.left + other.width,
                other.top + other.height,
            )
            if _overlap_ratio(other_box, item_box) < 0.5:
                continue
            if any(_overlap_ratio(other_box, kept) >= 0.2 for kept in kept_boxes):
                continue
            _remove(other)
        _remove(placed)

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
                    if placed is not None:
                        cast(Any, placed.shape).width = Emu(
                            round(widest / 1000 * self.width)
                        )

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
        slide.shapes.add_picture(
            io.BytesIO(image_bytes), Emu(left), Emu(top), Emu(width), Emu(height)
        )
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
