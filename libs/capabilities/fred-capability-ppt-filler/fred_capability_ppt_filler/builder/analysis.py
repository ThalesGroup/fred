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

"""Template analysis: from a plain ``.pptx`` to a :class:`TemplateInventory`.

Deterministic and offline. One pass over each layout and slide collects a flat
list of shape records (kind, geometry, text, font size, placeholder type);
every rule below works on those records, never on the XML again.

Rule order, most to least reliable (design.md D3): typed placeholders, shared
decoration, sample-text lexicon, repeated groups, free boxes by geometry and
font rank, then intent and exclusion. Optional annotations (shape names,
``intent:`` notes) override the corresponding heuristic.
"""

from __future__ import annotations

import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.models import (
    AnalysisError,
    AnalyzeResult,
    Box,
    Intent,
    Pattern,
    RepeatGroup,
    TemplateInventory,
    Zone,
    ZoneRole,
)
from fred_capability_ppt_filler.traversal import KEY_PATTERN, walk_shapes

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pptx.shapes.base import BaseShape

CODE_INVALID_UPLOAD = "invalid_upload"

# A relationship of these kinds can be re-created on a duplicated slide; any
# other part (chart, SmartArt, OLE) makes the slide uncopyable.
COPYABLE_REL_SUFFIXES = (
    "/image",
    "/audio",
    "/video",
    "/media",
    "/hyperlink",
    "/slideLayout",
    "/notesSlide",
    "/tags",
    "/customXml",
)

# Default font sizes per role when the run carries none (inherited from the
# layout/master), used only for the capacity estimate.
_DEFAULT_PT: Dict[str, float] = {
    "title": 32.0,
    "subtitle": 20.0,
    "heading": 20.0,
    "body": 16.0,
    "caption": 12.0,
    "number": 40.0,
    "label": 12.0,
}

# Text repeated on this many slides is decoration (footer, confidentiality).
_SHARED_TEXT_MIN_SLIDES = 3
# A free picture covering this share of the slide is content, not decoration.
_REPLACEABLE_PICTURE_AREA = 0.25
# A chart/table covering this share of the slide is the slide's content.
_MAIN_CONTENT_AREA = 0.15
_ICON_BANK_PICTURES = 20


@dataclass
class _Rec:
    key: str
    path: Tuple[int, ...]
    kind: str  # text | picture | table | chart | group | other
    ph_type: Optional[str]
    ph_idx: Optional[int]
    box: Box
    area: float
    text: str
    font_pt: Optional[float]
    lines: int
    name: str
    shape: "BaseShape" = field(repr=False)

    @property
    def words(self) -> int:
        return len(self.text.split())


def _text_of(shape) -> str:
    return shape.text_frame.text.replace("\x0b", "\n").strip()


def _font_pt_of(shape) -> Optional[float]:
    best: Optional[float] = None
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            size = run.font.size
            if size is not None:
                pt = size.pt
                if best is None or pt > best:
                    best = pt
    return best


def _lst_style_pt(element) -> Optional[float]:
    """First-level default size declared in an element's ``a:lstStyle``/``a:lvl1pPr``."""
    if element is None:
        return None
    node = element.find(f".//{qn('a:lvl1pPr')}/{qn('a:defRPr')}")
    if node is None:
        return None
    size = node.get("sz")
    return int(size) / 100 if size else None


def _placeholder_pt(shape, layout, master) -> Optional[float]:
    """Font size a placeholder inherits when its runs carry none: its own list
    style, then the layout's and master's matching placeholder, then the
    master's title/body text styles. Enough for a capacity estimate."""
    own = _lst_style_pt(shape._element.find(f".//{qn('a:lstStyle')}"))
    if own:
        return own
    fmt = shape.placeholder_format
    for holder in (layout, master):
        if holder is None:
            continue
        for candidate in holder.placeholders:
            cfmt = candidate.placeholder_format
            if cfmt.idx == fmt.idx or (cfmt.type == fmt.type and fmt.type is not None):
                pt = _font_pt_of(candidate) if candidate.has_text_frame else None
                pt = pt or _lst_style_pt(
                    candidate._element.find(f".//{qn('a:lstStyle')}")
                )
                if pt:
                    return pt
                break
    if master is None:
        return None
    styles = master._element.find(qn("p:txStyles"))
    if styles is None:
        return None
    is_title = fmt.type is not None and fmt.type.name in ("TITLE", "CENTER_TITLE")
    return _lst_style_pt(styles.find(qn("p:titleStyle" if is_title else "p:bodyStyle")))


def _placeholder_key(shape) -> str:
    return f"ph:{shape.placeholder_format.idx}"


def _shape_key(path: Tuple[int, ...]) -> str:
    return "sp:" + "/".join(str(part) for part in path)


def _records(shapes, width: int, height: int, layout=None, master=None) -> List[_Rec]:
    """Flatten ``shapes`` (groups included) into records with per-mille boxes.

    ``layout``/``master`` let a placeholder without explicit run sizes report
    the size it inherits, which the capacity estimate needs.
    """
    slide_area = float(width * height) or 1.0
    records: List[_Rec] = []
    for placed in walk_shapes(shapes):
        shape = cast(Any, placed.shape)
        box = Box(
            x=round(placed.left * 1000 / width),
            y=round(placed.top * 1000 / height),
            w=round(placed.width * 1000 / width),
            h=round(placed.height * 1000 / height),
        )
        area = (placed.width * placed.height) / slide_area
        ph_type = ph_idx = None
        if shape.is_placeholder:
            fmt = shape.placeholder_format
            ph_type = fmt.type.name if fmt.type is not None else None
            ph_idx = fmt.idx
        shape_type = shape.shape_type
        text = ""
        font_pt = None
        lines = 0
        if shape_type == MSO_SHAPE_TYPE.GROUP:
            kind = "group"
        elif getattr(shape, "has_chart", False):
            kind = "chart"
        elif getattr(shape, "has_table", False):
            kind = "table"
        elif shape_type == MSO_SHAPE_TYPE.PICTURE or ph_type == "PICTURE":
            kind = "picture"
        elif shape.has_text_frame:
            kind = "text"
            text = _text_of(shape)
            font_pt = _font_pt_of(shape)
            if font_pt is None and ph_idx is not None:
                font_pt = _placeholder_pt(shape, layout, master)
            lines = text.count("\n") + 1 if text else 0
        else:
            kind = "other"
        key = _placeholder_key(shape) if ph_idx is not None else _shape_key(placed.path)
        records.append(
            _Rec(
                key=key,
                path=placed.path,
                kind=kind,
                ph_type=ph_type,
                ph_idx=ph_idx,
                box=box,
                area=area,
                text=text,
                font_pt=font_pt,
                lines=lines,
                name=shape.name or "",
                shape=shape,
            )
        )
    return records


def estimate_capacity(
    box: Box, font_pt: Optional[float], role: str, width_emu: int, height_emu: int
) -> Tuple[int, int]:
    """Rough (max_chars, max_lines) from the box and the font size.

    Average glyph width 0.5em, line height 1.2em; 10 % safety margin. No font
    metrics are available server-side, so this is deliberately conservative.
    """
    pt = font_pt or _DEFAULT_PT.get(role, 16.0)
    width_in = box.w / 1000 * width_emu / 914400
    height_in = box.h / 1000 * height_emu / 914400
    chars_per_line = max(1, int(width_in * 72 / (pt * 0.5)))
    lines = max(1, int(height_in * 72 / (pt * 1.2)))
    return int(chars_per_line * lines * 0.9), lines


def _zone(rec: _Rec, role: ZoneRole, width: int, height: int) -> Zone:
    max_chars = max_lines = None
    if role != "image" and role != "keep":
        max_chars, max_lines = estimate_capacity(
            rec.box, rec.font_pt, role, width, height
        )
    return Zone(
        key=rec.key,
        role=role,
        box=rec.box,
        sample=rec.text[:80],
        font_pt=rec.font_pt,
        max_chars=max_chars,
        max_lines=max_lines,
    )


def _is_top_band(rec: _Rec) -> bool:
    return rec.box.y < 120 and rec.box.h < 80


def _promote_headings(zones: List[Zone]) -> None:
    """A short body placeholder sitting right above another body in the same
    column is that column's heading (the Comparison layout shape)."""
    bodies = [z for z in zones if z.role == "body"]
    for zone in bodies:
        if zone.box.h >= 100:
            continue
        for other in bodies:
            # Only a tall body below counts as a column: contact cards stack
            # short lines and those are all bodies.
            if other is zone or other.box.y <= zone.box.y or other.box.h < 150:
                continue
            overlap = min(zone.box.x + zone.box.w, other.box.x + other.box.w) - max(
                zone.box.x, other.box.x
            )
            if (
                overlap > zone.box.w * 0.5
                and other.box.y - (zone.box.y + zone.box.h) < 60
            ):
                zone.role = "heading"
                break


def _placeholder_role(rec: _Rec) -> Optional[ZoneRole]:
    """Role implied by a placeholder type; None for the chrome placeholders."""
    ph = rec.ph_type
    if ph in ("TITLE", "CENTER_TITLE"):
        return "title"
    if ph == "SUBTITLE":
        return "subtitle"
    if ph in ("BODY", "OBJECT"):
        # A body placeholder on the top band is a column heading (some
        # templates type their headings as BODY), not a bullet area.
        return "heading" if _is_top_band(rec) and rec.box.w < 600 else "body"
    if ph == "PICTURE":
        return "image"
    return None


def _declared_role(rec: _Rec) -> Optional[str]:
    return lexicon.role_from_shape_name(rec.name)


class _Analyzer:
    def __init__(self, presentation) -> None:
        self.prs = presentation
        self.width = presentation.slide_width
        self.height = presentation.slide_height
        self.shared_texts: set[str] = set()

    # -- entry -----------------------------------------------------------------

    def run(self) -> TemplateInventory:
        slides = list(self.prs.slides)
        slide_records = [
            _records(
                slide.shapes,
                self.width,
                self.height,
                slide.slide_layout,
                slide.slide_layout.slide_master,
            )
            for slide in slides
        ]
        self.shared_texts = self._shared_texts(slide_records)

        patterns: List[Pattern] = []
        layout_zone_sets: Dict[str, frozenset] = {}
        # One running index over every master, matching the renderer's view.
        layouts = [
            layout
            for master in self.prs.slide_masters
            for layout in master.slide_layouts
        ]
        for index, layout in enumerate(layouts):
            if True:
                pattern = self._layout_pattern(layout, index)
                patterns.append(pattern)
                if pattern.included:
                    layout_zone_sets[layout.name] = frozenset(
                        z.key for z in pattern.zones
                    )

        for number, (slide, records) in enumerate(zip(slides, slide_records), start=1):
            pattern = self._slide_pattern(slide, number, records)
            if pattern is None:
                continue
            # A pure instance of a layout (same placeholders, nothing else on
            # the slide) renders identically: keep the layout, drop the copy.
            zone_keys = frozenset(z.key for z in pattern.zones)
            extra_content = any(
                rec.kind in ("chart", "table", "picture")
                or (rec.kind == "text" and rec.ph_idx is None and rec.text)
                for rec in records
            )
            if (
                not pattern.groups
                and not extra_content
                and zone_keys == layout_zone_sets.get(slide.slide_layout.name, None)
                and all(z.key.startswith("ph:") for z in pattern.zones)
            ):
                continue
            patterns.append(pattern)

        layout_intents = {
            p.intent for p in patterns if p.source == "layout" and p.included
        }
        for pattern in patterns:
            # A fixed slide is used verbatim, so "the designer's version" means
            # nothing there: a decorative example must not outrank a closing layout.
            if (
                pattern.source == "slide"
                and pattern.included
                and pattern.intent != "fixed"
                and pattern.intent in layout_intents
            ):
                pattern.preferred = True

        return TemplateInventory(
            slide_width=self.width,
            slide_height=self.height,
            patterns=patterns,
            shared_texts=sorted(self.shared_texts),
        )

    # -- shared decoration -------------------------------------------------------

    @staticmethod
    def _shared_texts(slide_records: Sequence[Sequence[_Rec]]) -> set[str]:
        counter: Counter[str] = Counter()
        for records in slide_records:
            seen = {
                rec.text
                for rec in records
                if rec.kind == "text" and rec.ph_idx is None and len(rec.text) >= 3
            }
            counter.update(seen)
        return {
            text for text, count in counter.items() if count >= _SHARED_TEXT_MIN_SLIDES
        }

    # -- layouts -----------------------------------------------------------------

    def _layout_pattern(self, layout, index: int) -> Pattern:
        records = _records(
            layout.placeholders, self.width, self.height, None, layout.slide_master
        )
        zones: List[Zone] = []
        for rec in records:
            role = _placeholder_role(rec)
            if role is None:
                continue
            zones.append(_zone(rec, role, self.width, self.height))
        _promote_headings(zones)
        name = layout.name or f"Layout {index + 1}"
        pattern = Pattern(
            id=f"layout:{index}",
            source="layout",
            source_index=index,
            name=name,
            label=name,
            intent="fixed",
            zones=zones,
        )
        if not zones:
            if lexicon.name_matches(name, lexicon.CLOSING_NAMES):
                pattern.intent = "fixed"
            else:
                pattern.included = False
                pattern.exclusion_reason = "no_placeholder"
            return pattern
        pattern.intent = self._intent(pattern, records, name)
        return pattern

    # -- slides --------------------------------------------------------------------

    def _slide_pattern(
        self, slide, number: int, records: List[_Rec]
    ) -> Optional[Pattern]:
        layout_name = slide.slide_layout.name or ""
        zones: List[Zone] = []
        groups: List[RepeatGroup] = []
        warnings: List[str] = []

        # 1. Typed placeholders keep their meaning. A designer who duplicated
        # a placeholder left two shapes with one idx: the second is addressed
        # by its shape path so both stay fillable.
        title_text = ""
        used_keys: set[str] = set()
        for rec in records:
            if rec.ph_idx is None:
                continue
            role = _placeholder_role(rec)
            if role is None:
                continue
            declared = _declared_role(rec)
            if declared == "keep":
                continue
            if declared and declared != "image":
                role = cast(ZoneRole, declared)
            if role == "title" and not title_text:
                title_text = rec.text
            zone = _zone(rec, role, self.width, self.height)
            if zone.key in used_keys:
                zone.key = _shape_key(rec.path)
            used_keys.add(zone.key)
            zones.append(zone)
        _promote_headings(zones)

        # 2. Repeated sibling groups.
        groups, grouped_paths = self._repeat_groups(records)

        # 3. Free text boxes outside the groups.
        free_text = [
            rec
            for rec in records
            if rec.kind == "text"
            and rec.ph_idx is None
            and rec.text
            and (rec.text not in self.shared_texts or lexicon.is_sample_text(rec.text))
            and rec.path[0] not in grouped_paths
        ]
        has_title = any(z.role == "title" for z in zones)
        zones.extend(self._free_text_zones(free_text, has_title))
        if not title_text:
            title_text = next((z.sample for z in zones if z.role == "title"), "")

        # 4. Free pictures large enough to be content.
        for rec in records:
            if (
                rec.kind == "picture"
                and rec.ph_idx is None
                and rec.path[0] not in grouped_paths
            ):
                declared = _declared_role(rec)
                if declared == "keep":
                    continue
                if declared == "image" or rec.area >= _REPLACEABLE_PICTURE_AREA:
                    zones.append(_zone(rec, "image", self.width, self.height))

        pattern = Pattern(
            id=f"slide:{slide.slide_id}",
            source="slide",
            source_index=number,
            name=layout_name,
            label=self._slide_label(title_text, layout_name, number),
            intent="fixed",
            zones=zones,
            groups=groups,
            warnings=warnings,
        )

        # 5. Exclusions.
        self._apply_exclusions(pattern, slide, records)

        # 6. Intent, with the notes directive on top.
        pattern.intent = self._intent(
            pattern, records, layout_name, slide_number=number
        )
        if slide.has_notes_slide:
            frame = slide.notes_slide.notes_text_frame
            notes = frame.text if frame is not None else ""
            match = lexicon.INTENT_NOTE.search(notes)
            if match and match.group(1) in Intent.__args__:  # type: ignore[attr-defined]
                pattern.intent = match.group(1)  # type: ignore[assignment]
            label = lexicon.LABEL_NOTE.search(notes)
            if label:
                pattern.label = label.group(1)[:60]
        return pattern

    def _slide_label(self, title_text: str, layout_name: str, number: int) -> str:
        if (
            title_text
            and not lexicon.is_sample_text(title_text)
            and title_text not in self.shared_texts
        ):
            return " ".join(title_text.split())[:60]
        return f"{layout_name or 'Slide'} ({number})"

    # -- repeated groups -------------------------------------------------------------

    def _repeat_groups(self, records: List[_Rec]) -> Tuple[List[RepeatGroup], set[int]]:
        by_group: Dict[int, List[_Rec]] = defaultdict(list)
        group_recs: Dict[int, _Rec] = {}
        for rec in records:
            if rec.kind == "group" and len(rec.path) == 1:
                group_recs[rec.path[0]] = rec
            elif len(rec.path) > 1 and rec.kind in ("text", "picture"):
                by_group[rec.path[0]].append(rec)

        signatures: Dict[tuple, List[int]] = defaultdict(list)
        for group_id, children in by_group.items():
            texts = [c for c in children if c.kind == "text" and c.text]
            if not texts:
                continue
            # Structure only (font sizes, picture count): sibling cards differ
            # in box sizes by a few per cent, never in structure.
            signature = tuple(sorted(round(c.font_pt or 0) for c in texts)) + (
                sum(1 for c in children if c.kind == "picture"),
            )
            signatures[signature].append(group_id)

        groups: List[RepeatGroup] = []
        grouped: set[int] = set()
        for signature, group_ids in signatures.items():
            if len(group_ids) < 3:
                continue
            ordered = sorted(
                group_ids,
                key=lambda gid: (group_recs[gid].box.y // 40, group_recs[gid].box.x),
            )
            item_roles: Optional[List[ZoneRole]] = None
            items: List[List[Zone]] = []
            for gid in ordered:
                children = sorted(
                    (c for c in by_group[gid] if c.kind == "text" and c.text),
                    key=lambda c: (c.box.y, c.box.x),
                )
                roles = self._item_roles(children)
                if item_roles is None:
                    item_roles = roles
                elif roles != item_roles:
                    # Same signature but a different reading: keep the first
                    # item's roles so every item has the same shape.
                    roles = item_roles
                items.append(
                    [
                        _zone(c, r, self.width, self.height)
                        for c, r in zip(children, roles)
                        if r != "keep"
                    ]
                )
            grouped.update(ordered)
            groups.append(
                RepeatGroup(
                    key=_shape_key((ordered[0],)),
                    count=len(ordered),
                    item_zones=[r for r in (item_roles or []) if r != "keep"],
                    items=items,
                    item_keys=[_shape_key((gid,)) for gid in ordered],
                )
            )
        groups.sort(key=lambda g: -g.count)
        return groups, grouped

    @staticmethod
    def _item_roles(children: List[_Rec]) -> List[ZoneRole]:
        roles: List[Optional[ZoneRole]] = [None] * len(children)
        for i, rec in enumerate(children):
            declared = _declared_role(rec)
            if declared:
                roles[i] = declared  # type: ignore[assignment]
            elif lexicon.is_numberish(rec.text):
                roles[i] = "number"
        rest = [i for i, r in enumerate(roles) if r is None]
        if not rest:
            return [r or "body" for r in roles]
        has_number = any(r == "number" for r in roles)
        ranked = sorted(rest, key=lambda i: -(children[i].font_pt or 0))
        if len(rest) == 1:
            rec = children[rest[0]]
            if has_number:
                roles[rest[0]] = (
                    "label" if rec.words <= 4 and rec.box.h <= 60 else "heading"
                )
            else:
                roles[rest[0]] = (
                    "label" if rec.box.h <= 60 and rec.words <= 4 else "body"
                )
        else:
            roles[ranked[0]] = "heading"
            for i in ranked[1:]:
                rec = children[i]
                roles[i] = "label" if rec.box.h <= 40 and rec.words <= 4 else "body"
        return [r or "body" for r in roles]

    # -- free text ---------------------------------------------------------------------

    def _free_text_zones(self, free_text: List[_Rec], has_title: bool) -> List[Zone]:
        zones: List[Zone] = []
        ranked = sorted(free_text, key=lambda r: -(r.font_pt or 0))
        for rank, rec in enumerate(ranked):
            declared = _declared_role(rec)
            if declared == "keep":
                continue
            marker = KEY_PATTERN.search(rec.text)
            if not (
                declared
                or marker
                or lexicon.is_sample_text(rec.text)
                or (not has_title and rank == 0)
            ):
                continue
            if declared:
                role = cast(ZoneRole, declared)
            elif marker:
                role = "body"
            elif lexicon.is_numberish(rec.text):
                role = "number"
            elif rank == 0 and not has_title and rec.box.y < 150:
                role = "title"
            elif (rec.font_pt or 0) >= 20 and rec.lines <= 2:
                role = "heading"
            elif rec.words <= 4 and rec.box.h <= 60:
                role = "label"
            else:
                role = "body"
            zones.append(_zone(rec, role, self.width, self.height))
        return zones

    # -- exclusions --------------------------------------------------------------------

    def _apply_exclusions(self, pattern: Pattern, slide, records: List[_Rec]) -> None:
        for rec in records:
            if rec.kind in ("chart", "table") and rec.area >= _MAIN_CONTENT_AREA:
                pattern.included = False
                pattern.exclusion_reason = rec.kind  # type: ignore[assignment]
                return
        pictures = sum(1 for rec in records if rec.kind == "picture")
        text_zones = [z for z in pattern.zones if z.role in ("body", "heading")]
        if pictures >= _ICON_BANK_PICTURES and not text_zones and not pattern.groups:
            pattern.included = False
            pattern.exclusion_reason = "icon_bank"
            return
        for rel in slide.part.rels.values():
            if rel.is_external:
                continue
            if not rel.reltype.endswith(COPYABLE_REL_SUFFIXES):
                pattern.included = False
                pattern.exclusion_reason = "unsupported_parts"
                pattern.warnings.append(
                    f"Slide holds a part that cannot be copied: {rel.reltype.rsplit('/', 1)[-1]}."
                )
                return

    # -- intent ------------------------------------------------------------------------

    def _intent(
        self, pattern: Pattern, records: List[_Rec], name: str, slide_number: int = 0
    ) -> Intent:
        zones = [z for z in pattern.zones if z.role != "keep"]
        if not zones and not pattern.groups:
            return "fixed"
        titles = [z for z in zones if z.role == "title"]
        subtitles = [z for z in zones if z.role == "subtitle"]
        headings = [z for z in zones if z.role == "heading"]
        bodies = [z for z in zones if z.role == "body"]
        images = [z for z in zones if z.role == "image"]
        labels = [z for z in zones if z.role in ("label", "caption", "number")]

        if pattern.groups:
            group = pattern.groups[0]
            roles = set(group.item_zones)
            numbers = [
                z.sample for item in group.items for z in item if z.role == "number"
            ]
            if "number" in roles and "body" not in roles and "label" not in roles:
                return (
                    "steps"
                    if numbers and all(lexicon.is_year(n) for n in numbers)
                    else "agenda"
                )
            if "number" in roles and _sequential(numbers):
                return "steps"
            return "cards"

        samples = [z.sample for z in zones] + [name]
        if len(zones) >= 3 and lexicon.has_contact_words(samples):
            return "contact"
        if lexicon.name_matches(name, lexicon.CONTACT_NAMES):
            return "contact"

        if titles and not bodies and not headings and not images:
            if subtitles or (labels and len(labels) == 1):
                return "title"
            if lexicon.name_matches(name, lexicon.COVER_NAMES) or slide_number == 1:
                return "title"
            if (
                lexicon.name_matches(name, lexicon.SECTION_NAMES)
                or pattern.source == "layout"
            ):
                return "section"
            # An example slide that dropped its layout's body to show only
            # a title over graphics is a decorative divider, used verbatim.
            has_pictures = any(rec.kind == "picture" for rec in records)
            return "fixed" if has_pictures and len(zones) == 1 else "section"
        if titles and len(bodies) == 1 and not headings and not images:
            body = bodies[0]
            title = titles[0]
            under_title = body.box.y >= title.box.y and body.box.h < 120
            if under_title and (
                lexicon.name_matches(name, lexicon.COVER_NAMES) or slide_number == 1
            ):
                return "title"
            if lexicon.name_matches(name, lexicon.SECTION_NAMES):
                return "section"
            if lexicon.name_matches(name, lexicon.STATEMENT_NAMES):
                return "statement"
            return "content"
        if titles and not bodies and images and not headings:
            return (
                "section"
                if lexicon.name_matches(name, lexicon.SECTION_NAMES)
                else "image_text"
            )
        if len(bodies) >= 2 and not images:
            same_band = (
                max(b.box.y for b in bodies) - min(b.box.y for b in bodies) < 100
            )
            if same_band and len(headings) >= 2:
                return "comparison"
            if same_band:
                return "two_columns"
        if images and (bodies or headings):
            return "image_text"
        if len(bodies) == 1 and not titles and not headings:
            return "statement"
        if bodies or headings:
            return "content"
        if images:
            return "image_text"
        return "content"


def _sequential(numbers: List[str]) -> bool:
    values: List[int] = []
    for raw in numbers:
        digits = re.sub(r"[^0-9]", "", raw)
        if not digits:
            return False
        values.append(int(digits))
    if len(values) < 2:
        return False
    return all(b - a == 1 for a, b in zip(values, values[1:])) or all(
        lexicon.is_year(n) for n in numbers
    )


def analyze_presentation(presentation) -> TemplateInventory:
    """Inventory an open presentation (CPU-bound; call off the event loop)."""
    return _Analyzer(presentation).run()


def analyze_template(pptx_source: Union[bytes, str]) -> AnalyzeResult:
    """Inventory ``.pptx`` bytes or a path, wrapping unreadable input as one error."""
    try:
        presentation = (
            Presentation(io.BytesIO(pptx_source))
            if isinstance(pptx_source, bytes)
            else Presentation(pptx_source)
        )
        inventory = analyze_presentation(presentation)
    except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a template error
        return AnalyzeResult(
            errors=[
                AnalysisError(
                    code=CODE_INVALID_UPLOAD,
                    message=f"The uploaded file could not be read as a .pptx: {exc}",
                )
            ]
        )
    return AnalyzeResult(inventory=inventory, summary=inventory.summary())


__all__ = [
    "CODE_INVALID_UPLOAD",
    "COPYABLE_REL_SUFFIXES",
    "analyze_presentation",
    "analyze_template",
    "estimate_capacity",
]
