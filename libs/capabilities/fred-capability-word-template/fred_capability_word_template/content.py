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

"""The "Rédaction" view: the current document as parts of blocks
(chapter, table, block_group, paragraph, fields). Every editable place carries
its address and the operation to send, so the frontend never builds one.
``paragraphs_markdown`` writes the Markdown subset ``write`` accepts, so
Markdown -> ``write`` -> Markdown gives the same text back.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from pydantic import BaseModel, ConfigDict, Field

from fred_capability_word_template.analysis import TemplateAnalysis, address_ranges
from fred_capability_word_template.docmap import (
    DEFAULT_CHUNK_SIZE,
    DocMap,
    MapElement,
    build_map_from_document,
    chapter_of,
    numbered_groups,
    own_text_units,
    own_textboxes,
    placed_image,
    row_cells,
    top_block,
)
from fred_capability_word_template.docmap import (
    parts as map_parts,
)
from fred_capability_word_template.operations import (
    list_kind_of,
    numbering_root,
    style_num_ids,
    text_units,
)

# --- the view (the route's response model) -------------------------------------


class _View(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ContentOperation(_View):
    """One operation of a batch, exactly as ``edit_document`` takes it (see
    its docstring for the semantics). The view hands out ready-made
    operations (``duplicate``, ``remove``, a text segment's ``edit``); the
    frontend completes ``text`` / ``markdown`` / ``replace`` where needed and
    posts them as they are."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    op: str = Field(
        description="set_text | replace_text | write | insert_after | repeat | remove"
    )
    address: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    count: int | None = None
    text: str | None = None
    find: str | None = None
    replace: str | None = None
    markdown: str | None = None


EditMode = Literal["set_text", "replace_text", "write"]


class TextPiece(_View):
    """A piece of a ``replace_text`` place: ``field`` pieces (page number,
    date, a page break...) are shown but never edited."""

    text: str
    field: bool = False


class Place(_View):
    """An editable place.

    - ``edit = "set_text"``: send ``{"op": "set_text", "address", "text"}``;
      ``text`` there is inline Markdown - start from ``markdown`` (the
      current value, escaped) and escape a typed literal ``\\ * _ ` `` with
      a backslash. ``\\n`` is a line break.
    - ``edit = "replace_text"``: the place holds a field; send
      ``{"op": "replace_text", "address", "find", "replace"}`` with ``find``
      copied from a non-field piece of ``pieces`` (plain text, no escaping).
    - ``edit = "write"`` (a multi-paragraph cell): send
      ``{"op": "write", "from": address, "markdown"}``, starting from
      ``markdown``.
    - ``edit`` absent: shown, not editable.
    """

    address: str
    text: str = ""
    edit: EditMode | None = None
    markdown: str | None = None
    pieces: list[TextPiece] | None = None


class ParagraphBlock(Place):
    kind: Literal["paragraph"] = "paragraph"
    style: str | None = None


class FieldsBlock(_View):
    """The places of a header, a footer or a text box (``address`` is the
    story's, e.g. ``H1``, ``F1``, ``X1``)."""

    kind: Literal["fields"] = "fields"
    address: str
    label: str
    fields: list[Place] = []


class CellView(Place):
    col: int = Field(description="1-based first grid column")
    col_span: int = 1
    row_span: int = 1


class RowView(_View):
    address: str
    cells: list[CellView] = []
    duplicate: ContentOperation | None = None
    remove: ContentOperation | None = None


class RowGroup(_View):
    """Consecutive rows the template analysis marks as one repeatable block."""

    from_: str = Field(alias="from")
    to: str
    label: str
    duplicate: ContentOperation
    remove: ContentOperation


class TableBlock(_View):
    kind: Literal["table"] = "table"
    address: str
    n_rows: int
    n_cols: int
    style: str | None = None
    repeat_label: str | None = Field(
        default=None, description="what one copy stands for, when repeatable"
    )
    rows: list[RowView] = []
    row_groups: list[RowGroup] = []
    duplicable: bool = True
    duplicate: ContentOperation | None = None
    removable: bool = True
    remove: ContentOperation | None = None


class TextSegment(_View):
    """Consecutive plain paragraphs and lists of a chapter body, as Markdown.
    Rewritten by sending ``edit`` with ``markdown`` set: a ``write`` over
    ``from``/``to``, or - for an empty chapter body - an ``insert_after``
    the heading."""

    kind: Literal["text"] = "text"
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    markdown: str = ""
    edit: ContentOperation


ChapterSegment = Annotated[
    TextSegment | TableBlock | ParagraphBlock | FieldsBlock,
    Field(discriminator="kind"),
]


class Heading(Place):
    level: int


class ChapterBlock(_View):
    """A heading and its body. ``from``/``to`` spans the whole chapter,
    sub-chapters included (what ``remove`` removes)."""

    kind: Literal["chapter"] = "chapter"
    level: int
    heading: Heading
    body: list[ChapterSegment] = []
    from_: str = Field(alias="from")
    to: str
    removable: bool = True
    remove: ContentOperation


GroupMember = Annotated[
    TableBlock | ParagraphBlock | FieldsBlock, Field(discriminator="kind")
]


class BlockGroup(_View):
    kind: Literal["block_group"] = "block_group"
    from_: str = Field(alias="from")
    to: str
    label: str
    blocks: list[GroupMember] = []
    duplicable: bool = True
    duplicate: ContentOperation
    removable: bool = True
    remove: ContentOperation


PartBlock = Annotated[
    ChapterBlock | TableBlock | BlockGroup | ParagraphBlock | FieldsBlock,
    Field(discriminator="kind"),
]


class ContentPart(_View):
    id: str
    title: str
    blocks: list[PartBlock] = []


# --- repeatable blocks from the analysis ------------------------------------------


@dataclass(frozen=True)
class RepeatableGroup:
    """A repeatable block of the analysis: addresses of the BLANK base."""

    first: str
    last: str
    label: str


def repeatable_groups(analysis: TemplateAnalysis) -> list[RepeatableGroup]:
    return [
        RepeatableGroup(first, last, block.one_per.strip() or "un élément")
        for block in analysis.repeatable_blocks
        for first, last in address_ranges(block.addresses)
    ]


# --- docx -> Markdown ------------------------------------------------------------

_LOST_IN_MARKDOWN = (
    qn("w:hyperlink"),
    qn("w:footnoteReference"),
    qn("w:endnoteReference"),
    qn("w:sdt"),
)


def _plain_style(element: MapElement) -> str | None:
    style = element.node.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return style.get(qn("w:val")) if style is not None else None


_SPECIAL_RE = re.compile(r"([\\`*_])")
_ORDERED_START_RE = re.compile(r"^(\d+)([.)])(?=\s)")
_BLOCK_START_RE = re.compile(r"^(?:#{1,6}|[-+])(?=\s)|^!\[")
_STYLE_LEVEL_RE = re.compile(r"^list\b.*?(\d)$", re.IGNORECASE)
_CODE_FONT = "Courier New"


def _on(element) -> bool:
    if element is None:
        return False
    return element.get(qn("w:val"), "true").lower() not in ("0", "false", "off")


def _run_format(run) -> tuple[bool, bool, bool]:
    """(bold, italic, code) set directly on the run - what ``write`` and
    ``set_text`` produce from Markdown; a style's own emphasis is not
    Markdown."""
    properties = run.find(qn("w:rPr")) if run is not None else None
    if properties is None:
        return False, False, False
    fonts = properties.find(qn("w:rFonts"))
    code = fonts is not None and fonts.get(qn("w:ascii")) == _CODE_FONT
    bold = _on(properties.find(qn("w:b")))
    # Bold wins: the inline parser reads ***x*** as bold.
    return bold, (not bold) and _on(properties.find(qn("w:i"))), code


def _escape(text: str) -> str:
    return _SPECIAL_RE.sub(r"\\\1", text)


def _split_space(text: str) -> tuple[str, str, str]:
    core = text.strip()
    if not core:
        return text, "", ""
    start = text.index(core)
    return text[:start], core, text[start + len(core) :]


def inline_markdown(paragraph, *, line_break: str = "\n") -> str:
    """One paragraph's text as inline Markdown (``set_text`` reads it back
    to the same runs). Tabs stay tabs; a line break becomes ``line_break``."""
    spans: list[tuple[str, tuple[bool, bool, bool]]] = []
    for unit in own_text_units(paragraph):
        if unit.tag == qn("w:t"):
            text = unit.text or ""
        elif unit.tag == qn("w:tab"):
            text = "\t"
        elif unit.get(qn("w:type")) in ("page", "column"):
            continue
        else:
            text = line_break
        fmt = _run_format(unit.getparent())
        if spans and spans[-1][1] == fmt:
            spans[-1] = (spans[-1][0] + text, fmt)
        else:
            spans.append((text, fmt))
    out: list[str] = []
    for text, (bold, italic, code) in spans:
        lead, core, trail = _split_space(text)
        if not core:
            out.append(text)
        elif code and "`" not in core:
            out.append(f"{lead}`{core}`{trail}")
        elif bold or italic:
            mark = "**" if bold else "*"
            out.append(f"{lead}{mark}{_escape(core)}{mark}{trail}")
        else:
            out.append(_escape(text))
    return "".join(out)


def _protect_line_start(line: str) -> str:
    """Escape a paragraph start the renderer would read as a heading, a list
    item or a picture."""
    ordered = _ORDERED_START_RE.match(line)
    if ordered:
        return f"{ordered.group(1)}\\{line[ordered.end(1) :]}"
    if _BLOCK_START_RE.match(line):
        return f"\\{line}"
    return line


class _Lists:
    """Bullet / numbered list detection, as the template draws lists."""

    def __init__(self, document: DocxDocument) -> None:
        self._numbering = numbering_root(document)
        self._style_nums = (
            style_num_ids(document) if self._numbering is not None else {}
        )

    def info(self, element: MapElement) -> tuple[str, int] | None:
        """("bullet" | "number", level 1-3), or None for a plain paragraph."""
        if self._numbering is None or element.heading_level is not None:
            return None
        properties = element.node.find(qn("w:pPr"))
        if properties is None:
            return None
        style = properties.find(qn("w:pStyle"))
        style_id = style.get(qn("w:val")) if style is not None else None
        num = properties.find(f"{qn('w:numPr')}/{qn('w:numId')}")
        direct = num.get(qn("w:val")) if num is not None else None
        effective = direct or (self._style_nums.get(style_id) if style_id else None)
        if not effective:
            return None
        kind = list_kind_of(self._numbering, effective)
        if kind is None:
            return None
        ilvl = properties.find(f"{qn('w:numPr')}/{qn('w:ilvl')}")
        if ilvl is not None and (ilvl.get(qn("w:val")) or "").isdigit():
            level = int(ilvl.get(qn("w:val")) or 0) + 1
        else:
            match = _STYLE_LEVEL_RE.match(element.style or "")
            level = int(match.group(1)) if match else 1
        return kind, max(1, min(level, 3))


def is_figure_caption(paragraph) -> bool:
    """The "Figure N : caption" paragraph the engine writes under a picture."""
    return any(
        "SEQ Figure" in (field.get(qn("w:instr")) or "")
        for field in paragraph.iter(qn("w:fldSimple"))
    )


def image_markdown(image_id: str, caption: str) -> str:
    """The line ``write`` reads back as that picture (a caption cannot hold
    brackets there)."""
    clean = " ".join(caption.replace("[", "(").replace("]", ")").split())
    return f"![{clean}](img:{image_id})"


def paragraphs_markdown(paragraphs: Sequence[MapElement], lists: _Lists) -> str:
    """Paragraphs as the Markdown ``write`` accepts: plain paragraphs
    separated by a blank line, list items on consecutive lines (two spaces
    per level), a picture the engine placed as ``![caption](img:<id>)``
    (its "Figure N" caption paragraph folded in). Empty paragraphs are left
    out (``write`` makes none)."""
    # (list kind of the item's top-level list, or None for a paragraph; line)
    chunks: list[tuple[str | None, str]] = []
    counters: dict[int, tuple[str, int]] = {}
    top_kind = "bullet"
    after_image = False
    for element in paragraphs:
        image = placed_image(element.node)
        if image is not None:
            counters.clear()
            chunks.append((None, image_markdown(*image)))
            after_image = True
            continue
        if after_image and is_figure_caption(element.node):
            after_image = False
            continue
        after_image = False
        text = inline_markdown(element.node, line_break=" ").strip()
        info = lists.info(element)
        if info is None:
            counters.clear()
            if text:
                chunks.append((None, _protect_line_start(text)))
            continue
        if not text:
            continue
        kind, level = info
        if level == 1 or not counters:
            top_kind = kind
        for deeper in [lvl for lvl in counters if lvl > level]:
            del counters[deeper]
        previous = counters.get(level)
        number = previous[1] + 1 if previous and previous[0] == kind else 1
        counters[level] = (kind, number)
        marker = f"{number}." if kind == "number" else "-"
        chunks.append((top_kind, f"{'  ' * (level - 1)}{marker} {text}"))
    out: list[str] = []
    for index, (list_kind, line) in enumerate(chunks):
        if index:
            # One list: items on consecutive lines; anything else (a
            # paragraph, another kind of list) after a blank line.
            same_list = list_kind is not None and list_kind == chunks[index - 1][0]
            out.append("\n" if same_list else "\n\n")
        out.append(line)
    return "".join(out)


# --- the view builder ------------------------------------------------------------


def _op(op: str, **fields: Any) -> ContentOperation:
    return ContentOperation.model_validate({"op": op, **fields})


def _range_op(op: str, first: str, last: str, **fields: Any) -> ContentOperation:
    if last != first:
        fields["to"] = last
    return _op(op, **{"from": first, **fields})


def _pieces(paragraph) -> tuple[str, list[TextPiece], bool]:
    """(visible text, pieces, has a field)."""
    pieces: list[TextPiece] = []
    opaque = False
    for unit in text_units(paragraph):
        is_field = unit.kind == "field"
        opaque = opaque or is_field
        if pieces and pieces[-1].field == is_field:
            pieces[-1].text += unit.shown
        else:
            pieces.append(TextPiece(text=unit.shown, field=is_field))
    return "".join(p.text for p in pieces), pieces, opaque


class _Builder:
    def __init__(self, document: DocxDocument, doc_map: DocMap) -> None:
        self.map = doc_map
        self.lists = _Lists(document)
        self.children: dict[str, list[MapElement]] = {}
        for element in doc_map.elements:
            if element.kind != "textbox":
                self.children.setdefault(element.container, []).append(element)
        self.top = [e for e in doc_map.elements if e.container == "" and e.is_block]
        self.top_index = {e.address: i for i, e in enumerate(self.top)}
        # Body text boxes, under the top-level block they are anchored in.
        self.textboxes: dict[str, list[MapElement]] = {}
        for element in doc_map.elements:
            if element.kind == "textbox" and element.story == "body":
                anchor = self._top_block(element)
                if anchor is not None:
                    self.textboxes.setdefault(anchor, []).append(element)

    def _top_block(self, element: MapElement | None) -> str | None:
        return top_block(self.map, element)

    # -- places ----------------------------------------------------------------

    def place(self, paragraph: MapElement, address: str | None = None) -> Place:
        text, pieces, opaque = _pieces(paragraph.node)
        target = address or paragraph.address
        # set_text would drop a link, a footnote or a content control.
        if opaque or any(True for _ in paragraph.node.iter(*_LOST_IN_MARKDOWN)):
            return Place(address=target, text=text, edit="replace_text", pieces=pieces)
        if own_textboxes(paragraph.node):
            # set_text would drop the text box's run: its text is edited in
            # its own fields block.
            return Place(address=target, text=text)
        return Place(
            address=target,
            text=text,
            edit="set_text",
            markdown=inline_markdown(paragraph.node),
        )

    def _rich(self, element: MapElement) -> bool:
        """A body paragraph Markdown carries without loss: no link, footnote
        or content control, which a rewrite would drop."""
        if element.kind != "paragraph" or element.heading_level is not None:
            return False
        if "image" in element.flags or own_textboxes(element.node):
            return False
        if any(True for _ in element.node.iter(*_LOST_IN_MARKDOWN)):
            return False
        return not any(u.kind == "field" for u in text_units(element.node))

    def _is_plain(self, element: MapElement) -> bool:
        """A text paragraph (list items, pictures and captions keep their own
        look)."""
        return (
            self.lists.info(element) is None
            and "image" not in element.flags
            and not is_figure_caption(element.node)
        )

    @staticmethod
    def _placed_image(element: MapElement) -> bool:
        """A body paragraph holding only a picture the engine placed: it
        reads back as ``![caption](img:<id>)``."""
        return (
            element.kind == "paragraph"
            and element.heading_level is None
            and placed_image(element.node) is not None
        )

    def paragraph_block(self, element: MapElement) -> ParagraphBlock:
        place = self.place(element)
        return ParagraphBlock(**place.model_dump(), style=element.style)

    def fields_block(self, story: MapElement) -> FieldsBlock:
        """Every paragraph under ``story`` (a header's tables and text boxes
        included), the empty ones only inside a cell (a value to fill)."""
        prefix = f"{story.address}."
        fields: list[Place] = []
        for element in self.map.elements:
            if element.kind != "paragraph" or not element.address.startswith(prefix):
                continue
            in_cell = ".C" in element.address
            if not element.text.strip() and not in_cell:
                continue
            fields.append(self.place(element))
        label = story.label or story.address
        if story.kind == "textbox":
            label = "text box"
        return FieldsBlock(address=story.address, label=label, fields=fields)

    def _textbox_blocks(self, top_address: str) -> list[FieldsBlock]:
        return [self.fields_block(box) for box in self.textboxes.get(top_address, [])]

    # -- tables ----------------------------------------------------------------

    def cell(self, cell: MapElement) -> CellView:
        inner = self.children.get(cell.address, [])
        column = int(cell.address.rsplit(".C", 1)[-1])
        common = {
            "address": cell.address,
            "text": cell.text,
            "col": column,
            "col_span": cell.col_span,
            "row_span": cell.row_span,
        }
        paragraphs = [e for e in inner if e.kind == "paragraph"]
        blocked = len(paragraphs) != len(inner) or any(
            own_textboxes(p.node) for p in paragraphs
        )
        if blocked:
            return CellView(**common)
        if len(paragraphs) <= 1:
            if not paragraphs:
                return CellView(**common, edit="set_text", markdown="")
            place = self.place(paragraphs[0], cell.address)
            return CellView(**{**place.model_dump(), **common})
        if not all(self._rich(p) for p in paragraphs):
            return CellView(**common)
        return CellView(
            **common,
            edit="write",
            markdown=paragraphs_markdown(paragraphs, self.lists),
        )

    def table_block(self, table: MapElement) -> TableBlock:
        rows = [r for r in self.children.get(table.address, []) if r.kind == "row"]
        views: list[RowView] = []
        for row in rows:
            cells = self.children.get(row.address, [])
            whole = len(row_cells(row.node)) == len(cells) and all(
                c.row_span == 1 for c in cells
            )
            views.append(
                RowView(
                    address=row.address,
                    cells=[self.cell(c) for c in cells],
                    duplicate=_op("repeat", **{"from": row.address, "count": 1})
                    if whole
                    else None,
                    remove=_op("remove", **{"from": row.address})
                    if whole and len(rows) > 1
                    else None,
                )
            )
        return TableBlock(
            address=table.address,
            n_rows=table.rows or len(rows),
            n_cols=table.cols or 0,
            style=table.style,
            rows=views,
            duplicate=_op("repeat", **{"from": table.address, "count": 1}),
            remove=_op("remove", **{"from": table.address}),
        )

    # -- chapters --------------------------------------------------------------

    def _member(self, element: MapElement) -> list[Any]:
        block = (
            self.table_block(element)
            if element.kind == "table"
            else self.paragraph_block(element)
        )
        return [block, *self._textbox_blocks(element.address)]

    def chapter(self, start: int) -> tuple[ChapterBlock, int]:
        heading = self.top[start]
        level = heading.heading_level or 1
        end_body = next(
            (
                i
                for i in range(start + 1, len(self.top))
                if self.top[i].heading_level is not None
            ),
            len(self.top),
        )
        end = next(
            (
                i
                for i in range(start + 1, len(self.top))
                if (self.top[i].heading_level or 99) <= level
            ),
            len(self.top),
        )
        body: list[Any] = []
        run: list[MapElement] = []

        def flush() -> None:
            if run:
                body.append(
                    TextSegment.model_validate(
                        {
                            "from": run[0].address,
                            "to": run[-1].address,
                            "markdown": paragraphs_markdown(run, self.lists),
                            "edit": _range_op("write", run[0].address, run[-1].address),
                        }
                    )
                )
                run.clear()

        after_image = False
        for element in self.top[start + 1 : end_body]:
            boxes = self._textbox_blocks(element.address)
            if not boxes and self._placed_image(element):
                run.append(element)
                after_image = True
                continue
            if after_image and is_figure_caption(element.node) and not boxes:
                # The picture's caption: rewritten with it.
                run.append(element)
                after_image = False
                continue
            after_image = False
            if self._rich(element) and not boxes:
                # A write takes its first paragraph's style: another style
                # (a quote, a note) starts its own segment and keeps it.
                if self._is_plain(element) and any(
                    self._is_plain(r) and _plain_style(r) != _plain_style(element)
                    for r in run
                ):
                    flush()
                run.append(element)
                continue
            flush()
            body.extend(self._member(element))
        flush()
        if not body:
            body.append(TextSegment(edit=_op("insert_after", address=heading.address)))
        place = self.place(heading)
        last = self.top[end - 1].address
        block = ChapterBlock.model_validate(
            {
                "level": level,
                "heading": Heading(**place.model_dump(), level=level),
                "body": body,
                "from": heading.address,
                "to": last,
                "remove": _range_op("remove", heading.address, last),
            }
        )
        return block, end_body

    # -- the whole view --------------------------------------------------------

    def _apply_row_groups(
        self, tables: dict[str, TableBlock], groups: Iterable[RepeatableGroup]
    ) -> None:
        for group in groups:
            first, last = self.map.get(group.first), self.map.get(group.last)
            if first is None or last is None:
                continue
            if first.kind == "table" and first is last and first.address in tables:
                tables[first.address].repeat_label = group.label
                continue
            if (
                first.kind == "row"
                and last.kind == "row"
                and first.container == last.container
                and first.position <= last.position
                and first.container in tables
            ):
                tables[first.container].row_groups.append(
                    RowGroup.model_validate(
                        {
                            "from": first.address,
                            "to": last.address,
                            "label": group.label,
                            "duplicate": _range_op(
                                "repeat", first.address, last.address, count=1
                            ),
                            "remove": _range_op("remove", first.address, last.address),
                        }
                    )
                )

    def _block_groups(
        self, groups: Iterable[RepeatableGroup]
    ) -> dict[int, tuple[int, str]]:
        """Top-level index of a group's first block -> (index of its last
        block, label), for groups of 2+ body blocks outside any chapter."""
        heading_at = [i for i, e in enumerate(self.top) if e.heading_level is not None]
        first_heading = heading_at[0] if heading_at else len(self.top)
        out: dict[int, tuple[int, str]] = {}
        for group in groups:
            a = self.top_index.get(group.first)
            b = self.top_index.get(group.last)
            if a is None or b is None or b <= a or b >= first_heading:
                continue
            if any(a <= start <= b for start in out) or any(
                s <= a <= e for s, (e, _l) in out.items()
            ):
                continue
            out[a] = (b, group.label)
        return out

    def build(
        self, groups: Sequence[RepeatableGroup], chunk_size: int
    ) -> list[ContentPart]:
        block_groups = self._block_groups(groups)
        placed: list[tuple[int, Any]] = []
        tables: dict[str, TableBlock] = {}
        i = 0
        while i < len(self.top):
            element = self.top[i]
            if element.heading_level is not None:
                chapter, i_next = self.chapter(i)
                placed.append((i, chapter))
                for segment in chapter.body:
                    if isinstance(segment, TableBlock):
                        tables[segment.address] = segment
                i = i_next
                continue
            if i in block_groups:
                last, label = block_groups[i]
                members: list[Any] = []
                for member in self.top[i : last + 1]:
                    members.extend(self._member(member))
                tables.update(
                    {m.address: m for m in members if isinstance(m, TableBlock)}
                )
                first_address, last_address = element.address, self.top[last].address
                placed.append(
                    (
                        i,
                        BlockGroup.model_validate(
                            {
                                "from": first_address,
                                "to": last_address,
                                "label": label,
                                "blocks": members,
                                "duplicate": _range_op(
                                    "repeat", first_address, last_address, count=1
                                ),
                                "remove": _range_op(
                                    "remove", first_address, last_address
                                ),
                            }
                        ),
                    )
                )
                i = last + 1
                continue
            for block in self._member(element):
                if isinstance(block, TableBlock):
                    tables[block.address] = block
                placed.append((i, block))
            i += 1
        self._apply_row_groups(tables, groups)

        # One part per chapter: the pieces of a long chapter are for the
        # model's reads, the collaborator sees the chapter whole.
        titles = {
            p.part_id: p.title for p in map_parts(self.map, chunk_size=chunk_size)
        }
        out: list[ContentPart] = []
        index_of: dict[str, int] = {}
        part_of: dict[int, int] = {}
        for part_id, group in numbered_groups(self.map, chunk_size):
            chapter = chapter_of(part_id)
            if chapter not in index_of:
                index_of[chapter] = len(out)
                out.append(ContentPart(id=chapter, title=titles[part_id]))
            for element in group:
                part_of[self.top_index[element.address]] = index_of[chapter]
        for start, block in placed:
            if out:
                out[part_of.get(start, len(out) - 1)].blocks.append(block)
        stories = [e for e in self.map.elements if e.kind in ("header", "footer")]
        if stories:
            out.append(
                ContentPart(
                    id="hf",
                    title="headers and footers",
                    blocks=[self.fields_block(s) for s in stories],
                )
            )
        return out


def build_content_parts(
    docx_bytes: bytes,
    *,
    groups: Sequence[RepeatableGroup] = (),
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ContentPart]:
    """The "Rédaction" view of a document (CPU-bound: call it in a thread).
    ``groups`` are the analysis's repeatable blocks; pass them only when
    their addresses still hold (no structural edit since the base)."""
    document = Document(io.BytesIO(docx_bytes))
    doc_map = build_map_from_document(document)
    return _Builder(document, doc_map).build(groups, chunk_size)


__all__ = [
    "BlockGroup",
    "CellView",
    "ChapterBlock",
    "ContentOperation",
    "ContentPart",
    "FieldsBlock",
    "Heading",
    "ParagraphBlock",
    "Place",
    "RepeatableGroup",
    "RowGroup",
    "RowView",
    "TableBlock",
    "TextPiece",
    "TextSegment",
    "build_content_parts",
    "inline_markdown",
    "paragraphs_markdown",
    "repeatable_groups",
]
