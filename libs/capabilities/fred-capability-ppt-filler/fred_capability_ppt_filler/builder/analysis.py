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

from lxml import etree  # pyright: ignore[reportAttributeAccessIssue]
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from fred_capability_ppt_filler import text_metrics
from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.design_system import (
    MAJOR_LATIN,
    MINOR_LATIN,
    THEME_SLOTS,
    ColorPair,
    ColorToken,
    IconRef,
    DesignSystem,
    Grid,
    OpticalAnchors,
    ShapeLanguage,
    FIGURE_TEXT,
    MIN_FREE_SHARE,
    SpacingScale,
    TypeToken,
    best_pair,
    free_area,
    lightness,
    tint,
)
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
    font_name: Optional[str]
    bold: bool
    lines: int
    name: str
    shape: "BaseShape" = field(repr=False)
    frame: "FrameMetrics" = field(default_factory=lambda: FrameMetrics(), repr=False)

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
ANALYSIS_VERSION = 5


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


# -- design system -------------------------------------------------------------
#
# What composing draws from (design.md D2). Read here because it needs the file;
# everything downstream works on `DesignSystem` and never reopens the template.


def theme_colors(presentation) -> Dict[str, str]:
    """The theme's colour slots as ``{slot: RRGGBB}``, empty on a theme-less deck.

    A slot may be an explicit ``srgbClr`` or a ``sysClr`` with its last rendered
    value; both carry the hex we need, neither is invented here.
    """
    try:
        master_part = presentation.slide_masters[0].part
        theme_part = next(
            rel.target_part
            for rel in master_part.rels.values()
            if not rel.is_external and rel.reltype.endswith("/theme")
        )
        scheme = etree.fromstring(theme_part.blob).find(f".//{qn('a:clrScheme')}")
    except Exception:  # noqa: BLE001 - a theme-less deck simply has no slots
        return {}
    if scheme is None:
        return {}
    colors: Dict[str, str] = {}
    for slot in THEME_SLOTS:
        node = scheme.find(qn(f"a:{slot}"))
        if node is None:
            continue
        srgb = node.find(qn("a:srgbClr"))
        if srgb is not None and srgb.get("val"):
            colors[slot] = srgb.get("val", "").upper()
            continue
        sysclr = node.find(qn("a:sysClr"))
        if sysclr is not None and sysclr.get("lastClr"):
            colors[slot] = sysclr.get("lastClr", "").upper()
    return colors


def _literal_colors(records: Sequence[_Rec]) -> List[str]:
    """Solid fills actually used on the template's shapes, most frequent first.

    The fallback when the theme says nothing: a template that paints in literals
    still tells us what it paints with.
    """
    seen: Counter[str] = Counter()
    for rec in records:
        element = getattr(rec.shape, "_element", None)
        if element is None:
            continue
        for node in element.iter(qn("a:srgbClr")):
            value = node.get("val")
            if value:
                seen[value.upper()] += 1
    return [value for value, _ in seen.most_common()]


#: How far a muted surface sits from the page: a tint, not a colour block.
_MUTED_LUM_MOD = 8000
_MUTED_LUM_OFF = 92000


def _muted_surface(
    background: Optional[ColorToken], foreground: Optional[ColorToken]
) -> Optional[ColorToken]:
    """The surface a Card sits on: a TINT of the template's ink, not a slot.

    Reading it off `lt2` assumes the template uses its theme as the format
    intends. Slot names lie — a real template put a vivid cyan there, and every
    card came out flashy. A tint of the ink is quiet by construction, still a
    theme reference, and still follows a theme change (D12).
    """
    ink = foreground or background
    if ink is None:
        return None
    if background is not None and lightness(background.rgb) < 0.5:
        # A dark deck: lift the page rather than tint the ink, or the card
        # would be lighter than the text on it.
        return tint(background, lum_mod=100000, lum_off=10000)
    return tint(ink, lum_mod=_MUTED_LUM_MOD, lum_off=_MUTED_LUM_OFF)


def _build_pairs(
    slots: Dict[str, str], literals: Sequence[str]
) -> Tuple[List[ColorPair], List[str]]:
    """Pair every candidate surface with the most readable ink available (D12).

    Surfaces and inks both come from the template; `unreferenced` names the
    tokens that had no theme slot to point at, so D11 can report them.
    """
    unreferenced: List[str] = []
    tokens: Dict[str, ColorToken] = {
        slot: ColorToken(ref=slot, rgb=rgb) for slot, rgb in slots.items() if rgb
    }
    for index, value in enumerate(literals[:4]):
        if any(token.rgb == value for token in tokens.values()):
            continue
        name = f"literal{index + 1}"
        tokens[name] = ColorToken(ref=None, rgb=value)
        unreferenced.append(name)
    if not tokens:
        return [], unreferenced

    inks = list(tokens.values())
    # `lt1`/`dk1` are the template's page and ink when it uses its theme as
    # intended; the surfaces below fall back to what is actually there.
    background = tokens.get("lt1") or tokens.get("lt2")
    foreground = tokens.get("dk1") or tokens.get("dk2")
    named: List[Tuple[str, Optional[ColorToken]]] = [
        ("surface", background or foreground),
        ("surface-muted", _muted_surface(background, foreground)),
        ("accent", tokens.get("accent1")),
        ("accent-2", tokens.get("accent2")),
        ("inverse", foreground or background),
    ]
    pairs: List[ColorPair] = []
    for name, surface in named:
        if surface is None:
            continue
        if any(pair.surface.rgb == surface.rgb for pair in pairs):
            continue
        pairs.append(best_pair(name, surface, inks))
    # What D11 has to report is a pair that will WRITE a literal, not a token
    # that happened to be read and may never reach a shape.
    unreferenced = [
        pair.name
        for pair in pairs
        if not pair.surface.referenced or not pair.on_surface.referenced
    ]
    return pairs, unreferenced


#: Roles whose size the type scale reports, and the placeholder that carries it.
_SCALE_SOURCES: tuple[Tuple[ZoneRole, tuple[str, ...]], ...] = (
    ("title", _TITLE_PLACEHOLDERS),
    ("subtitle", ("SUBTITLE",)),
    ("body", ("BODY", "OBJECT")),
)


def _build_type_scale(
    records: Sequence[_Rec], theme: Tuple[Optional[str], Optional[str]]
) -> List[TypeToken]:
    """The size of each text level, read from the template's own placeholders.

    Roles the template has no placeholder for are derived from `body` by the
    ratios a type scale usually holds, so a plain template still has a scale.
    """
    major, minor = theme
    sizes: Dict[str, float] = {}
    for role, ph_types in _SCALE_SOURCES:
        candidates = [
            rec.font_pt
            for rec in records
            if rec.ph_type in ph_types and rec.font_pt is not None
        ]
        if candidates:
            sizes[role] = max(candidates)
    body = sizes.get("body") or sizes.get("subtitle") or 18.0
    title = sizes.get("title") or body * 2.0
    subtitle = sizes.get("subtitle") or body * 1.3
    derived: Dict[ZoneRole, Tuple[float, bool, Optional[str]]] = {
        "title": (title, True, MAJOR_LATIN),
        "subtitle": (subtitle, False, MINOR_LATIN),
        "heading": (body * 1.15, True, MINOR_LATIN),
        "body": (body, False, MINOR_LATIN),
        "caption": (body * 0.8, False, MINOR_LATIN),
        "number": (title * 1.1, True, MAJOR_LATIN),
        "label": (body * 0.75, True, MINOR_LATIN),
    }
    scale: List[TypeToken] = []
    for role, (size, bold, ref) in derived.items():
        scale.append(
            TypeToken(
                role=role,
                font_ref=ref,
                font_name=(major if ref == MAJOR_LATIN else minor) or "",
                size_pt=round(size, 1),
                bold=bold,
            )
        )
    return scale


_DEFAULT_AREA = Box(x=60, y=90, w=880, h=820)


#: Intents whose geometry says nothing about where CONTENT goes. A cover's
#: title sits in a narrow column by design; reading the content band off it
#: gives a band no content fits in.
_NON_CONTENT_INTENTS: frozenset = frozenset({"title", "section", "contact", "fixed"})

#: A content band narrower than this is not a content band, whatever measured it.
_MIN_AREA_WIDTH = 450


def _usable_area(records: Sequence[_Rec], width: int, height: int) -> Box:
    """The band the template's own content sits in, per-mille.

    Placeholders first: they ARE the content area the designer laid out. Free
    boxes only answer when there is no placeholder, and then by their most
    common edge rather than their extremes — one full-bleed decorative band
    must not erase the margins every other slide respects.

    `records` must come from CONTENT sources only: a template whose only
    placeholders sit on a cover would otherwise teach us that content belongs
    in a narrow column, and every composed slide would be squeezed into it.
    """
    placed = [
        rec.box
        for rec in records
        if rec.ph_idx is not None and rec.box.w > 50 and rec.box.w < 1000
    ]
    boxes = placed or [
        rec.box for rec in records if rec.kind == "text" and 50 < rec.box.w < 1000
    ]
    if not boxes:
        return _DEFAULT_AREA.model_copy()
    left = Counter(box.x for box in boxes).most_common(1)[0][0]
    right = Counter(box.x + box.w for box in boxes).most_common(1)[0][0]
    top = min(box.y for box in boxes)
    bottom = max(box.y + box.h for box in boxes)
    if right - left < _MIN_AREA_WIDTH:
        return _DEFAULT_AREA.model_copy()
    return Box(
        x=max(0, left),
        y=max(0, top),
        w=max(1, min(1000, right) - max(0, left)),
        h=max(1, min(1000, bottom) - max(0, top)),
    )


#: A shape covering more of the slide than this is the background, not a
#: fixture: reserving it would leave nothing to compose on.
_BACKGROUND_SHARE = 0.5


def _fixtures(records: Sequence[_Rec]) -> List[Box]:
    """What a layout or master draws for itself: logo, band, footer, rule.

    PowerPoint INHERITS these onto every slide using the layout, so a composed
    slide already shows them and must not draw over them. Placeholders are not
    fixtures — they are what a slide fills — and the full-bleed background is
    not one either, or nothing would be left.
    """
    return [
        rec.box
        for rec in records
        if rec.ph_idx is None
        and rec.kind != "group"
        and rec.area < _BACKGROUND_SHARE
        and rec.box.w > 0
        and rec.box.h > 0
    ]


def _inherits_master(layout) -> bool:
    """A layout may switch the master's own shapes off; its logo goes with them."""
    value = layout._element.get("showMasterSp")
    return value is None or value not in ("0", "false")


#: A block is a shape big enough to hold something and small enough not to be
#: the page: below, an icon or a bullet dot; above, a background.
_BLOCK_MIN_AREA = 0.004
_BLOCK_MAX_AREA = 0.35
_FILLS = ("a:solidFill", "a:gradFill", "a:pattFill", "a:blipFill")


def _paint(rec: _Rec) -> Optional[Tuple[bool, bool]]:
    """``(filled, outlined)`` for a shape that paints a block, else None.

    A bare text box paints nothing and must not vote: it would make every
    template look like one that outlines rather than fills.
    """
    element = getattr(rec.shape, "_element", None)
    if element is None:
        return None
    props = element.find(qn("p:spPr"))
    if props is None:
        return None
    style = element.find(qn("p:style"))

    def referenced(tag: str) -> bool:
        node = None if style is None else style.find(qn(tag))
        return node is not None and node.get("idx", "0") != "0"

    if props.find(qn("a:noFill")) is not None:
        filled = False
    elif any(props.find(qn(tag)) is not None for tag in _FILLS):
        filled = True
    else:
        filled = referenced("a:fillRef")
    line = props.find(qn("a:ln"))
    if line is not None:
        outlined = line.find(qn("a:noFill")) is None
    else:
        outlined = referenced("a:lnRef")
    return (filled, outlined) if filled or outlined else None


def _blocks(records: Sequence[_Rec]) -> List[_Rec]:
    """The shapes a designer would call a block: panels, chips, bands."""
    return [
        rec
        for rec in records
        if rec.ph_idx is None
        and rec.kind in ("text", "other")
        and _BLOCK_MIN_AREA <= rec.area <= _BLOCK_MAX_AREA
    ]


def _radius_of(rec: _Rec) -> Optional[float]:
    element = getattr(rec.shape, "_element", None)
    if element is None:
        return None
    for node in element.iter(qn("a:gd")):
        fmla = node.get("fmla", "")
        if node.get("name", "").startswith("adj") and fmla.startswith("val "):
            try:
                return int(fmla.split()[1]) / 100000
            except (ValueError, IndexError):
                return None
    return None


def _inset_of(rec: _Rec) -> Optional[int]:
    """The horizontal text inset the shape sets for itself, in EMU."""
    element = getattr(rec.shape, "_element", None)
    if element is None:
        return None
    body = element.find(f"{qn('p:txBody')}/{qn('a:bodyPr')}")
    if body is None or body.get("lIns") is None:
        return None
    try:
        return int(body.get("lIns", "0"))
    except ValueError:
        return None


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _column_gap(
    groups: Sequence[Sequence[_Rec]], width: int, shorter: int
) -> Optional[int]:
    """The air the template leaves between two blocks side by side.

    Read per slide, because a gap only means something between shapes that
    share a row. Reported per-mille of the SHORTER side, like every other gap,
    so it stays comparable with the spacing scale.
    """
    gaps: List[float] = []
    for records in groups:
        row_candidates = [rec for rec in _blocks(records) if rec.box.h > 10]
        for left, right in _side_by_side(row_candidates):
            gap = right.box.x - (left.box.x + left.box.w)
            # A negative gap is an overlap, and a huge one is two unrelated
            # shapes that happen to share a band.
            if 0 < gap < 200:
                gaps.append(gap * width / max(1, shorter))
    if not gaps:
        return None
    return max(2, round(_median(gaps)))


def _side_by_side(records: Sequence[_Rec]) -> List[Tuple[_Rec, _Rec]]:
    """Consecutive pairs of shapes that share a row, left to right."""
    pairs: List[Tuple[_Rec, _Rec]] = []
    remaining = sorted(records, key=lambda rec: (rec.box.y, rec.box.x))
    while remaining:
        head = remaining[0]
        row = [
            rec
            for rec in remaining
            if min(rec.box.y + rec.box.h, head.box.y + head.box.h)
            - max(rec.box.y, head.box.y)
            > min(rec.box.h, head.box.h) / 2
        ]
        remaining = [rec for rec in remaining if rec not in row]
        row.sort(key=lambda rec: rec.box.x)
        pairs.extend(zip(row, row[1:]))
    return pairs


def _figure_above_label(groups: Sequence[Sequence[_Rec]]) -> Optional[bool]:
    """Does the template put a figure above the words that name it?

    Looks for a bare quantity and the nearest text sharing its column. A
    template that shows no figure gets no answer, and the default stands.
    """
    above = below = 0
    for records in groups:
        texts = [rec for rec in records if rec.kind == "text" and rec.text.strip()]
        figures = [rec for rec in texts if FIGURE_TEXT.match(rec.text.strip())]
        for figure in figures:
            partner = _nearest_in_column(figure, texts)
            if partner is None:
                continue
            if figure.box.y < partner.box.y:
                above += 1
            else:
                below += 1
    if not (above or below):
        return None
    return above >= below


def _nearest_in_column(figure: _Rec, texts: Sequence[_Rec]) -> Optional[_Rec]:
    candidates = []
    for rec in texts:
        if rec is figure or FIGURE_TEXT.match(rec.text.strip()):
            continue
        overlap = min(rec.box.x + rec.box.w, figure.box.x + figure.box.w) - max(
            rec.box.x, figure.box.x
        )
        distance = abs(rec.box.y - figure.box.y)
        if overlap > min(rec.box.w, figure.box.w) / 2 and distance < 150:
            candidates.append((distance, rec))
    if not candidates:
        return None
    return min(candidates, key=lambda pair: pair[0])[1]


#: Shape names PowerPoint invents. An icon called "Picture 12" cannot be asked
#: for by name, so it is not offered at all (D22).
_GENERIC_NAME = __import__("re").compile(
    r"^(picture|image|graphic|imagen|grafik|forme|shape|freeform|group|rectangle|oval)"
    r"[\s_-]*\d*$",
    2,
)


_FILE_NAME = __import__("re").compile(
    r"\.(png|jpe?g|gif|bmp|tiff?|svg|emf|wmf|webp)$", 2
)


def _icon_name(rec: _Rec) -> Optional[str]:
    """What a reader would call this icon: its alt text, else its own name."""
    element = getattr(rec.shape, "_element", None)
    candidates = []
    if element is not None:
        node = element.find(f".//{qn('p:cNvPr')}")
        if node is not None:
            candidates.extend([node.get("descr") or "", node.get("title") or ""])
    candidates.append(rec.name or "")
    for candidate in candidates:
        name = candidate.strip()
        if not name or len(name) > 60 or _GENERIC_NAME.match(name):
            continue
        # A file name is what the picture was imported as, not what it means.
        if _FILE_NAME.search(name):
            continue
        return name
    return None


def _aspect_of(rec: _Rec) -> float:
    shape = cast(Any, rec.shape)
    width, height = getattr(shape, "width", None), getattr(shape, "height", None)
    if not width or not height:
        return 1.0
    return float(width) / float(height)


def _icons(records: Sequence[_Rec], slide_id: int) -> List[IconRef]:
    """The named pictures of one icon bank."""
    found: List[IconRef] = []
    for rec in records:
        if rec.kind != "picture":
            continue
        name = _icon_name(rec)
        if name is None or any(icon.name == name for icon in found):
            continue
        found.append(
            IconRef(
                name=name,
                slide_id=slide_id,
                key=rec.key,
                # From the shape's real EMU, never from its per-mille box: the
                # per-mille axes have different scales, so a square icon would
                # read as a wide one and be stretched back into the frame.
                aspect=_aspect_of(rec),
            )
        )
    return found


def _shape_language(
    groups: Sequence[Sequence[_Rec]], width: int, shorter: int
) -> ShapeLanguage:
    """How the template draws a block, read from the blocks it draws (D18)."""
    blocks = [rec for records in groups for rec in _blocks(records)]
    painted = [(rec, paint) for rec in blocks if (paint := _paint(rec)) is not None]
    filled = sum(1 for _, (is_filled, _) in painted if is_filled)
    outlined = sum(1 for _, (_, is_outlined) in painted if is_outlined)
    radii = [radius for rec, _ in painted if (radius := _radius_of(rec)) is not None]
    insets = [inset for rec, _ in painted if (inset := _inset_of(rec)) is not None]
    figure_first = _figure_above_label(groups)
    return ShapeLanguage(
        corner_radius=max(0.0, min(0.5, _median(radii))) if radii else 0.06,
        stroked=bool(painted and outlined * 2 >= len(painted)),
        filled=not painted or filled * 2 >= len(painted),
        padding=round(_median(insets) * 1000 / max(1, shorter)) if insets else None,
        column_gap=_column_gap(groups, width, shorter),
        figure_above_label=True if figure_first is None else figure_first,
    )


def _anchors(
    slide_records: Sequence[Sequence[_Rec]], layout_records: Sequence[Sequence[_Rec]]
) -> OpticalAnchors:
    """Where titles and content blocks start (D13).

    The template's own slides win over its master: that is the convention its
    reader recognises, even when it contradicts the master.
    """

    def read(
        groups: Sequence[Sequence[_Rec]],
    ) -> Optional[Tuple[int, int, Optional[int]]]:
        titles: List[int] = []
        bodies: List[int] = []
        footers: List[int] = []
        for records in groups:
            for rec in records:
                if rec.ph_type in _TITLE_PLACEHOLDERS:
                    titles.append(rec.box.y)
                elif rec.ph_type in ("BODY", "OBJECT", "SUBTITLE"):
                    bodies.append(rec.box.y)
                elif rec.box.y > 850 and rec.kind == "text":
                    footers.append(rec.box.y)
        if not titles and not bodies:
            return None
        title_y = min(titles) if titles else 90
        content_y = (
            min(y for y in bodies if y > title_y)
            if any(y > title_y for y in bodies)
            else title_y + 120
        )
        return title_y, content_y, (min(footers) if footers else None)

    from_slides = read(slide_records)
    if from_slides is not None:
        title_y, content_y, footer_y = from_slides
        return OpticalAnchors(
            title_y=title_y, content_y=content_y, footer_y=footer_y, source="slides"
        )
    from_master = read(layout_records)
    if from_master is not None:
        title_y, content_y, footer_y = from_master
        return OpticalAnchors(
            title_y=title_y, content_y=content_y, footer_y=footer_y, source="master"
        )
    return OpticalAnchors(title_y=90, content_y=260, source="master")


def build_design_system(
    *,
    presentation,
    slide_records: Sequence[Sequence[_Rec]],
    layout_records: Sequence[Sequence[_Rec]],
    theme: Tuple[Optional[str], Optional[str]],
    reserved: Sequence[Box] = (),
    content_slides: Optional[Sequence[Sequence[_Rec]]] = None,
    content_layouts: Optional[Sequence[Sequence[_Rec]]] = None,
    icons: Sequence[IconRef] = (),
) -> DesignSystem:
    """Read the template's tokens. Never invents a value it did not find."""
    width = presentation.slide_width or 1
    height = presentation.slide_height or 1
    flat = [
        rec for group in list(slide_records) + list(layout_records) for rec in group
    ]
    pairs, unreferenced = _build_pairs(
        theme_colors(presentation), _literal_colors(flat)
    )
    scale = _build_type_scale(flat, theme)

    # The base step is half a body line, the oldest rule there is for rhythm;
    # the ladder above it is that step doubled and halved.
    body = next((token for token in scale if token.role == "body"), None)
    shorter = min(width, height) or 1
    base = 12
    if body is not None:
        base = max(4, round(body.line_pt * 12700 * 0.5 * 1000 / shorter))
    steps = sorted({max(2, round(base * factor)) for factor in (0.5, 1, 1.5, 2.5, 4)})

    # The canvas already carries the template's fixtures; composing inside what
    # they leave free is how a composed slide keeps the logo it inherited.
    # Colours and type come from everything the template draws; the content
    # band and the anchors come from its CONTENT slides only.
    slides_for_layout = slide_records if content_slides is None else content_slides
    layouts_for_layout = layout_records if content_layouts is None else content_layouts
    content_flat = [
        rec
        for group in list(slides_for_layout) + list(layouts_for_layout)
        for rec in group
    ]
    area = free_area(_usable_area(content_flat, width, height), reserved)
    # Read per slide and per layout, not over one flat list: a gap only means
    # something between two shapes that share a row of the same page.
    groups = list(slide_records) + list(layout_records)
    language = _shape_language(groups, width, shorter)
    anchors = _anchors(slides_for_layout, layouts_for_layout)
    # The template's own slides put their title where the canvas has a band:
    # the ordinate moves down by what the band takes, and the content with it,
    # rather than the title disappearing under the charter (D13).
    if area.y > anchors.title_y:
        anchors = anchors.model_copy(
            update={
                "title_y": area.y,
                "content_y": anchors.content_y + area.y - anchors.title_y,
            }
        )
    return DesignSystem(
        slide_width=width,
        slide_height=height,
        pairs=pairs,
        type_scale=scale,
        spacing=SpacingScale(steps=steps),
        # The gutter is the template's own gap between two blocks when it shows
        # one; the scale only answers for a template that never put two side by
        # side (D18).
        grid=Grid(
            columns=12,
            area=area,
            gutter=language.column_gap or (steps[1] if len(steps) > 1 else base),
        ),
        shapes=language,
        anchors=anchors,
        unreferenced=unreferenced,
        reserved=list(reserved),
        icons=list(icons),
    )


class _Analyzer:
    def __init__(self, presentation) -> None:
        self.prs = presentation
        self.width = presentation.slide_width
        self.height = presentation.slide_height
        self.shared_texts: set[str] = set()
        self.icons: List[IconRef] = []
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
        layout_records: List[List[_Rec]] = []
        for index, layout in enumerate(layouts):
            if True:
                layout_records.append(
                    _records(
                        layout.shapes,
                        self.width,
                        self.height,
                        layout,
                        layout.slide_master,
                        self.theme,
                    )
                )
                pattern = self._layout_pattern(layout, index)
                patterns.append(pattern)
                if pattern.included:
                    layout_zone_sets[layout.name] = frozenset(
                        z.key for z in pattern.zones
                    )

        slide_intents: List[Optional[str]] = [None] * len(slide_records)
        for number, (slide, records) in enumerate(zip(slides, slide_records), start=1):
            pattern = self._slide_pattern(slide, number, records)
            if pattern is None:
                continue
            # Kept even for a slide dropped as a duplicate of its layout: the
            # geometry it carries is still a content slide's geometry.
            slide_intents[number - 1] = pattern.intent if pattern.included else None
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

        content_slides = [
            records
            for records, intent in zip(slide_records, slide_intents)
            if intent is not None and intent not in _NON_CONTENT_INTENTS
        ]
        content_layouts = [
            records
            for index, records in enumerate(layout_records)
            if index < len(patterns)
            and patterns[index].included
            and patterns[index].intent not in _NON_CONTENT_INTENTS
        ]
        content_flat = [
            rec for group in content_slides + content_layouts for rec in group
        ]
        base_area = _usable_area(content_flat, self.width, self.height)
        canvas_layout, reserved = self._canvas_layout(
            patterns, self._fixtures_per_layout(layouts, layout_records), base_area
        )

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
            analysis_version=ANALYSIS_VERSION,
            slide_width=self.width,
            slide_height=self.height,
            patterns=patterns,
            shared_texts=sorted(self.shared_texts),
            canvas_layout=canvas_layout,
            design_system=build_design_system(
                presentation=self.prs,
                slide_records=slide_records,
                layout_records=layout_records,
                theme=self.theme,
                reserved=reserved,
                content_slides=content_slides,
                content_layouts=content_layouts,
                icons=self.icons,
            ),
        )

    def _fixtures_per_layout(
        self, layouts: Sequence[Any], layout_records: Sequence[Sequence[_Rec]]
    ) -> List[List[Box]]:
        """What each layout would put under a slide of its own, per-mille."""
        masters: Dict[int, List[Box]] = {}
        per_layout: List[List[Box]] = []
        for index, layout in enumerate(layouts):
            boxes = list(_fixtures(layout_records[index]))
            master = layout.slide_master
            if _inherits_master(layout):
                if id(master) not in masters:
                    masters[id(master)] = _fixtures(
                        _records(
                            master.shapes,
                            self.width,
                            self.height,
                            None,
                            master,
                            self.theme,
                        )
                    )
                boxes += masters[id(master)]
            per_layout.append(boxes)
        return per_layout

    @staticmethod
    def _canvas_layout(
        patterns: Sequence[Pattern],
        fixtures: Sequence[Sequence[Box]],
        area: Box,
    ) -> Tuple[Optional[int], List[Box]]:
        """The layout composed slides are drawn on, and what it reserves.

        Not the emptiest one: a layout's own shapes are inherited by every
        slide using it, so the layout carrying the most of the template's
        furniture is the one that makes a composed slide look like the rest of
        the deck. It only qualifies if what it leaves free still holds a slide.
        Its exclusion stops being a failure and becomes a role.
        """
        candidates = [
            pattern
            for pattern in patterns
            if pattern.source == "layout"
            and pattern.exclusion_reason == "no_placeholder"
        ]
        dressed = [
            (pattern, list(fixtures[pattern.source_index]))
            for pattern in candidates
            if pattern.source_index < len(fixtures)
        ]
        if not dressed:
            return None, []
        floor = area.surface * MIN_FREE_SHARE
        usable = [
            (pattern, boxes)
            for pattern, boxes in dressed
            if free_area(area, boxes).surface >= floor
        ]
        if usable:
            chosen, reserved = max(
                usable,
                key=lambda pair: (
                    sum(box.surface for box in pair[1]),
                    -pair[0].source_index,
                ),
            )
        else:
            # Every dressed layout would crowd out the content: compose on the
            # barest one and keep the whole area rather than half a slide.
            chosen, reserved = min(dressed, key=lambda pair: len(pair[1]))[0], []
        chosen.exclusion_reason = "canvas"
        return chosen.source_index, reserved

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
            # The bank is not a slide to render, but its icons are a resource
            # the template offers and composing may draw on (D22).
            self.icons.extend(_icons(records, slide.slide_id))
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
    "ANALYSIS_VERSION",
    "analyze_presentation",
    "analyze_template",
    "estimate_capacity",
]
