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

"""A table's intents (total row, highlighted row and column), drawn from its
style: the style's own total-row formatting, a tint of its accent.
PowerPoint's predefined styles are referenced by GUID and never written in
the file, so the accent each is built on is listed here."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from pptx.dml.fill import FillFormat
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn

from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.plan import PlanTable


@dataclass(frozen=True)
class TableStyle:
    accent: int = 1  # the theme accent the style is built on
    total_row: bool = True  # it formats a last row flagged as a total
    dark: bool = False  # light text over a dark or accent fill


# Per predefined style family, its GUIDs: the plain style, then Accent 1 to 6
# (the list LibreOffice ships to render them).
_FAMILIES: Dict[str, tuple[str, ...]] = {
    "themed1": (
        "2D5ABB26-0587-4C30-8999-92F81FD0307C",  # No Style, No Grid
        "3C2FFA5D-87B4-456A-9821-1D502468CF0F",
        "284E427A-3D55-4303-BF80-6455036E1DE7",
        "69C7853C-536D-4A76-A0AE-DD22124D55A5",
        "775DCB02-9BB8-47FD-8907-85C794F793BA",
        "35758FB7-9AC5-4552-8A53-C91805E547FA",
        "08FB837D-C827-4EFA-A057-4D05807E0F7C",
    ),
    "themed2": (
        "5940675A-B579-460E-94D1-54222C63F5DA",  # No Style, Table Grid
        "D113A9D2-9D6B-4929-AA2D-F23B5EE8CBE7",
        "18603FDC-E32A-4AB5-989C-0864C3EAD2B8",
        "306799F8-075E-4A3A-A7F6-7FBC6576F1A4",
        "E269D01E-BC32-4049-B463-5C60D7B0CCD2",
        "327F97BB-C833-4FB7-BDE5-3F7075034690",
        "638B1855-1B75-4FBE-930C-398BA8C253C6",
    ),
    "light1": (
        "9D7B26C5-4107-4FEC-AEDC-1716B250A1EF",
        "3B4B98B0-60AC-42C2-AFA5-B58CD77FA1E5",
        "0E3FDE45-AF77-4B5C-9715-49D594BDF05E",
        "C083E6E3-FA7D-4D7B-A595-EF9225AFEA82",
        "D27102A9-8310-4765-A935-A1911B00CA55",
        "5FD0F851-EC5A-4D38-B0AD-8093EC10F338",
        "68D230F3-CF80-4859-8CE7-A43EE81993B5",
    ),
    "light2": (
        "7E9639D4-E3E2-4D34-9284-5A2195B3D0D7",
        "69012ECD-51FC-41F1-AA8D-1B2483CD663E",
        "72833802-FEF1-4C79-8D5D-14CF1EAF98D9",
        "F2DE63D5-997A-4646-A377-4702673A728D",
        "17292A2E-F333-43FB-9621-5CBBE7FDCDCB",
        "5A111915-BE36-4E01-A7E5-04B1672EAD32",
        "912C8C85-51F0-491E-9774-3900AFEF0FD7",
    ),
    "light3": (
        "616DA210-FB5B-4158-B5E0-FEB733F419BA",
        "BC89EF96-8CEA-46FF-86C4-4CE0E7609802",
        "5DA37D80-6434-44D0-A028-1B22A696006F",
        "8799B23B-EC83-4686-B30A-512413B5E67A",
        "ED083AE6-46FA-4A59-8FB0-9F97EB10719F",
        "BDBED569-4797-4DF1-A0F4-6AAB3CD982D8",
        "E8B1032C-EA38-4F05-BA0D-38AFFFC7BED3",
    ),
    "medium1": (
        "793D81CF-94F2-401A-BA57-92F5A7B2D0C5",
        "B301B821-A1FF-4177-AEE7-76D212191A09",
        "9DCAF9ED-07DC-4A11-8D7F-57B35C25682E",
        "1FECB4D8-DB02-4DC6-A0A2-4F2EBAE1DC90",
        "1E171933-4619-4E11-9A3F-F7608DF75F80",
        "FABFCF23-3B69-468F-B69F-88F6DE6A72F2",
        "10A1B5D5-9B99-4C35-A422-299274C87663",
    ),
    "medium2": (
        "073A0DAA-6AF3-43AB-8588-CEC1D06C72B9",
        "5C22544A-7EE6-4342-B048-85BDC9FD1C3A",
        "21E4AEA4-8DFA-4A89-87EB-49C32662AFE0",
        "F5AB1C69-6EDB-4FF4-983F-18BD219EF322",
        "00A15C55-8517-42AA-B614-E9B94910E393",
        "7DF18680-E054-41AD-8BC1-D1AEF772440D",
        "93296810-A885-4BE3-A3E7-6D5BEEA58F35",
    ),
    "medium3": (
        "8EC20E35-A176-4012-BC5E-935CFFF8708E",
        "6E25E649-3F16-4E02-A733-19D2CDBF48F0",
        "85BE263C-DBD7-4A20-BB59-AAB30ACAA65A",
        "EB344D84-9AFB-497E-A393-DC336BA19D2E",
        "EB9631B5-78F2-41C9-869B-9F39066F8104",
        "74C1A8A3-306A-4EB7-A6B1-4F7E0EB9C5D6",
        "2A488322-F2BA-4B5B-9748-0D474271808F",
    ),
    "medium4": (
        "D7AC3CCA-C797-4891-BE02-D94E43425B78",
        "69CF1AB2-1976-4502-BF36-3FF5EA218861",
        "8A107856-5554-42FB-B03E-39F5DBC370BA",
        "0505E3EF-67EA-436B-97B2-0124C06EBD24",
        "C4B1156A-380E-4F78-BDF5-A606A8083BF9",
        "22838BEF-8BB2-4498-84A7-C5851F593DF1",
        "16D9F66E-5EB9-4882-86FB-DCBF35E3C3E4",
    ),
    "dark1": (
        "E8034E78-7F5D-4C2E-B375-FC64B27BC917",
        "125E5076-3810-47DD-B79F-674D7AD40C01",
        "37CE84F3-28C3-443E-9E96-99CF82512B78",
        "D03447BB-5D67-496B-8E87-E561075AD55C",
        "E929F9F4-4A8F-4326-A1B4-22849713DDAB",
        "8FD4443E-F989-4FC4-A0C8-D5A2AF1F390B",
        "AF606853-7671-496A-8E4F-DF71F8EC918B",
    ),
}
# Dark Style 2 pairs accents: Accent 1/2, 3/4, 5/6, built on the first.
_DARK2 = (
    ("5202B0CA-FC54-4496-8BCA-5EF66A818D29", 1),
    ("0660B408-B3CF-4A94-85FC-2B1E0A45F4A2", 1),
    ("91EBBBCC-DAD2-459C-BE2E-F6DE35CF9A28", 3),
    ("46F890A9-2807-4EBB-B81D-B2AA78EC7F39", 5),
)
_NO_STYLE = (
    "2D5ABB26-0587-4C30-8999-92F81FD0307C",
    "5940675A-B579-460E-94D1-54222C63F5DA",
)
_DARK_FAMILIES = ("themed2", "dark1")


def _predefined() -> Dict[str, TableStyle]:
    found: Dict[str, TableStyle] = {}
    for family, guids in _FAMILIES.items():
        for position, guid in enumerate(guids):
            found[guid] = TableStyle(
                accent=max(1, position),
                total_row=guid not in _NO_STYLE,
                dark=family in _DARK_FAMILIES and guid not in _NO_STYLE,
            )
    for guid, accent in _DARK2:
        found[guid] = TableStyle(accent=accent, dark=True)
    return found


PREDEFINED: Dict[str, TableStyle] = _predefined()
_DARK_COLOURS = ("dk1", "dk2", "tx1")


def _guid(value: Optional[str]) -> str:
    return (value or "").strip().strip("{}").upper()


def _accent(element: Any) -> Optional[int]:
    """The accent of the first theme colour under ``element``, if any."""
    if element is None:
        return None
    for colour in element.iter(qn("a:schemeClr")):
        value = colour.get("val", "")
        if value.startswith("accent") and value[6:].isdigit():
            return int(value[6:])
    return None


def _custom(styles: Any, guid: str) -> Optional[TableStyle]:
    """A style the file defines in tableStyles.xml."""
    for style in styles.findall(qn("a:tblStyle")):
        if _guid(style.get("styleId")) != guid:
            continue
        whole = style.find(qn("a:wholeTbl"))
        fill = whole.find(qn("a:tcStyle")) if whole is not None else None
        fill = fill.find(qn("a:fill")) if fill is not None else None
        colours = (
            [c.get("val") for c in fill.iter(qn("a:schemeClr"))]
            if fill is not None
            else []
        )
        return TableStyle(
            accent=_accent(style.find(qn("a:firstRow"))) or _accent(whole) or 1,
            total_row=style.find(qn("a:lastRow")) is not None,
            dark=bool(colours) and colours[0] in _DARK_COLOURS,
        )
    return None


def _style_part(presentation: Any) -> Any:
    try:
        part = presentation.part.part_related_by(RT.TABLE_STYLES)
        return parse_xml(part.blob)
    except (KeyError, ValueError, SyntaxError):
        return None


def table_style(presentation: Any, tbl: Any) -> TableStyle:
    """The style a table is drawn with: its own style id, else the file's
    default; an unknown style reads as no total-row formatting on accent 1."""
    tblPr = tbl.find(qn("a:tblPr"))
    node = tblPr.find(qn("a:tableStyleId")) if tblPr is not None else None
    styles = _style_part(presentation)
    guid = _guid(node.text if node is not None else None)
    if not guid and styles is not None:
        guid = _guid(styles.get("def"))
    if guid in PREDEFINED:
        return PREDEFINED[guid]
    custom = _custom(styles, guid) if styles is not None and guid else None
    return custom or TableStyle(total_row=False)


# --- emphasis ---------------------------------------------------------------------------

# (field, summary code, agent note) of an intent drawn otherwise or not at all.
Told = Tuple[str, Literal["intent_not_shown", "intent_shown_otherwise"], str]
_ACCENTS = (
    MSO_THEME_COLOR.ACCENT_1,
    MSO_THEME_COLOR.ACCENT_2,
    MSO_THEME_COLOR.ACCENT_3,
    MSO_THEME_COLOR.ACCENT_4,
    MSO_THEME_COLOR.ACCENT_5,
    MSO_THEME_COLOR.ACCENT_6,
)
# The tint's brightness: lumMod 60 % lumOff 40 %, stronger than the 20 % and
# 40 % bands of the predefined styles; lumMod 40 % lumOff 60 % when dark text
# would not read on it.
_TINT = 0.4
_PALE_TINT = 0.6
_READABLE = 4.5  # WCAG contrast of body text


def _listed(texts: Sequence[str]) -> str:
    shown = [f"'{t}'" for t in texts[:6] if t]
    return ", ".join(shown) + (", …" if len(texts) > 6 else "")


def _find(reference: int | str, names: Sequence[str]) -> Optional[int]:
    """An index, a text matching one of ``names``, or digits read as an index."""
    if isinstance(reference, int):
        return reference if 0 <= reference < len(names) else None
    wanted = lexicon.normalize(reference)
    for index, name in enumerate(names):
        if lexicon.normalize(name) == wanted:
            return index
    if reference.isdigit() and int(reference) < len(names):
        return int(reference)
    return None


def part_row(
    table: PlanTable, start: int, size: int, first: bool
) -> Optional[int | str]:
    """The highlighted row of a table split over slides, on the part holding
    rows ``start`` to ``start + size``; one that matches nothing stays on the
    first part, so its note is said once."""
    if table.highlight_row is None:
        return None
    found = _find(table.highlight_row, [row[0] if row else "" for row in table.rows])
    if found is None:
        return table.highlight_row if first else None
    return found - start if start <= found < start + size else None


def _bold(tc: Any) -> None:
    for run in tc.iter(qn("a:r")):
        run.get_or_add_rPr().set("b", "1")


def _theme_rgb(presentation: Any, names: Sequence[str]) -> List[Optional[str]]:
    """The hex colours ``names`` take in the first master's theme."""
    try:
        master = presentation.slide_masters[0].part
        scheme = parse_xml(master.part_related_by(RT.THEME).blob).find(
            f".//{qn('a:clrScheme')}"
        )
    except (IndexError, KeyError, ValueError, SyntaxError):
        return [None] * len(names)
    found: List[Optional[str]] = []
    for name in names:
        slot = scheme.find(qn(f"a:{name}")) if scheme is not None else None
        colour = slot[0] if slot is not None and len(slot) else None
        found.append(
            None if colour is None else colour.get("val") or colour.get("lastClr")
        )
    return found


def _luminance(rgb: Sequence[float]) -> float:
    linear = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def tint_level(presentation: Any, accent: int) -> float:
    """The strong tint, unless the theme's dark text would not read on it."""
    hexes = _theme_rgb(presentation, [f"accent{min(max(accent, 1), 6)}", "dk1"])
    known = [h for h in hexes if h and len(h) == 6]
    try:
        fill, text = [[int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)] for h in known]
    except ValueError:  # an unreadable colour, or one of the two missing
        return _TINT
    hue, light, sat = colorsys.rgb_to_hls(*fill)
    light = min(1.0, light * (1 - _TINT) + _TINT)  # what lumMod/lumOff do
    tinted = _luminance(colorsys.hls_to_rgb(hue, light, sat))
    dark = _luminance(text)
    ratio = (max(tinted, dark) + 0.05) / (min(tinted, dark) + 0.05)
    return _TINT if ratio >= _READABLE else _PALE_TINT


def _tint(tc: Any, accent: int, level: float) -> None:
    fill = FillFormat.from_fill_parent(tc.get_or_add_tcPr())
    fill.solid()
    fill.fore_color.theme_color = _ACCENTS[min(max(accent, 1), 6) - 1]
    fill.fore_color.brightness = level


def _total_row(
    tblPr: Any, body: List[Any], table: PlanTable, style: TableStyle
) -> List[Told]:
    """The style's total-row flag on the last row, or bold where it has none;
    a template's flag goes when the plan has no total."""
    tblPr.attrib.pop("lastRow", None)
    if not table.total_row:
        return []
    if len(body) < 2:
        return [
            (
                "total_row",
                "intent_not_shown",
                "table.total_row was not applied: a total needs at least two rows. "
                "Nothing to do; drop table.total_row, or add the rows it totals.",
            )
        ]
    if style.total_row:
        tblPr.set("lastRow", "1")
        return []
    for tc in body[-1].findall(qn("a:tc")):
        _bold(tc)
    return [
        (
            "total_row",
            "intent_shown_otherwise",
            "the table's style has no total-row formatting, so the total row is "
            "shown in bold. Nothing to do.",
        )
    ]


def _emphasise(
    cells: List[Any], name: str, style: TableStyle, level: float
) -> List[Told]:
    for tc in cells:
        _bold(tc)
        if not style.dark:
            _tint(tc, style.accent, level)
    if not style.dark:
        return []
    return [
        (
            name,
            "intent_shown_otherwise",
            f"the table's style is dark, so table.{name} is shown in bold without a "
            "tint. Nothing to do.",
        )
    ]


def _row(
    body: List[Any], table: PlanTable, shift: int, style: TableStyle, level: float
) -> List[Told]:
    reference = table.highlight_row
    if reference is None:
        return []
    firsts = [row[0] if row else "" for row in table.rows]
    found = _find(reference, firsts)
    at = None if found is None else found - shift
    if found is not None and at is not None and 0 <= at < len(body):
        return _emphasise(body[at].findall(qn("a:tc")), "highlight_row", style, level)
    why = (
        f"table.highlight_row '{reference}' is rows[0], shown as the table's header"
        if at is not None and at < 0
        else f"table.highlight_row '{reference}' matches no row (first cells: "
        f"{_listed(firsts)})"
    )
    return [
        (
            "highlight_row",
            "intent_not_shown",
            f"{why}; built without it. To set it, edit table.highlight_row to a row's "
            "first cell or its index in rows (from 0).",
        )
    ]


def _column(
    body: List[Any], table: PlanTable, shift: int, style: TableStyle, level: float
) -> List[Told]:
    reference = table.highlight_column
    if reference is None:
        return []
    # A plan without a header whose first row became the template's header.
    names = (
        table.header
        if any(table.header)
        else table.rows[0]
        if shift == 1 and table.rows
        else [""] * table.width
    )
    at = _find(reference, names)
    if at is not None:
        cells = [tr.findall(qn("a:tc")) for tr in body]
        return _emphasise(
            [row[at] for row in cells if at < len(row)],
            "highlight_column",
            style,
            level,
        )
    headers = f"headers: {_listed(names)}" if any(names) else "no header"
    return [
        (
            "highlight_column",
            "intent_not_shown",
            f"table.highlight_column '{reference}' matches no column ({headers}); built "
            "without it. To set it, edit table.highlight_column to a header or its "
            f"index (0 to {table.width - 1}).",
        )
    ]


def emphasise(
    presentation: Any, tbl: Any, table: PlanTable, head: bool, shift: int
) -> List[Told]:
    """Draw ``table``'s intents on a filled ``tbl`` (``head``: its first row is
    the header; plan row i is body row i - ``shift``)."""
    style = table_style(presentation, tbl)
    tblPr = tbl.find(qn("a:tblPr"))
    if tblPr is None:
        tblPr = tbl.makeelement(qn("a:tblPr"), {})
        tbl.insert(0, tblPr)
    body = tbl.findall(qn("a:tr"))[1 if head else 0 :]
    wanted = table.highlight_row is not None or table.highlight_column is not None
    level = tint_level(presentation, style.accent) if wanted else _TINT
    return (
        _total_row(tblPr, body, table, style)
        + _row(body, table, shift, style, level)
        + _column(body, table, shift, style, level)
    )
