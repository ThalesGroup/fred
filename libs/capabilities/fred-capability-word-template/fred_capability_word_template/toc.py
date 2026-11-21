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

"""The table of contents kept in step with the headings: after each batch its
lines are rebuilt from the headings (number, text, order), in the template's
own line styles. Only Word computes page numbers: the downloaded file asks
it to update its fields on opening.
"""

from __future__ import annotations

import copy
import io
import re
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from fred_capability_word_template.docmap import build_map_from_document

_TOC_RE = re.compile(r"^\s*TOC\b")
_LEVELS_RE = re.compile(r'\\o\s+"(\d)-(\d)"')
_PAGEREF_RE = re.compile(r"PAGEREF\s+\S+")
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_ROMAN = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
    (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)  # fmt: skip


def refresh_table_of_contents(document: DocxDocument) -> None:
    """Rebuild the lines of the document's TOC field from its headings. A
    document without one, or whose lines carry no heading link, is left as
    it is."""
    found = _toc_lines(document)
    if found is None:
        _drop_stale_lines(document)
        return
    lines, levels = found
    samples = _samples(lines, document)
    if not samples:
        return
    pages = {_anchor(line): _page(line) for line in lines}
    numbers = _Numbering(document)
    doc_map = build_map_from_document(document)
    in_toc = {id(line) for line in lines}
    built: list[Any] = []
    page = ""
    for element in doc_map.elements:
        level = element.heading_level
        if (
            level is None
            or element.story != "body"
            or element.in_textbox
            or id(element.node) in in_toc
        ):
            continue
        number = numbers.next(element.node, level)
        if not levels[0] <= level <= levels[1] or not element.text.strip():
            continue
        # The nearest level that has a line in the template (lxml elements
        # are never tested for truth: an empty one is falsy).
        style_level = (
            level
            if level in samples
            else max((k for k in samples if k <= level), default=min(samples))
        )
        sample = samples[style_level]
        name = _bookmark(element.node, document, pages)
        page = pages.get(name) or page
        built.append(_line(sample, name, number, element.text.strip(), page))
    # Unchanged headings leave the template's own lines untouched.
    if [_line_text(line) for line in built] != [_line_text(line) for line in lines]:
        _replace(lines, built)


def with_update_fields(docx_bytes: bytes) -> bytes:
    """The document set to have Word update its fields (the table of
    contents' page numbers) when it opens it."""
    document = Document(io.BytesIO(docx_bytes))
    settings = document.settings.element
    if settings.find(qn("w:updateFields")) is None:
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        settings.insert(0, update)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _drop_stale_lines(document: DocxDocument) -> None:
    """Without a TOC field (a contents typed or pasted as text), a line made
    only of links to a heading bookmark that is gone goes with the heading;
    a sentence holding such a link stays."""
    body = document.element.body
    names = {s.get(qn("w:name")) for s in body.iter(qn("w:bookmarkStart"))}
    for paragraph in list(body.iter(qn("w:p"))):
        links = list(paragraph.iter(qn("w:hyperlink")))
        anchors = {link.get(qn("w:anchor")) or "" for link in links}
        if not anchors or not all(a.startswith("_Toc") for a in anchors):
            continue
        outside = "".join(
            t.text or ""
            for t in paragraph.iter(qn("w:t"))
            if not any(a.tag == qn("w:hyperlink") for a in t.iterancestors())
        )
        if anchors - names and not outside.strip().strip("0123456789"):
            parent = paragraph.getparent()
            if parent is not None:
                parent.remove(paragraph)


def _toc_lines(document: DocxDocument) -> tuple[list[Any], tuple[int, int]] | None:
    """The paragraphs of the TOC field holding a heading link, and the
    heading levels its switch lists."""
    paragraphs = list(document.element.body.iter(qn("w:p")))
    start = next(
        (
            i
            for i, p in enumerate(paragraphs)
            if any(_TOC_RE.match(t.text or "") for t in p.iter(qn("w:instrText")))
        ),
        None,
    )
    if start is None:
        return None
    instruction = "".join(
        t.text or "" for t in paragraphs[start].iter(qn("w:instrText"))
    )
    match = _LEVELS_RE.search(instruction)
    levels = (int(match.group(1)), int(match.group(2))) if match else (1, 3)
    depth = 0
    lines: list[Any] = []
    for paragraph in paragraphs[start:]:
        if _anchor(paragraph):
            lines.append(paragraph)
        for char in paragraph.iter(qn("w:fldChar")):
            kind = char.get(qn("w:fldCharType"))
            depth += 1 if kind == "begin" else -1 if kind == "end" else 0
        if depth <= 0:
            break
    return (lines, levels) if lines else None


def _line_text(paragraph) -> str:
    """What a line shows: its link's text (number, title, page)."""
    link = paragraph.find(f".//{qn('w:hyperlink')}")
    nodes = link.iter(qn("w:t")) if link is not None else iter(())
    return "".join(t.text or "" for t in nodes)


def _anchor(paragraph) -> str:
    link = paragraph.find(f".//{qn('w:hyperlink')}")
    anchor = link.get(qn("w:anchor")) if link is not None else None
    return anchor or ""


def _page(paragraph) -> str:
    """The page number shown by a line: the text after its PAGEREF field's
    separator."""
    link = paragraph.find(f".//{qn('w:hyperlink')}")
    if link is None:
        return ""
    shown, inside = [], False
    for node in link.iter(qn("w:fldChar"), qn("w:t")):
        if node.tag == qn("w:fldChar"):
            kind = node.get(qn("w:fldCharType"))
            inside = kind == "separate" or (inside and kind != "end")
        elif inside:
            shown.append(node.text or "")
    return "".join(shown).strip()


def _samples(lines: list[Any], document: DocxDocument) -> dict[int, Any]:
    """One line per TOC level, the first of each "toc N" style."""
    samples: dict[int, Any] = {}
    for line in lines:
        style_el = line.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
        style = (
            document.styles.element.get_by_id(style_el.get(qn("w:val")))
            if style_el is not None
            else None
        )
        match = re.match(
            r"toc\s*(\d)", (style.name_val or "") if style is not None else "", re.I
        )
        if match:
            samples.setdefault(int(match.group(1)), line)
    return samples


def _bookmark(heading, document: DocxDocument, linked: dict[str, str]) -> str:
    """The heading's "_Toc" bookmark - the one a line already links to,
    else its first - added when missing (numbered after the document's
    highest, so a replay adds the same ones)."""
    names = [
        start.get(qn("w:name")) or ""
        for start in heading.iter(qn("w:bookmarkStart"))
        if (start.get(qn("w:name")) or "").startswith("_Toc")
    ]
    if names:
        return next((n for n in names if n in linked), names[0])
    body = document.element.body
    starts = list(body.iter(qn("w:bookmarkStart")))
    ids = [
        int(s.get(qn("w:id"))) for s in starts if (s.get(qn("w:id")) or "").isdigit()
    ]
    tocs = [
        int(name[4:])
        for s in starts
        if (name := s.get(qn("w:name")) or "").startswith("_Toc") and name[4:].isdigit()
    ]
    bookmark_id = str(max(ids, default=0) + 1)
    name = f"_Toc{max(tocs, default=100000000) + 1}"
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bookmark_id)
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bookmark_id)
    properties = heading.find(qn("w:pPr"))
    if properties is not None:
        properties.addnext(start)
    else:
        heading.insert(0, start)
    heading.append(end)
    return name


def _line(sample, anchor: str, number: str, title: str, page: str):
    """A TOC line in ``sample``'s look: its number, title and page runs."""
    line = copy.deepcopy(sample)
    for element in line.iter():
        for attribute in (f"{{{_W14}}}paraId", f"{{{_W14}}}textId"):
            element.attrib.pop(attribute, None)
    link = line.find(f".//{qn('w:hyperlink')}")
    # The TOC field's own begin/end runs stay with the first/last lines only.
    for child in list(line):
        if child.tag == qn("w:r") and child.find(qn("w:fldChar")) is not None:
            line.remove(child)
        elif child.tag == qn("w:r") and child.find(qn("w:instrText")) is not None:
            line.remove(child)
    if link is None:
        return line
    link.set(qn("w:anchor"), anchor)
    runs = list(link.iter(qn("w:r")))
    field = next(
        (i for i, r in enumerate(runs) if r.find(qn("w:fldChar")) is not None),
        len(runs),
    )
    tabs = [i for i, r in enumerate(runs[:field]) if r.find(qn("w:tab")) is not None]
    title_runs = (
        runs[tabs[0] + 1 : tabs[1]]
        if len(tabs) > 1
        else runs[: tabs[0] if tabs else field]
    )
    number_runs = runs[: tabs[0]] if len(tabs) > 1 else []
    if number_runs and number:
        _set_runs(number_runs, number)
    elif number_runs:
        for run in [*number_runs, runs[tabs[0]]]:
            run.getparent().remove(run)
    elif number:
        title = f"{number} {title}"
    _set_runs(title_runs, title)
    for instr in link.iter(qn("w:instrText")):
        instr.text = _PAGEREF_RE.sub(f"PAGEREF {anchor}", instr.text or "")
    shown = [r for r in runs[field:] if r.find(qn("w:t")) is not None]
    if shown:
        _set_runs(shown, page)
    return line


def _set_runs(runs: list[Any], text: str) -> None:
    texts = [t for run in runs for t in run.iter(qn("w:t"))]
    if not texts:
        return
    texts[0].text = text
    texts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for extra in texts[1:]:
        extra.text = ""


def _replace(lines: list[Any], built: list[Any]) -> None:
    """Put the rebuilt lines in place of the old ones, the TOC field's begin
    (in its first line) and end (in its last line, if there) kept."""
    if not built:
        return

    def field_runs(line, kinds: tuple[str, ...]) -> list[Any]:
        return [
            child
            for child in line
            if child.tag == qn("w:r")
            and (
                child.find(qn("w:instrText")) is not None
                or (char := child.find(qn("w:fldChar"))) is not None
                and char.get(qn("w:fldCharType")) in kinds
            )
        ]

    head = field_runs(lines[0], ("begin", "separate"))
    tail = [
        r for r in field_runs(lines[-1], ("end",)) if r.find(qn("w:instrText")) is None
    ]
    properties = built[0].find(qn("w:pPr"))
    for run in reversed(head):
        if properties is not None:
            properties.addnext(run)
        else:
            built[0].insert(0, run)
    for run in tail:
        built[-1].append(run)
    for line in built:
        lines[0].addprevious(line)
    for line in lines:
        parent = line.getparent()
        if parent is not None:
            parent.remove(line)


class _Numbering:
    """Heading numbers as Word shows them, from the template's numbering
    definitions (counters per list, reset below the level that moves)."""

    def __init__(self, document: DocxDocument) -> None:
        self.document = document
        self.levels: dict[str, dict[int, tuple[str, str, int]]] = {}
        self.abstract_of: dict[str, str] = {}
        self.counters: dict[str, list[int]] = {}
        try:
            numbering = document.part.numbering_part.element
        except (KeyError, NotImplementedError, AttributeError):
            return
        for abstract in numbering.findall(qn("w:abstractNum")):
            key = abstract.get(qn("w:abstractNumId")) or ""
            defs: dict[int, tuple[str, str, int]] = {}
            for lvl in abstract.findall(qn("w:lvl")):
                fmt = lvl.find(qn("w:numFmt"))
                text = lvl.find(qn("w:lvlText"))
                start = lvl.find(qn("w:start"))
                defs[int(lvl.get(qn("w:ilvl")) or 0)] = (
                    fmt.get(qn("w:val")) if fmt is not None else "decimal",
                    text.get(qn("w:val")) if text is not None else "",
                    int(start.get(qn("w:val"))) if start is not None else 1,
                )
            self.levels[key] = defs
        for num in numbering.findall(qn("w:num")):
            abstract_id = num.find(qn("w:abstractNumId"))
            if abstract_id is not None:
                self.abstract_of[num.get(qn("w:numId")) or ""] = (
                    abstract_id.get(qn("w:val")) or ""
                )

    def next(self, paragraph, heading_level: int) -> str:
        """The number Word gives ``paragraph``, counting it."""
        found = self._num_pr(paragraph)
        if found is None:
            return ""
        num_id, ilvl = found
        if ilvl is None:
            ilvl = heading_level - 1
        abstract = self.abstract_of.get(num_id)
        defs = self.levels.get(abstract or "")
        if not defs or ilvl not in defs:
            return ""
        counters = self.counters.setdefault(
            abstract or "", [defs.get(i, ("", "", 1))[2] - 1 for i in range(9)]
        )
        counters[ilvl] += 1
        for deeper in range(ilvl + 1, 9):
            counters[deeper] = defs.get(deeper, ("", "", 1))[2] - 1
        fmt, text, _start = defs[ilvl]
        return re.sub(
            r"%(\d)",
            lambda m: _format(
                counters[int(m.group(1)) - 1], defs.get(int(m.group(1)) - 1, (fmt,))[0]
            ),
            text,
        )

    def _num_pr(self, paragraph) -> tuple[str, int | None] | None:
        """The paragraph's numId and level, its own or its style's."""
        properties = paragraph.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
        style = self._style(paragraph.find(f"{qn('w:pPr')}/{qn('w:pStyle')}"))
        for _ in range(10):
            num_id = properties.find(qn("w:numId")) if properties is not None else None
            if num_id is not None:
                if num_id.get(qn("w:val")) in (None, "0"):
                    return None
                ilvl = properties.find(qn("w:ilvl")) if properties is not None else None
                level = int(ilvl.get(qn("w:val")) or 0) if ilvl is not None else None
                return num_id.get(qn("w:val")) or "", level
            if style is None:
                return None
            properties = style.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
            style = self._style(style.find(qn("w:basedOn")))
        return None

    def _style(self, reference) -> Any:
        if reference is None:
            return None
        return self.document.styles.element.get_by_id(reference.get(qn("w:val")))


def _format(value: int, fmt: str) -> str:
    if fmt in ("lowerLetter", "upperLetter"):
        letters = ""
        n = value
        while n > 0:
            n, rest = divmod(n - 1, 26)
            letters = chr(ord("a") + rest) + letters
        return letters.upper() if fmt == "upperLetter" else letters
    if fmt in ("lowerRoman", "upperRoman"):
        roman, n = "", value
        for amount, symbol in _ROMAN:
            while n >= amount:
                roman, n = roman + symbol, n - amount
        return roman.upper() if fmt == "upperRoman" else roman
    if fmt in ("none", "bullet"):
        return ""
    if fmt == "decimalZero":
        return f"{value:02d}"
    return str(value)
