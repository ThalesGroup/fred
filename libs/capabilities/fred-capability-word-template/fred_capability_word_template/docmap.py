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

"""The document map.

Every addressable element of a ``.docx`` gets an address, in reading
order, for the document's CURRENT state:

==================  ==============================================================
``P12``             body paragraph 12
``T3``              body table 3
``T3.R2``           row 2 of table 3 (used by ``repeat`` / ``remove``)
``T3.R2.C4``        a cell, at its first grid column; a merged cell appears once
``T3.R2.C4.P2``     a paragraph inside a cell (also ``T3.R2.C4.T1...``: nested)
``H1.P2``/``F1.P1`` header / footer paragraphs of section 1 (``H1f``/``H1e``:
                    first-page / even-page variants)
``X1.P3``           a text-box paragraph (``H1.X1.P1`` inside a header)
==================  ==============================================================

The map is a structured list of :class:`MapElement` (kept with their XML node
so operations can resolve addresses) plus a compact text rendering for the
model, split into readable parts.
"""

from __future__ import annotations

import colorsys
import io
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn

ElementKind = Literal[
    "paragraph", "table", "row", "cell", "header", "footer", "textbox"
]

_P = qn("w:p")
_TBL = qn("w:tbl")
_TR = qn("w:tr")
_TC = qn("w:tc")
_SDT = qn("w:sdt")
_SDT_CONTENT = qn("w:sdtContent")
_CUSTOM_XML = qn("w:customXml")
_TXBX_CONTENT = qn("w:txbxContent")
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_FALLBACK = f"{{{_MC_NS}}}Fallback"
_VML_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_TEXT_UNIT_TAGS = (qn("w:t"), qn("w:br"), qn("w:cr"), qn("w:tab"))

# Map text rendering knobs.
_MAX_PARAGRAPH_CHARS = 400
# A template text the writer keeps or replaces is shown whole, up to this.
_MAX_FULL_CHARS = 3000
_MAX_CELL_CHARS = 200
_COLLAPSE_EMPTY_RUN = 3
DEFAULT_CHUNK_SIZE = 40


@dataclass
class MapElement:
    """One addressable element of the document map.

    ``container`` is the address of the element holding it (``""`` for the
    body, ``"H1"``, ``"T2.R3.C1"``, ``"X1"``, ``"T2"`` for a row, ``"T2.R3"``
    for a cell); ``position`` is its 0-based index among its container's
    elements of the same family (blocks, rows or cells). ``node`` is the XML
    element, ``part`` the python-docx story part owning it.
    """

    address: str
    kind: ElementKind
    container: str
    position: int
    depth: int
    text: str = ""
    style: str | None = None
    heading_level: int | None = None
    color: str | None = None  # a colour name, when the text is not the body colour
    color_hex: str | None = None
    flags: tuple[str, ...] = ()
    rows: int | None = None  # table
    cols: int | None = None  # table
    col_span: int = 1  # cell
    row_span: int = 1  # cell
    full_width: bool = False  # cell
    label: str | None = None  # header / footer / text box description
    node: Any = field(default=None, repr=False, compare=False)
    part: Any = field(default=None, repr=False, compare=False)
    story: str = field(default="body", repr=False)  # "body", "header", "footer"
    in_textbox: bool = field(default=False, repr=False)
    color_weights: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def is_block(self) -> bool:
        return self.kind in ("paragraph", "table")


@dataclass
class DocMap:
    elements: list[MapElement]
    by_address: dict[str, MapElement] = field(repr=False)

    def get(self, address: str) -> MapElement | None:
        return self.by_address.get(address)

    def __getitem__(self, address: str) -> MapElement:
        return self.by_address[address]

    def children(self, container: str) -> list[MapElement]:
        return [e for e in self.elements if e.container == container]


@dataclass(frozen=True)
class MapPart:
    """A readable slice of the map: body elements between two top-level
    headings (or a fixed-size chunk), or the headers/footers (``"hf"``)."""

    part_id: str
    title: str
    first: str | None
    last: str | None
    size: int


# --- styles ----------------------------------------------------------------


@dataclass(frozen=True)
class _Style:
    style_id: str
    name: str
    based_on: str | None
    outline_level: int | None
    color: str | None
    bold: bool | None


def _on_off(element) -> bool | None:
    if element is None:
        return None
    return element.get(qn("w:val"), "true").lower() not in ("0", "false", "off")


def _color_of(rpr) -> str | None:
    """``None`` when not set, ``""`` for auto, else the upper-case hex."""
    if rpr is None:
        return None
    color = rpr.find(qn("w:color"))
    if color is None:
        return None
    value = (color.get(qn("w:val")) or "").upper()
    return "" if value in ("", "AUTO") else value


class _Styles:
    def __init__(self, document: DocxDocument) -> None:
        self._styles: dict[str, _Style] = {}
        self.default_paragraph: str | None = None
        root = document.styles.element
        for el in root.findall(qn("w:style")):
            style_id = el.get(qn("w:styleId")) or ""
            name_el = el.find(qn("w:name"))
            based = el.find(qn("w:basedOn"))
            ppr = el.find(qn("w:pPr"))
            outline = ppr.find(qn("w:outlineLvl")) if ppr is not None else None
            rpr = el.find(qn("w:rPr"))
            self._styles[style_id] = _Style(
                style_id=style_id,
                name=(name_el.get(qn("w:val")) if name_el is not None else None)
                or style_id,
                based_on=based.get(qn("w:val")) if based is not None else None,
                outline_level=_int(outline.get(qn("w:val")))
                if outline is not None
                else None,
                color=_color_of(rpr),
                bold=_on_off(rpr.find(qn("w:b"))) if rpr is not None else None,
            )
            if el.get(qn("w:type")) == "paragraph" and el.get(qn("w:default")) in (
                "1",
                "true",
            ):
                self.default_paragraph = style_id
        defaults = root.find(
            f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}"
        )
        self._default_color = _color_of(defaults) or ""
        self.body_color = self.color(None, self.default_paragraph) or ""

    def _chain(self, style_id: str | None) -> Iterator[_Style]:
        seen: set[str] = set()
        while style_id and style_id not in seen and style_id in self._styles:
            seen.add(style_id)
            style = self._styles[style_id]
            yield style
            style_id = style.based_on

    def name(self, style_id: str | None) -> str | None:
        style = self._styles.get(style_id or "")
        return style.name if style else None

    def outline_level(self, style_id: str | None) -> int | None:
        return next(
            (
                s.outline_level
                for s in self._chain(style_id)
                if s.outline_level is not None
            ),
            None,
        )

    def color(self, run, paragraph_style: str | None) -> str | None:
        if run is not None:
            rpr = run.find(qn("w:rPr"))
            direct = _color_of(rpr)
            if direct is not None:
                return direct
            if rpr is not None:
                rstyle = rpr.find(qn("w:rStyle"))
                if rstyle is not None:
                    for style in self._chain(rstyle.get(qn("w:val"))):
                        if style.color is not None:
                            return style.color
        for style in self._chain(paragraph_style or self.default_paragraph):
            if style.color is not None:
                return style.color
        return self._default_color

    def bold(self, run, paragraph_style: str | None) -> bool:
        rpr = run.find(qn("w:rPr"))
        if rpr is not None:
            direct = _on_off(rpr.find(qn("w:b")))
            if direct is not None:
                return direct
            rstyle = rpr.find(qn("w:rStyle"))
            if rstyle is not None:
                for style in self._chain(rstyle.get(qn("w:val"))):
                    if style.bold is not None:
                        return style.bold
        for style in self._chain(paragraph_style or self.default_paragraph):
            if style.bold is not None:
                return style.bold
        return False


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


# --- colours ---------------------------------------------------------------


def _is_dark(hex_color: str) -> bool:
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return True
    return max(r, g, b) < 0x40


def color_name(hex_color: str) -> str:
    """A short human colour name for ``hex_color`` (e.g. ``"blue"``,
    ``"dark blue"``, ``"grey"``), enough for the model to tell text apart."""
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return hex_color
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    if value < 0.25:
        return "black"
    if saturation < 0.2:
        return "white" if value > 0.95 else "grey"
    degrees = hue * 360
    names = (
        (15, "red"),
        (45, "orange"),
        (70, "yellow"),
        (170, "green"),
        (200, "cyan"),
        (260, "blue"),
        (300, "purple"),
        (345, "pink"),
        (360, "red"),
    )
    name = next(n for limit, n in names if degrees < limit)
    return f"dark {name}" if value < 0.45 else name


# --- text helpers ----------------------------------------------------------


def own_text_units(paragraph_element) -> list:
    """The paragraph's own text units in reading order - `w:t` nodes plus
    line breaks and tabs - not those of a paragraph nested inside it (a text
    box)."""
    return [
        node
        for node in paragraph_element.iter(*_TEXT_UNIT_TAGS)
        if next(node.iterancestors(_P), None) is paragraph_element
    ]


def own_runs(paragraph_element) -> list:
    """The paragraph's own runs (inside hyperlinks, content controls...),
    not those of a nested text-box paragraph."""
    return [
        r
        for r in paragraph_element.iter(qn("w:r"))
        if next(r.iterancestors(_P), None) is paragraph_element
    ]


def paragraph_text(paragraph_element) -> str:
    parts: list[str] = []
    for unit in own_text_units(paragraph_element):
        if unit.tag == qn("w:t"):
            parts.append(unit.text or "")
        elif unit.tag == qn("w:tab"):
            parts.append(" ")
        else:
            br_type = unit.get(qn("w:type"))
            parts.append("" if br_type in ("page", "column") else "\n")
    return "".join(parts)


def _paragraph_style_id(paragraph_element) -> str | None:
    style = paragraph_element.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return style.get(qn("w:val")) if style is not None else None


def _has_own(paragraph_element, tag: str) -> bool:
    return any(
        next(node.iterancestors(_P), None) is paragraph_element
        for node in paragraph_element.iter(tag)
    )


# A picture the engine placed from ``![caption](img:<id>)`` carries its id
# in its drawing's ``wp:docPr/@name`` and its caption in ``@descr``.
PLACED_IMAGE_PREFIX = "img:"
_DOC_PR = (
    "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
)


def placed_image(paragraph_element) -> tuple[str, str] | None:
    """``(image_id, caption)`` when the paragraph holds exactly one picture
    the engine placed and no text, else None."""
    if paragraph_text(paragraph_element).strip():
        return None
    found = [
        node
        for node in paragraph_element.iter(_DOC_PR)
        if next(node.iterancestors(_P), None) is paragraph_element
    ]
    if len(found) != 1:
        return None
    name = found[0].get("name") or ""
    if not name.startswith(PLACED_IMAGE_PREFIX) or len(name) <= len(
        PLACED_IMAGE_PREFIX
    ):
        return None
    return name[len(PLACED_IMAGE_PREFIX) :], found[0].get("descr") or ""


def block_children(container) -> list:
    """The paragraphs and tables of a container, in order, looking through
    block-level content controls and custom XML."""
    out: list = []
    for child in container:
        if child.tag in (_P, _TBL):
            out.append(child)
        elif child.tag == _SDT:
            content = child.find(_SDT_CONTENT)
            if content is not None:
                out.extend(block_children(content))
        elif child.tag == _CUSTOM_XML:
            out.extend(block_children(child))
    return out


def row_cells(row) -> list:
    out: list = []
    for child in row:
        if child.tag == _TC:
            out.append(child)
        elif child.tag == _SDT:
            content = child.find(_SDT_CONTENT)
            if content is not None:
                out.extend(row_cells(content))
        elif child.tag == _CUSTOM_XML:
            out.extend(row_cells(child))
    return out


def table_rows(table) -> list:
    out: list = []
    for child in table:
        if child.tag == _TR:
            out.append(child)
        elif child.tag in (_SDT, _CUSTOM_XML):
            content = child.find(_SDT_CONTENT) if child.tag == _SDT else child
            if content is not None:
                out.extend(r for r in content if r.tag == _TR)
    return out


def own_textboxes(paragraph_element) -> list:
    """Text-box contents anchored in this paragraph, the DrawingML copy only
    (the VML ``mc:Fallback`` duplicate is skipped and synced on edit)."""
    out = []
    for content in paragraph_element.iter(_TXBX_CONTENT):
        if next(content.iterancestors(_P), None) is not paragraph_element:
            continue
        if any(a.tag == _FALLBACK for a in content.iterancestors()):
            continue
        out.append(content)
    return out


def _cell_span(cell) -> int:
    span = cell.find(f"{qn('w:tcPr')}/{qn('w:gridSpan')}")
    return max(1, _int(span.get(qn("w:val"))) or 1) if span is not None else 1


def _cell_vmerge(cell) -> str | None:
    """``"restart"``, ``"continue"`` or None."""
    merge = cell.find(f"{qn('w:tcPr')}/{qn('w:vMerge')}")
    if merge is None:
        return None
    return "restart" if merge.get(qn("w:val")) == "restart" else "continue"


def _grid_before(row) -> int:
    before = row.find(f"{qn('w:trPr')}/{qn('w:gridBefore')}")
    return (_int(before.get(qn("w:val"))) or 0) if before is not None else 0


def cell_grid(table) -> list[list[tuple[int, Any]]]:
    """Per row, the (0-based grid column, cell) of each cell."""
    grid: list[list[tuple[int, Any]]] = []
    for row in table_rows(table):
        column = _grid_before(row)
        cells: list[tuple[int, Any]] = []
        for cell in row_cells(row):
            cells.append((column, cell))
            column += _cell_span(cell)
        grid.append(cells)
    return grid


def table_columns(table) -> int:
    grid_cols = table.findall(f"{qn('w:tblGrid')}/{qn('w:gridCol')}")
    widest = max(
        (
            _grid_before(row) + sum(_cell_span(c) for c in row_cells(row))
            for row in table_rows(table)
        ),
        default=0,
    )
    return max(len(grid_cols), widest)


# --- map building ----------------------------------------------------------


class _Builder:
    def __init__(self, document: DocxDocument) -> None:
        self.document = document
        self.styles = _Styles(document)
        self.elements: list[MapElement] = []

    def add(self, element: MapElement) -> MapElement:
        self.elements.append(element)
        return element

    # A story: body, header or footer root.
    def story(self, root, prefix: str, part, story: str) -> None:
        textbox_counter = [0]
        self.container(
            root, prefix, part, story, depth=0, textboxes=textbox_counter, in_tb=False
        )

    def container(
        self,
        node,
        prefix: str,
        part,
        story: str,
        *,
        depth: int,
        textboxes: list[int],
        in_tb: bool,
        story_prefix: str | None = None,
    ) -> None:
        story_prefix = prefix if story_prefix is None else story_prefix
        p_count = t_count = 0
        base = f"{prefix}." if prefix else ""
        for position, child in enumerate(block_children(node)):
            if child.tag == _P:
                p_count += 1
                self.paragraph(
                    child,
                    f"{base}P{p_count}",
                    prefix,
                    position,
                    depth,
                    part,
                    story,
                    in_tb,
                )
                for content in own_textboxes(child):
                    textboxes[0] += 1
                    sbase = f"{story_prefix}." if story_prefix else ""
                    address = f"{sbase}X{textboxes[0]}"
                    self.add(
                        MapElement(
                            address=address,
                            kind="textbox",
                            container=prefix,
                            position=-1,
                            depth=depth + 1,
                            label=f"text box anchored in {base}P{p_count}",
                            node=content,
                            part=part,
                            story=story,
                            in_textbox=True,
                        )
                    )
                    self.container(
                        content,
                        address,
                        part,
                        story,
                        depth=depth + 2,
                        textboxes=textboxes,
                        in_tb=True,
                        story_prefix=story_prefix,
                    )
            else:
                t_count += 1
                self.table(
                    child,
                    f"{base}T{t_count}",
                    prefix,
                    position,
                    depth,
                    part,
                    story,
                    textboxes,
                    in_tb,
                    story_prefix,
                )

    def paragraph(
        self, node, address, container, position, depth, part, story, in_tb
    ) -> MapElement:
        style_id = _paragraph_style_id(node) or self.styles.default_paragraph
        text = paragraph_text(node)
        level = None
        direct_outline = node.find(f"{qn('w:pPr')}/{qn('w:outlineLvl')}")
        if text.strip():
            outline = (
                _int(direct_outline.get(qn("w:val")))
                if direct_outline is not None
                else self.styles.outline_level(style_id)
            )
            if outline is not None and 0 <= outline <= 8:
                level = outline + 1
            else:
                name = (self.styles.name(style_id) or "").lower()
                match = re.fullmatch(r"heading (\d)", name)
                if match:
                    level = int(match.group(1))
        flags: list[str] = []
        weights: dict[str, int] = {}
        runs = [r for r in own_runs(node) if paragraph_text_of_run(r).strip()]
        if runs:
            total = 0
            bold_chars = 0
            for run in runs:
                length = len(paragraph_text_of_run(run).strip())
                total += length
                run_color = self.styles.color(run, style_id) or ""
                weights[run_color] = weights.get(run_color, 0) + length
                if self.styles.bold(run, style_id):
                    bold_chars += length
            if level is None and bold_chars == total:
                flags.append("bold")
        if _has_own(node, qn("a:blip")) or _has_own(node, _VML_IMAGEDATA):
            flags.append("image")
            placed = placed_image(node)
            if placed is not None:
                flags.append(f"{PLACED_IMAGE_PREFIX}{placed[0]}")
        if node.find(f"{qn('w:pPr')}/{qn('w:sectPr')}") is not None:
            flags.append("section break")
        if (
            any(
                br.get(qn("w:type")) == "page"
                for br in own_text_units(node)
                if br.tag == qn("w:br")
            )
            or node.find(f"{qn('w:pPr')}/{qn('w:pageBreakBefore')}") is not None
        ):
            flags.append("page break")
        if level is None and node.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None:
            flags.append("list")
        style_name = self.styles.name(style_id)
        return self.add(
            MapElement(
                address=address,
                kind="paragraph",
                container=container,
                position=position,
                depth=depth,
                text=text,
                style=style_name,
                heading_level=level,
                flags=tuple(flags),
                color_weights=weights,
                node=node,
                part=part,
                story=story,
                in_textbox=in_tb,
            )
        )

    def table(
        self,
        node,
        address,
        container,
        position,
        depth,
        part,
        story,
        textboxes,
        in_tb,
        story_prefix,
    ) -> None:
        rows = table_rows(node)
        columns = table_columns(node)
        style_el = node.find(f"{qn('w:tblPr')}/{qn('w:tblStyle')}")
        self.add(
            MapElement(
                address=address,
                kind="table",
                container=container,
                position=position,
                depth=depth,
                rows=len(rows),
                cols=columns,
                style=self.styles.name(style_el.get(qn("w:val")))
                if style_el is not None
                else None,
                node=node,
                part=part,
                story=story,
                in_textbox=in_tb,
            )
        )
        grid = cell_grid(node)
        for r_index, (row, cells) in enumerate(zip(rows, grid)):
            row_address = f"{address}.R{r_index + 1}"
            self.add(
                MapElement(
                    address=row_address,
                    kind="row",
                    container=address,
                    position=r_index,
                    depth=depth + 1,
                    node=row,
                    part=part,
                    story=story,
                    in_textbox=in_tb,
                )
            )
            c_position = 0
            for column, cell in cells:
                if _cell_vmerge(cell) == "continue":
                    continue
                span = _cell_span(cell)
                row_span = 1
                if _cell_vmerge(cell) == "restart":
                    for below in grid[r_index + 1 :]:
                        if any(
                            col == column and _cell_vmerge(c) == "continue"
                            for col, c in below
                        ):
                            row_span += 1
                        else:
                            break
                cell_address = f"{row_address}.C{column + 1}"
                element = self.add(
                    MapElement(
                        address=cell_address,
                        kind="cell",
                        container=row_address,
                        position=c_position,
                        depth=depth + 1,
                        col_span=span,
                        row_span=row_span,
                        full_width=span >= columns > 1,
                        node=cell,
                        part=part,
                        story=story,
                        in_textbox=in_tb,
                    )
                )
                c_position += 1
                first_child = len(self.elements)
                self.container(
                    cell,
                    cell_address,
                    part,
                    story,
                    depth=depth + 2,
                    textboxes=textboxes,
                    in_tb=in_tb,
                    story_prefix=story_prefix,
                )
                inner = [
                    e
                    for e in self.elements[first_child:]
                    if e.container == cell_address and e.kind == "paragraph"
                ]
                element.text = "\n".join(e.text for e in inner)
                element.color_weights = _merge_weights(e.color_weights for e in inner)
                texts = [e for e in inner if e.text.strip()]
                if texts and all("bold" in e.flags for e in texts):
                    element.flags = ("bold",)

    def finalize(self) -> None:
        """Name the colour of every paragraph and cell whose text is not in
        the body colour: the default paragraph style's colour, and inside
        tables the document's dominant colour too (a form typed in one colour
        must not flag every cell; a guidance-heavy body must still show its
        guidance)."""
        totals = _merge_weights(
            e.color_weights for e in self.elements if e.kind == "paragraph"
        )
        body_defaults = {"", self.styles.body_color}
        cell_defaults = set(body_defaults)
        if totals:
            cell_defaults.add(max(totals, key=totals.__getitem__))
        for element in self.elements:
            if element.kind not in ("paragraph", "cell") or element.heading_level:
                continue
            defaults = cell_defaults if ".C" in element.address else body_defaults
            weights = element.color_weights
            total = sum(weights.values())
            notable = {
                c: w
                for c, w in weights.items()
                if c not in defaults and not _is_dark(c)
            }
            if not notable or not total:
                continue
            element.color_hex = max(notable, key=notable.__getitem__)
            name = color_name(element.color_hex)
            element.color = (
                name if sum(notable.values()) / total >= 0.6 else f"partly {name}"
            )


def _merge_weights(items) -> dict[str, int]:
    merged: dict[str, int] = {}
    for weights in items:
        for color, weight in weights.items():
            merged[color] = merged.get(color, 0) + weight
    return merged


def paragraph_text_of_run(run) -> str:
    return "".join(
        (t.text or "") if t.tag == qn("w:t") else " "
        for t in run.iter(*_TEXT_UNIT_TAGS)
    )


NOT_SHOWN = "never shown by Word in this document"


def _header_footer_parts(document: DocxDocument) -> list[tuple[str, str, Any]]:
    """(address, label, part) for every header/footer a section defines. A
    first-page one without the section's "different first page", or an
    even-page one without the document's odd/even pages, is never shown."""
    out: list[tuple[str, str, Any]] = []
    seen: set[int] = set()
    suffixes = {"default": "", "first": "f", "even": "e"}
    variants = {"default": "", "first": ", first page", "even": ", even pages"}
    odd_and_even = document.settings.odd_and_even_pages_header_footer
    for s_index, section in enumerate(document.sections, start=1):
        sect_pr = section._sectPr
        shown = {
            "default": True,
            "first": section.different_first_page_header_footer,
            "even": odd_and_even,
        }
        for tag, letter, kind in (
            ("w:headerReference", "H", "header"),
            ("w:footerReference", "F", "footer"),
        ):
            for ref in sect_pr.findall(qn(tag)):
                variant = ref.get(qn("w:type")) or "default"
                rel_id = ref.get(qn("r:id"))
                part = document.part.related_parts.get(rel_id) if rel_id else None
                if part is None or id(part) in seen:
                    continue
                seen.add(id(part))
                address = f"{letter}{s_index}{suffixes.get(variant, '')}"
                hidden = "" if shown.get(variant, True) else f", {NOT_SHOWN}"
                out.append(
                    (
                        address,
                        f"{kind} (section {s_index}{variants.get(variant, '')}{hidden})",
                        part,
                    )
                )
    order = {"H": 0, "F": 1}
    out.sort(key=lambda item: order[item[0][0]])
    return out


def build_map_from_document(document: DocxDocument) -> DocMap:
    builder = _Builder(document)
    builder.story(document.element.body, "", document.part, "body")
    for address, label, part in _header_footer_parts(document):
        story = "header" if address.startswith("H") else "footer"
        builder.add(
            MapElement(
                address=address,
                kind=story,
                container="",
                position=-1,
                depth=0,
                label=label,
                flags=("hidden",) if NOT_SHOWN in label else (),
                node=part.element,
                part=part,
                story=story,
            )
        )
        builder.story(part.element, address, part, story)
    builder.finalize()
    elements = builder.elements
    return DocMap(elements=elements, by_address={e.address: e for e in elements})


def build_map(docx_bytes: bytes) -> DocMap:
    """The map of a ``.docx`` in its current state."""
    return build_map_from_document(Document(io.BytesIO(docx_bytes)))


# --- text rendering --------------------------------------------------------


def _quote(text: str, limit: int) -> str:
    flat = text.replace("\n", " ⏎ ").strip()
    if not flat:
        return "∅"
    if len(flat) > limit:
        flat = f"{flat[:limit]}... (+{len(flat) - limit} chars)"
    return f'"{flat}"'


_NOTE_WORD = (
    r"(?:(?:partly )?(?:dark )?(?:black|white|grey|red|orange|yellow|green|cyan|"
    r"blue|purple|pink)|bold|image|list|section break|page break|img:\S+)"
)
# The map's own notes on an element ("{blue, bold}"), never document text.
MAP_NOTE_RE = re.compile(rf"\{{\s*{_NOTE_WORD}(?:\s*,\s*{_NOTE_WORD})*\s*\}}")


def _decorations(element: MapElement) -> str:
    bits = list(element.flags)
    if element.color:
        bits.insert(0, element.color)
    return f" {{{', '.join(bits)}}}" if bits else ""


def _local(address: str) -> str:
    return address.rsplit(".", 1)[-1]


def _paragraph_tag(element: MapElement) -> str:
    tag = element.address
    if element.heading_level is not None:
        tag += f" heading {element.heading_level}"
        if element.style and not re.fullmatch(
            r"heading \d", element.style, re.IGNORECASE
        ):
            tag += f' "{element.style}"'
    elif element.style and element.style.lower() not in ("normal", "default"):
        tag += f' "{element.style}"'
    return f"[{tag}]"


def _is_plain_empty(element: MapElement) -> bool:
    return (
        element.kind == "paragraph"
        and not element.text.strip()
        and not element.flags
        and element.heading_level is None
    )


class _Renderer:
    def __init__(self, doc_map: DocMap, full: frozenset[str] = frozenset()) -> None:
        self.map = doc_map
        self.full = full
        self.children: dict[str, list[MapElement]] = {}
        self.textboxes: dict[str, list[MapElement]] = {}
        for element in doc_map.elements:
            if element.kind == "textbox":
                anchor = (element.label or "").rsplit(" ", 1)[-1]
                self.textboxes.setdefault(anchor, []).append(element)
            else:
                self.children.setdefault(element.container, []).append(element)

    def _limit(self, element: MapElement) -> int:
        full = element.text.strip() in self.full
        return _MAX_FULL_CHARS if full else _MAX_PARAGRAPH_CHARS

    def blocks(self, elements: Sequence[MapElement], indent: int) -> list[str]:
        lines: list[str] = []
        pad = "  " * indent
        i = 0
        while i < len(elements):
            element = elements[i]
            j = i
            while j < len(elements) and _is_plain_empty(elements[j]):
                if elements[j].address in self.textboxes:
                    break
                j += 1
            if j - i >= _COLLAPSE_EMPTY_RUN:
                lines.append(
                    f"{pad}[{elements[i].address}–{_local(elements[j - 1].address)}] ∅ ×{j - i}"
                )
                i = j
                continue
            if element.kind == "paragraph":
                lines.append(
                    f"{pad}{_paragraph_tag(element)} "
                    f"{_quote(element.text, self._limit(element))}{_decorations(element)}"
                )
                for box in self.textboxes.get(element.address, []):
                    lines.append(f"{pad}  [{box.address}] text box")
                    lines.extend(
                        self.blocks(self.children.get(box.address, []), indent + 2)
                    )
            elif element.kind == "table":
                lines.extend(self.table(element, indent))
            i += 1
        return lines

    def table(self, table: MapElement, indent: int) -> list[str]:
        pad = "  " * indent
        style = f', style "{table.style}"' if table.style else ""
        lines = [
            f"{pad}[{table.address}] table, {table.rows} rows × {table.cols} cols{style}"
        ]
        for row in self.children.get(table.address, []):
            cells = self.children.get(row.address, [])
            if not cells:
                lines.append(
                    f"{pad}  {_local(row.address)}: (merged with the row above)"
                )
                continue
            rendered: list[str] = []
            details: list[str] = []
            for cell in cells:
                inner = self.children.get(cell.address, [])
                notes: list[str] = []
                if cell.full_width:
                    notes.append("full width")
                elif cell.col_span > 1:
                    notes.append(f"spans {cell.col_span} cols")
                if cell.row_span > 1:
                    notes.append(f"spans {cell.row_span} rows")
                note = f" - {', '.join(notes)}" if notes else ""
                complex_cell = len(inner) > 1 or any(
                    e.kind == "table" or e.address in self.textboxes for e in inner
                )
                if complex_cell:
                    rendered.append(
                        f"[{_local(cell.address)}: {len(inner)} blocks, below{note}]"
                    )
                    details.extend(self.blocks(inner, indent + 2))
                else:
                    paragraph = inner[0] if inner else None
                    style = ""
                    if paragraph is not None and paragraph.heading_level is not None:
                        style = f" heading {paragraph.heading_level}"
                    decorations = _decorations(paragraph) if paragraph else ""
                    rendered.append(
                        f"[{_local(cell.address)}{style} "
                        f"{_quote(cell.text, _MAX_CELL_CHARS)}{decorations}{note}]"
                    )
            lines.append(f"{pad}  {_local(row.address)}: {' '.join(rendered)}")
            lines.extend(details)
        return lines

    def story(self, story: MapElement) -> list[str]:
        lines = [f"[{story.address}] {story.label}"]
        lines.extend(self.blocks(self.children.get(story.address, []), 1))
        return lines


def render_map(doc_map: DocMap) -> str:
    """The whole map as compact text (body, then headers and footers)."""
    renderer = _Renderer(doc_map)
    lines = renderer.blocks(renderer.children.get("", []), 0)
    for element in doc_map.elements:
        if element.kind in ("header", "footer"):
            lines.extend(renderer.story(element))
    return "\n".join(lines)


def _top_level(doc_map: DocMap) -> list[MapElement]:
    return [e for e in doc_map.elements if e.container == "" and e.is_block]


def _part_title(doc_map: DocMap, elements: Sequence[MapElement]) -> str:
    """The part's first heading, else its first text (looking into tables)."""
    heading = next((e for e in elements if e.heading_level is not None), None)
    if heading is not None:
        return _quote(heading.text, 80).strip('"')
    for element in elements:
        if element.kind == "paragraph" and element.text.strip():
            return _quote(element.text, 80).strip('"')
        if element.kind == "table":
            prefix = f"{element.address}."
            cell = next(
                (
                    e
                    for e in doc_map.elements
                    if e.kind == "paragraph"
                    and e.address.startswith(prefix)
                    and e.text.strip()
                ),
                None,
            )
            if cell is not None:
                return _quote(cell.text, 80).strip('"')
    return "(empty)"


def _split(doc_map: DocMap, chunk_size: int) -> list[list[list[MapElement]]]:
    """The top-level elements as chapters (at the top-level headings), each
    as one or more chunks: an overlong chapter is read in pieces. Without
    headings, every chunk is a chapter of its own."""
    top = _top_level(doc_map)
    levels = [e.heading_level for e in top if e.heading_level is not None]
    if not levels:
        return [[top[i : i + chunk_size]] for i in range(0, len(top), chunk_size)]
    split_level = min(levels)
    chapters: list[list[MapElement]] = []
    for element in top:
        if element.heading_level == split_level or not chapters:
            chapters.append([])
        chapters[-1].append(element)
    return [
        [chapter]
        if len(chapter) <= chunk_size * 2
        else [chapter[i : i + chunk_size] for i in range(0, len(chapter), chunk_size)]
        for chapter in chapters
    ]


def numbered_groups(
    doc_map: DocMap, chunk_size: int
) -> list[tuple[str, list[MapElement]]]:
    """The parts' ids and blocks. What comes before the first heading (a
    cover page) is part "0", so part N is the chapter the template numbers N
    whatever the length of the chapters before it; the pieces of an overlong
    chapter are "N", "Nb", "Nc"... A document without headings counts from "1"."""
    chapters = _split(doc_map, chunk_size)
    has_heading = any(e.heading_level is not None for e in _top_level(doc_map))
    cover = has_heading and chapters and chapters[0][0][0].heading_level is None
    first = 0 if cover else 1
    return [
        (f"{first + i}{_piece_suffix(j)}", chunk)
        for i, chunks in enumerate(chapters)
        for j, chunk in enumerate(chunks)
    ]


def _piece_suffix(index: int) -> str:
    if index == 0:
        return ""
    return chr(ord("a") + index) if index < 26 else f"-{index + 1}"


_PIECE_RE = re.compile(r"^(\d+)(?:[a-z]|-\d+)$")


def word_numbered(paragraph: Any, styles: Any) -> bool:
    """Whether Word numbers this paragraph itself (its own or its style's
    numbering); ``styles`` is the document's python-docx styles."""
    if paragraph.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None:
        return True
    style_el = paragraph.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    style = (
        styles.element.get_by_id(style_el.get(qn("w:val")))
        if style_el is not None
        else None
    )
    for _ in range(10):
        if style is None:
            return False
        if style.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None:
            return True
        based = style.find(qn("w:basedOn"))
        style = (
            styles.element.get_by_id(based.get(qn("w:val")))
            if based is not None
            else None
        )
    return False


def heading_numbers(doc_map: DocMap) -> dict[str, str]:
    """The number Word shows before each numbered body heading ("1.3.1"),
    by address."""
    headings = [
        e
        for e in doc_map.elements
        if e.heading_level is not None
        and e.kind == "paragraph"
        and e.container == ""
        and e.story == "body"
        and e.part is not None
        and word_numbered(e.node, e.part.styles)
    ]
    if not headings:
        return {}
    top = min(e.heading_level or 0 for e in headings)
    counts: list[int] = []
    numbers: dict[str, str] = {}
    for e in headings:
        depth = (e.heading_level or 0) - top
        counts = counts[: depth + 1] + [0] * (depth + 1 - len(counts))
        counts[depth] += 1
        numbers[e.address] = ".".join(str(c) for c in counts)
    return numbers


def outline(doc_map: DocMap, part_id: str) -> str | None:
    """The headings of a chapter as they are now, with the numbers Word
    gives them, for the model to describe the structure from what is there
    rather than from what it meant to do (or counted itself). None for the
    cover page, headers/footers or a chapter without heading."""
    chapter = chapter_of(part_id)
    headings = [
        e
        for group_id, group in numbered_groups(doc_map, DEFAULT_CHUNK_SIZE)
        if chapter_of(group_id) == chapter
        for e in group
        if e.heading_level is not None
    ]
    if not headings:
        return None
    numbers = heading_numbers(doc_map)

    def label(e: MapElement) -> str:
        number = numbers.get(e.address)
        return f'{number} "{e.text.strip()}"' if number else f'"{e.text.strip()}"'

    top, rest = headings[0], headings[1:]
    subs = (
        "; ".join(
            f"{'  ' * (e.heading_level - top.heading_level - 1)}{label(e)}"
            for e in rest
            if e.heading_level and top.heading_level
        )
        or "none"
    )
    return f"OUTLINE of chapter {chapter} now: {label(top)}; sub-headings: {subs}"


def chapter_of(part_id: str) -> str:
    """The chapter a part belongs to: "5" for the pieces "5", "5b", "5c"."""
    piece = _PIECE_RE.match(part_id)
    return piece.group(1) if piece else part_id


_BEFORE_HEADINGS = "before the first heading"


def _title(
    doc_map: DocMap, part_id: str, group: Sequence[MapElement], titles: dict[str, str]
) -> str:
    """A part's title; a later piece of a chapter is named after the chapter."""
    if part_id == "0":
        return _BEFORE_HEADINGS
    chapter = chapter_of(part_id)
    if chapter != part_id and chapter in titles:
        return f"{titles[chapter]} (continued)"
    titles[part_id] = _part_title(doc_map, group)
    return titles[part_id]


def parts(doc_map: DocMap, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[MapPart]:
    """The map split into readable parts: at the top-level headings (a
    heading-less document, or an overlong chapter, in chunks of
    ``chunk_size`` top-level elements), plus ``"hf"`` for the headers and
    footers when the document has any."""
    titles: dict[str, str] = {}
    out = [
        MapPart(
            part_id=part_id,
            title=_title(doc_map, part_id, group, titles),
            first=group[0].address,
            last=group[-1].address,
            size=len(group),
        )
        for part_id, group in numbered_groups(doc_map, chunk_size)
    ]
    stories = [e for e in doc_map.elements if e.kind in ("header", "footer")]
    if stories:
        out.append(
            MapPart(
                part_id="hf",
                title="headers and footers",
                first=stories[0].address,
                last=stories[-1].address,
                size=len(stories),
            )
        )
    return out


def render_parts(doc_map: DocMap, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """One line per part, for the model to choose what to read."""
    return "\n".join(
        f"part {p.part_id}: {p.title} ({p.first}–{p.last}, {p.size} elements)"
        if p.first != p.last
        else f"part {p.part_id}: {p.title} ({p.first})"
        for p in parts(doc_map, chunk_size=chunk_size)
    )


def _texts_under(doc_map: DocMap, elements: Sequence[MapElement]) -> list[MapElement]:
    """The paragraphs of ``elements`` and of everything nested in them."""
    prefixes = tuple(f"{e.address}." for e in elements)
    own = {e.address for e in elements}
    return [
        e
        for e in doc_map.elements
        if e.kind == "paragraph"
        and (e.address in own or e.address.startswith(prefixes))
    ]


LeftoverKind = Literal["template", "field", "marker", "empty"]


@dataclass(frozen=True)
class Leftover:
    """A place of a part that still needs the writer: the base's guidance,
    sample or placeholder text ("template"), a placeholder inside fixed
    wording ("field"), a heading with nothing under it ("empty"), or an
    [À COMPLÉTER] marker ("marker", not an error)."""

    address: str
    text: str
    kind: LeftoverKind
    where: str


@dataclass(frozen=True)
class PartCheck:
    part_id: str
    title: str
    leftovers: tuple[Leftover, ...]
    empty: bool  # a body part with nothing written under its heading

    @property
    def places_left(self) -> int:
        return sum(1 for left in self.leftovers if left.kind != "marker")

    @property
    def finished(self) -> bool:
        return not self.empty and self.places_left == 0


def top_block(doc_map: DocMap, element: MapElement | None) -> str | None:
    """The top-level body block holding ``element``, following text boxes
    to the paragraph they are anchored in."""
    for _ in range(50):
        if element is None:
            return None
        if element.kind == "textbox":
            element = doc_map.get((element.label or "").rsplit(" ", 1)[-1])
            continue
        if not element.container:
            return element.address
        element = doc_map.get(element.container)
    return None


def is_toc(element: MapElement) -> bool:
    return (element.style or "").lower().startswith("toc")


def _where(doc_map: DocMap, element: MapElement, order: Mapping[str, int]) -> str:
    """Where a place is, in words: its row's first cell, else the nearest
    heading above it, else its header or footer."""
    if element.story != "body":
        story = doc_map.get(element.address.split(".", 1)[0])
        return (story.label if story is not None else None) or element.story
    cell = doc_map.get(element.container)
    if cell is not None and cell.kind == "cell":
        first = next(iter(doc_map.children(cell.container)), None)
        if first is not None and first.address != cell.address and first.text.strip():
            return f'row "{_quote(first.text, 40).strip(chr(34))}"'
    top = element.address.split(".", 1)[0]
    index = order.get(top, -1)
    heading = next(
        (
            e
            for e in reversed(doc_map.elements[: max(index, 0)])
            if e.heading_level is not None and e.container == ""
        ),
        None,
    )
    return (
        f'under "{_quote(heading.text, 60).strip(chr(34))}"'
        if heading
        else "before the first heading"
    )


def check_parts(
    doc_map: DocMap,
    template_texts: frozenset[str],
    field_texts: frozenset[str] = frozenset(),
    *,
    notes: Mapping[str, str] | None = None,
    is_marker: Callable[[str], bool] = lambda _text: False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[PartCheck]:
    """Each part's places still needing the writer, found by text so the
    check follows removals, insertions and repeats: ``template_texts`` are
    the base's texts to replace, ``field_texts`` its fixed paragraphs holding
    a placeholder; ``notes`` name a text in words (the analysis' notes).
    Table-of-contents lines are left out."""
    notes = notes or {}
    order = {e.address: i for i, e in enumerate(doc_map.elements)}
    groups = numbered_groups(doc_map, chunk_size)
    # A header or footer Word never shows has no place to fill.
    stories = [
        e
        for e in doc_map.elements
        if e.kind in ("header", "footer") and "hidden" not in e.flags
    ]
    if stories:
        groups.append(("hf", stories))
    titles = {p.part_id: p.title for p in parts(doc_map, chunk_size=chunk_size)}
    # Body text boxes belong to the block they are anchored in.
    anchored: dict[str, list[MapElement]] = {}
    for e in doc_map.elements:
        if e.kind == "paragraph" and e.story == "body" and e.address.startswith("X"):
            if (anchor := top_block(doc_map, e)) is not None:
                anchored.setdefault(anchor, []).append(e)
    checks: list[PartCheck] = []
    for part_id, group in groups:
        paragraphs = _texts_under(doc_map, group) + [
            p for block in group for p in anchored.get(block.address, [])
        ]
        leftovers: list[Leftover] = []
        for p in paragraphs:
            text = p.text.strip()
            if not text or is_toc(p):
                continue
            kind: LeftoverKind | None = (
                "template"
                if text in template_texts
                else "field"
                if text in field_texts
                else "marker"
                if is_marker(text)
                else None
            )
            if kind is not None:
                where = notes.get(text) or _where(doc_map, p, order)
                leftovers.append(Leftover(p.address, text, kind, where))
        written = [p for p in paragraphs if p.text.strip() and p.heading_level is None]
        has_table = any(e.kind == "table" for e in group)
        empty = part_id != "hf" and not written and not has_table
        if not empty:
            leftovers.extend(_empty_headings(doc_map, group, anchored))
        checks.append(
            PartCheck(
                part_id=part_id,
                title=titles.get(part_id, ""),
                leftovers=tuple(leftovers),
                empty=empty,
            )
        )
    return checks


@dataclass(frozen=True)
class UnusedRange:
    start: str
    end: str
    label: str


def unused_template_ranges(
    doc_map: DocMap,
    template_texts: frozenset[str],
    base_texts: frozenset[str],
    *,
    is_marker: Callable[[str], bool] = lambda _text: False,
) -> list[UnusedRange]:
    """The body's unused template parts after the cover page: a section whose
    heading still holds sample text and whose content is all untouched base
    content, and elsewhere a paragraph or table holding only sample text (an
    empty frame included). Fixed wording and anything written are kept."""
    top = [e for e in _top_level(doc_map) if e.kind in ("paragraph", "table")]
    first = next((i for i, e in enumerate(top) if e.heading_level is not None), None)
    if first is None:
        return []

    def texts(block: MapElement) -> list[str]:
        found = [block] if block.kind == "paragraph" else _texts_under(doc_map, [block])
        return [t for p in found if (t := p.text.strip())]

    def untouched(block: MapElement) -> bool:
        return all(t in base_texts and not is_marker(t) for t in texts(block))

    def sample(block: MapElement) -> bool:
        found = texts(block)
        if block.kind == "paragraph":
            return bool(found) and found[0] in template_texts and not is_toc(block)
        return all(t in template_texts for t in found)

    marked: dict[int, str] = {}
    i = first
    while i < len(top):
        block, level = top[i], top[i].heading_level
        if level is None or block.text.strip() not in template_texts:
            i += 1
            continue
        end = next(
            (
                j
                for j in range(i + 1, len(top))
                if (other := top[j].heading_level) is not None and other <= level
            ),
            len(top),
        )
        if all(untouched(b) for b in top[i:end]):
            marked.update({j: "" for j in range(i + 1, end)})
            marked[i] = f"{_quote(block.text, 60)} (heading and content)"
            i = end
        else:
            i += 1
    for j in range(first, len(top)):
        block = top[j]
        if j not in marked and block.heading_level is None and sample(block):
            text = next(iter(texts(block)), "")
            marked[j] = _quote(text, 60) if text else "an empty frame"
    # Empty paragraphs between two removed blocks go with them.
    for j in range(first, len(top)):
        if j in marked or texts(top[j]) or top[j].kind != "paragraph":
            continue
        before = next((k for k in range(j - 1, first - 1, -1) if texts(top[k])), None)
        after = next((k for k in range(j + 1, len(top)) if texts(top[k])), None)
        if before in marked and after in marked:
            marked[j] = ""
    runs: list[list[int]] = []
    for j in sorted(marked):
        if runs and runs[-1][-1] == j - 1:
            runs[-1].append(j)
        else:
            runs.append([j])
    return [
        UnusedRange(
            top[run[0]].address,
            top[run[-1]].address,
            "; ".join(marked[j] for j in run if marked[j]),
        )
        for run in runs
    ]


def _empty_headings(
    doc_map: DocMap,
    group: Sequence[MapElement],
    anchored: Mapping[str, Sequence[MapElement]],
) -> list[Leftover]:
    """Headings with nothing written under them before the next heading of
    the same or a higher level (a heading followed by its sub-headings is a
    parent, not empty)."""
    out: list[Leftover] = []
    for i, heading in enumerate(group):
        level = heading.heading_level
        if level is None:
            continue
        rest = group[i + 1 :]
        stop = next(
            (j for j, e in enumerate(rest) if e.heading_level is not None), len(rest)
        )
        if stop < len(rest) and (rest[stop].heading_level or 0) > level:
            continue
        under = list(rest[:stop])
        content = _texts_under(doc_map, under) + [
            p for block in under for p in anchored.get(block.address, [])
        ]
        if any(e.kind == "table" for e in under) or any(
            p.text.strip() or "image" in p.flags for p in content
        ):
            continue
        out.append(Leftover(heading.address, heading.text.strip(), "empty", ""))
    return out


def render_part(
    doc_map: DocMap,
    part_id: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    full: frozenset[str] = frozenset(),
) -> str:
    """The text map of one part (see :func:`parts`); the ``full`` texts are
    not cut. Raises ``KeyError`` for an unknown part id."""
    renderer = _Renderer(doc_map, full)
    if part_id == "hf":
        stories = [e for e in doc_map.elements if e.kind in ("header", "footer")]
        if not stories:
            raise KeyError(part_id)
        return "\n".join(line for s in stories for line in renderer.story(s))
    groups = dict(numbered_groups(doc_map, chunk_size))
    if part_id not in groups:
        raise KeyError(part_id)
    return "\n".join(renderer.blocks(groups[part_id], 0))
