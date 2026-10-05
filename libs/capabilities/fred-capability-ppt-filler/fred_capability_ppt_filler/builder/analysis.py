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

On an example slide every text-bearing shape is a slot, except text repeated
on several slides and date/footer/slide-number fields; roles come from
placeholder types, repeated groups, geometry and font rank. The slide kind is
a heuristic the vision pass refines (design.md D2). Optional annotations
(shape names, ``kind:`` notes) override the corresponding heuristic.
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

from lxml import etree  # pyright: ignore[reportAttributeAccessIssue]
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from fred_capability_ppt_filler import text_metrics
from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    AnalysisError,
    AnalyzeResult,
    Box,
    Pattern,
    RepeatGroup,
    SlideKind,
    TemplateInventory,
    Zone,
    ZoneRole,
)
from fred_capability_ppt_filler.traversal import KEY_PATTERN, walk_shapes

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pptx.shapes.base import BaseShape

CODE_INVALID_UPLOAD = "invalid_upload"

# A relationship of these kinds does not block duplicating a slide (slide-to-
# slide links are dropped, not copied); any other part (chart, SmartArt, OLE)
# makes the slide uncopyable.
COPYABLE_REL_SUFFIXES = (
    "/slide",
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
_SHARED_TEXT_MIN_SLIDES = 2
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
    font_name: Optional[str]
    bold: bool
    lines: int
    name: str
    shape: "BaseShape" = field(repr=False)
    frame: "FrameMetrics" = field(default_factory=lambda: FrameMetrics(), repr=False)
    # Holds a slide-number or date field: chrome, never a slot.
    is_field: bool = False

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


_THEME_FONTS = {"+mj-lt": 0, "+mn-lt": 1}
# Placeholders drawn with the theme's heading font ("SUBTITLE" is not one).
_TITLE_PLACEHOLDERS = ("TITLE", "CENTER_TITLE", "VERTICAL_TITLE")


# Bumped whenever the rules below change what an inventory holds, so agents
# saved with an older analysis are recomputed from their stored template.
ANALYSIS_VERSION = 6


def theme_fonts(presentation) -> Tuple[Optional[str], Optional[str]]:
    """The theme's (heading, body) latin typefaces, or ``(None, None)``."""
    try:
        master_part = presentation.slide_masters[0].part
        theme_part = next(
            rel.target_part
            for rel in master_part.rels.values()
            if not rel.is_external and rel.reltype.endswith("/theme")
        )
        scheme = etree.fromstring(theme_part.blob).find(f".//{qn('a:fontScheme')}")
    except Exception:  # noqa: BLE001 - a theme-less deck just measures by default
        return None, None
    if scheme is None:
        return None, None

    def typeface(kind: str) -> Optional[str]:
        node = scheme.find(f"{qn(kind)}/{qn('a:latin')}")
        return node.get("typeface") if node is not None else None

    return typeface("a:majorFont"), typeface("a:minorFont")


def _font_name_of(
    shape, theme: Tuple[Optional[str], Optional[str]], is_title: bool
) -> Tuple[Optional[str], bool]:
    """The font a shape's text is drawn with, and whether it is bold. Runs
    first, then any declared typeface, then the theme's heading/body font."""
    name: Optional[str] = None
    bold = False
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            name = name or run.font.name
            bold = bold or bool(run.font.bold)
    if name is None:
        latin = shape._element.find(f".//{qn('a:latin')}")
        name = latin.get("typeface") if latin is not None else None
    if not bold:
        bold = any(
            node.get("b") in ("1", "true", "on")
            for node in shape._element.iter(qn("a:rPr"))
        )
    major, minor = theme
    if name in _THEME_FONTS:
        name = (major, minor)[_THEME_FONTS[name]]
    return (name or (major if is_title else minor)), bold


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


@dataclass(frozen=True)
class FrameMetrics:
    """What a text box costs in room before a single glyph is drawn.

    PowerPoint lays text inside the box's padding, and advances each paragraph
    by its own line spacing plus the space declared around it. A template that
    sets ``lnSpc 114%`` and ``spcBef 16pt`` on its body style fits barely half
    the bullets a bare "height / (size × 1.2)" would promise.
    """

    lr_inset: int = 2 * text_metrics.DEFAULT_INSET_EMU
    tb_inset: int = 2 * text_metrics.DEFAULT_V_INSET_EMU
    line_spacing: float = 1.0
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    # Does not wrap: the box widens with its text instead of breaking a line.
    # Auto-sizing the *height* does not count — such a box still wraps, and the
    # width limit that follows from it is the one that matters.
    grows: bool = False


def _pPr_chain(shape, layout, master) -> List[Any]:
    """Paragraph-property elements that apply to a shape's first level, most
    specific first: its own text, its list style, then the ones it inherits."""
    chain: List[Any] = []
    element = shape._element
    own = element.find(f".//{qn('a:p')}/{qn('a:pPr')}")
    if own is not None:
        chain.append(own)
    lvl = element.find(f".//{qn('a:lstStyle')}/{qn('a:lvl1pPr')}")
    if lvl is not None:
        chain.append(lvl)
    fmt = shape.placeholder_format if shape.is_placeholder else None
    if fmt is not None:
        for holder in (layout, master):
            if holder is None:
                continue
            for candidate in holder.placeholders:
                cfmt = candidate.placeholder_format
                if cfmt.idx == fmt.idx or (
                    cfmt.type == fmt.type and fmt.type is not None
                ):
                    node = candidate._element.find(
                        f".//{qn('a:lstStyle')}/{qn('a:lvl1pPr')}"
                    )
                    if node is not None:
                        chain.append(node)
                    break
    if master is not None:
        styles = master._element.find(qn("p:txStyles"))
        if styles is not None:
            is_title = (
                fmt is not None
                and fmt.type is not None
                and fmt.type.name
                in (
                    "TITLE",
                    "CENTER_TITLE",
                )
            )
            if fmt is None:
                names = ("p:otherStyle", "p:bodyStyle")
            elif is_title:
                names = ("p:titleStyle",)
            else:
                names = ("p:bodyStyle",)
            for name in names:
                style = styles.find(qn(name))
                node = None if style is None else style.find(qn("a:lvl1pPr"))
                if node is not None:
                    chain.append(node)
    return chain


def _spc_pt(pPr, tag: str, font_pt: Optional[float]) -> Optional[float]:
    """``spcBef``/``spcAft`` of a paragraph, in points."""
    element = pPr.find(qn(tag))
    if element is None:
        return None
    points = element.find(qn("a:spcPts"))
    if points is not None and points.get("val"):
        return int(points.get("val")) / 100
    percent = element.find(qn("a:spcPct"))
    if percent is not None and percent.get("val") and font_pt:
        return int(percent.get("val")) / 100000 * font_pt * text_metrics.LINE_HEIGHT
    return None


def _line_ratio(pPr, font_pt: Optional[float]) -> Optional[float]:
    """``lnSpc`` as a multiple of the font's own line height."""
    element = pPr.find(qn("a:lnSpc"))
    if element is None:
        return None
    percent = element.find(qn("a:spcPct"))
    if percent is not None and percent.get("val"):
        return int(percent.get("val")) / 100000
    points = element.find(qn("a:spcPts"))
    if points is not None and points.get("val") and font_pt:
        return int(points.get("val")) / 100 / (font_pt * text_metrics.LINE_HEIGHT)
    return None


def _frame_metrics(shape, layout, master, font_pt: Optional[float]) -> FrameMetrics:
    """Padding and paragraph spacing a text box applies, inherited included."""
    body = shape.text_frame._txBody.find(qn("a:bodyPr"))
    if body is None:
        lr = 2 * text_metrics.DEFAULT_INSET_EMU
        tb = 2 * text_metrics.DEFAULT_V_INSET_EMU
    else:
        lr = sum(
            int(body.get(side, text_metrics.DEFAULT_INSET_EMU))
            for side in ("lIns", "rIns")
        )
        tb = sum(
            int(body.get(side, text_metrics.DEFAULT_V_INSET_EMU))
            for side in ("tIns", "bIns")
        )
    spacing: Optional[float] = None
    before: Optional[float] = None
    after: Optional[float] = None
    for pPr in _pPr_chain(shape, layout, master):
        if spacing is None:
            spacing = _line_ratio(pPr, font_pt)
        if before is None:
            before = _spc_pt(pPr, "a:spcBef", font_pt)
        if after is None:
            after = _spc_pt(pPr, "a:spcAft", font_pt)
        if spacing is not None and before is not None and after is not None:
            break
    return FrameMetrics(
        lr_inset=max(0, lr),
        tb_inset=max(0, tb),
        line_spacing=spacing or 1.0,
        space_before_pt=max(0.0, before or 0.0),
        space_after_pt=max(0.0, after or 0.0),
        grows=body is not None and body.get("wrap") == "none",
    )


_CHROME_FIELDS = ("slidenum", "datetime")


def _has_chrome_field(shape) -> bool:
    return any(
        (node.get("type") or "").lower().startswith(_CHROME_FIELDS)
        for node in shape._element.iter(qn("a:fld"))
    )


def _placeholder_key(shape) -> str:
    return f"ph:{shape.placeholder_format.idx}"


def _shape_key(path: Tuple[int, ...]) -> str:
    return "sp:" + "/".join(str(part) for part in path)


def _records(
    shapes,
    width: int,
    height: int,
    layout=None,
    master=None,
    theme: Tuple[Optional[str], Optional[str]] = (None, None),
) -> List[_Rec]:
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
        font_name = None
        bold = False
        lines = 0
        frame = FrameMetrics()
        is_field = False
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
            font_name, bold = _font_name_of(
                shape, theme, is_title=ph_type in _TITLE_PLACEHOLDERS
            )
            frame = _frame_metrics(shape, layout, master, font_pt)
            lines = text.count("\n") + 1 if text else 0
            is_field = _has_chrome_field(shape)
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
                font_name=font_name,
                bold=bold,
                lines=lines,
                name=shape.name or "",
                shape=shape,
                frame=frame,
                is_field=is_field,
            )
        )
    return records


# Roles whose text is a list: every line is its own paragraph, so it pays the
# paragraph spacing again. A title wraps within one paragraph and pays it once.
_BULLET_ROLES = frozenset({"body", "caption"})


def estimate_capacity(
    box: Box,
    font_pt: Optional[float],
    role: str,
    width_emu: int,
    height_emu: int,
    font_name: Optional[str] = None,
    bold: bool = False,
    frame: Optional[FrameMetrics] = None,
) -> Tuple[int, int]:
    """(max_chars, max_lines) of a box, as the renderer will really fill it.

    Both dimensions go through the box's own formatting: the padding comes off
    the usable width and height, and a line advances by the paragraph's line
    spacing plus the space declared around it. Widths are measured with the
    real font (see ``text_metrics``); greedy wrapping wastes about half a word
    at every line break, so the product of characters and lines is not free.
    """
    pt = font_pt or _DEFAULT_PT.get(role, 16.0)
    metrics = frame or FrameMetrics()
    width_emu_box = box.w / 1000 * width_emu - metrics.lr_inset
    height_emu_box = box.h / 1000 * height_emu - metrics.tb_inset
    width_pt = max(0.0, width_emu_box) / 914400 * 72
    height_pt = max(0.0, height_emu_box) / 914400 * 72

    pitch = pt * text_metrics.LINE_HEIGHT * metrics.line_spacing
    around = metrics.space_before_pt + metrics.space_after_pt
    if role in _BULLET_ROLES:
        lines = int(height_pt / (pitch + around)) if pitch + around > 0 else 1
    else:
        lines = int((height_pt - around) / pitch) if pitch > 0 else 1
    lines = max(1, lines)

    per_line = text_metrics.chars_per_line(width_pt, pt, font_name, bold)
    waste = text_metrics.WRAP_WASTE_CHARS * (lines - 1)
    chars = (per_line * lines - waste) * text_metrics.SAFETY
    return max(1, int(chars)), lines


def _zone(rec: _Rec, role: ZoneRole, width: int, height: int) -> Zone:
    max_chars = max_lines = None
    if role != "image" and role != "keep":
        max_chars, max_lines = estimate_capacity(
            rec.box,
            rec.font_pt,
            role,
            width,
            height,
            rec.font_name,
            rec.bold,
            rec.frame,
        )
    return Zone(
        key=rec.key,
        role=role,
        box=rec.box,
        sample=rec.text[:80],
        font_pt=rec.font_pt,
        max_chars=max_chars,
        max_lines=max_lines,
        grows=rec.frame.grows,
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
        self.theme = theme_fonts(presentation)

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
                self.theme,
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
            pattern = self._layout_pattern(layout, index)
            patterns.append(pattern)
            if pattern.included:
                layout_zone_sets[layout.name] = frozenset(z.key for z in pattern.zones)

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

        layout_kinds = {p.kind for p in patterns if p.source == "layout" and p.included}
        for pattern in patterns:
            if (
                pattern.source == "slide"
                and pattern.included
                and pattern.reusable
                and pattern.kind in layout_kinds
            ):
                pattern.preferred = True

        return TemplateInventory(
            analysis_version=ANALYSIS_VERSION,
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
            layout.placeholders,
            self.width,
            self.height,
            None,
            layout.slide_master,
            self.theme,
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
            kind="other",
            zones=zones,
        )
        pattern.kind = _kind(pattern, records, name, layout._element.get("type"))
        if not zones and pattern.kind != "closing":
            pattern.included = False
            pattern.exclusion_reason = "no_placeholder"
        pattern.reusable = pattern.kind != "other"
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

        # 3. Every other text box is a slot, but chrome: text repeated across
        # slides (a repeated sample box still counts) and date/number fields.
        free_text = [
            rec
            for rec in records
            if rec.kind == "text"
            and rec.ph_idx is None
            and rec.text
            and not rec.is_field
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
            kind="other",
            zones=zones,
            groups=groups,
            warnings=warnings,
        )

        # 5. Exclusions.
        self._apply_exclusions(pattern, slide, records)

        # 6. Label then kind, with the notes directives on top.
        notes = ""
        if slide.has_notes_slide:
            frame = slide.notes_slide.notes_text_frame
            notes = frame.text if frame is not None else ""
        label = lexicon.LABEL_NOTE.search(notes)
        if label:
            pattern.label = label.group(1)[:60]
        pattern.kind = _kind(
            pattern,
            records,
            layout_name,
            slide.slide_layout._element.get("type"),
            slide_number=number,
        )
        match = lexicon.KIND_NOTE.search(notes)
        if match:
            declared = match.group(1).lower()
            declared = lexicon.LEGACY_KINDS.get(declared, declared)
            if declared in SLIDE_KINDS:
                pattern.kind = cast(SlideKind, declared)
        pattern.reusable = pattern.kind != "other"
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


# -- slide kind (heuristic; the vision pass refines it) ---------------------------

# `<p:sldLayout type=…>` values that state a kind; `obj`, `tx` and the custom
# ones say nothing the zones do not.
_LAYOUT_TYPE_KINDS: Dict[str, SlideKind] = {
    "title": "cover",
    "secHead": "section",
    "twoObj": "two_columns",
    "twoColTx": "two_columns",
    "twoTxTwoObj": "comparison",
    "picTx": "image_text",
}
# Kinds that never hold body content, whatever a name says ("3 images +
# message clé" is no quote).
_SPARSE_KINDS = ("cover", "section", "quote")
# A title this short names the slide ("Equipe", "Planche de processus"); a
# longer one is content and says nothing about the kind.
_NAMING_TITLE_WORDS = 4


def _has_body_content(pattern: Pattern) -> bool:
    """Content a cover or a divider never holds: a list, three or more text
    slots beside the title, or a body box sized for paragraphs."""
    if pattern.groups:
        return True
    text = [
        z for z in pattern.zones if z.role not in ("title", "subtitle", "image", "keep")
    ]
    if len(text) >= 3:
        return True
    return any(
        z.role in ("body", "heading")
        and (z.box.h >= 300 or len(z.sample.split()) >= 25)
        for z in text
    )


def _hinted_kind(
    pattern: Pattern, records: List[_Rec], name: str, layout_type: Optional[str]
) -> Optional[SlideKind]:
    """A kind the template states: its layout type, then its layout name, a
    naming title or label, then a declared shape name."""
    # The layout type describes the placeholders, not what was drawn over them.
    if layout_type in _LAYOUT_TYPE_KINDS and not pattern.groups:
        return _LAYOUT_TYPE_KINDS[layout_type]
    names = [name]
    title = next((z.sample for z in pattern.zones if z.role == "title"), "")
    if pattern.source == "slide":
        # The label is the title, or what a `label:` note says.
        for text in (title, pattern.label):
            if len(text.split()) <= _NAMING_TITLE_WORDS or lexicon.is_sample_text(text):
                names.append(text)
    names.extend(rec.name for rec in records if not lexicon.is_auto_name(rec.name))
    for candidate in names:
        kind = lexicon.kind_from_name(candidate)
        if kind is not None:
            return cast(SlideKind, kind)
    return None


def _group_kind(group: RepeatGroup, samples: List[str]) -> SlideKind:
    roles = set(group.item_zones)
    numbers = [z.sample for item in group.items for z in item if z.role == "number"]
    if numbers and all(lexicon.is_year(n) for n in numbers):
        return "timeline"
    if "number" in roles:
        if not _sequential(numbers):
            return "figures"
        return "process" if roles & {"body", "label"} else "agenda"
    if lexicon.has_contact_words(samples):
        return "team"
    return "cards"


def _kind(
    pattern: Pattern,
    records: List[_Rec],
    name: str,
    layout_type: Optional[str],
    slide_number: int = 0,
) -> SlideKind:
    """The slide kind from the template's own hints, else from the slot roles.
    A slide holding real body content is never a cover, a section or a quote."""
    zones = [z for z in pattern.zones if z.role != "keep"]
    hinted = _hinted_kind(pattern, records, name, layout_type)
    if not zones and not pattern.groups:
        return "closing" if hinted == "closing" else "other"
    body = _has_body_content(pattern)
    if hinted is not None and not (hinted in _SPARSE_KINDS and body):
        return hinted

    samples = [z.sample for z in zones] + [
        z.sample for g in pattern.groups for item in g.items for z in item
    ]
    if pattern.groups:
        return _group_kind(pattern.groups[0], samples)
    if len(zones) >= 3 and lexicon.has_contact_words(samples + [name]):
        return "closing"

    titles = [z for z in zones if z.role == "title"]
    subtitles = [z for z in zones if z.role == "subtitle"]
    headings = [z for z in zones if z.role == "heading"]
    bodies = [z for z in zones if z.role == "body"]
    images = [z for z in zones if z.role == "image"]
    labels = [z for z in zones if z.role in ("label", "caption", "number")]

    if titles and not bodies and not headings and not images and not body:
        if subtitles or len(labels) == 1 or slide_number == 1:
            return "cover"
        # A lone title over graphics on an example slide is decoration.
        if pattern.source == "slide" and len(zones) == 1:
            if any(rec.kind == "picture" for rec in records):
                return "other"
        return "section"
    if titles and len(bodies) == 1 and not headings and not images:
        under_title = bodies[0].box.y >= titles[0].box.y and bodies[0].box.h < 120
        if under_title and slide_number == 1 and not body:
            return "cover"
        return "bullets"
    if titles and not bodies and images and not headings:
        return "image_text"
    if len(bodies) >= 2 and not images:
        same_band = max(b.box.y for b in bodies) - min(b.box.y for b in bodies) < 100
        if same_band:
            return "comparison" if len(headings) >= 2 else "two_columns"
    if images and (bodies or headings):
        return "image_text"
    if len(bodies) == 1 and not titles and not headings:
        return "quote"
    if images and not bodies and not headings:
        return "image_text"
    return "bullets"


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
    "ANALYSIS_VERSION",
    "analyze_presentation",
    "analyze_template",
    "estimate_capacity",
]
