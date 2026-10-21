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

"""Workbook builder: every generated file is read back with openpyxl."""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

import pytest
from fred_capability_spreadsheet.workbook import (
    MAX_CELL_CHARS,
    MAX_PREVIEW_ROWS,
    CreateSpreadsheetInput,
    SpreadsheetInputError,
    build_preview,
    build_workbook,
    sanitize_file_name,
)
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet


def _request(*sheets: dict[str, Any]) -> CreateSpreadsheetInput:
    return CreateSpreadsheetInput.model_validate(
        {"file_name": "test", "sheets": list(sheets)}
    )


def _sheet(name: str = "Data", columns=None, rows=None) -> dict[str, Any]:
    return {
        "name": name,
        "columns": columns or [{"header": "Item"}],
        "rows": rows if rows is not None else [],
    }


def _build(*sheets: dict[str, Any]) -> Any:
    return load_workbook(io.BytesIO(build_workbook(_request(*sheets))))


def _ws(*sheets: dict[str, Any]) -> Worksheet:
    sheet = _build(*sheets).worksheets[0]
    assert isinstance(sheet, Worksheet)
    return sheet


def _error(*sheets: dict[str, Any]) -> str:
    with pytest.raises(SpreadsheetInputError) as info:
        build_workbook(_request(*sheets))
    return str(info.value)


TYPED_COLUMNS = [
    {"header": "Name"},
    {"header": "Qty", "type": "integer"},
    {"header": "Price", "type": "number"},
    {"header": "Rate", "type": "percent"},
    {"header": "Amount", "type": "currency", "currency": "EUR"},
    {"header": "Due", "type": "date"},
]


def test_typed_columns_get_values_and_number_formats():
    ws = _ws(
        _sheet(
            columns=TYPED_COLUMNS,
            rows=[["Bolt", 3, "1 234,5", "15%", 1234.5, "2026-10-21"]],
        )
    )
    assert [c.value for c in ws[1]] == ["Name", "Qty", "Price", "Rate", "Amount", "Due"]
    name, qty, price, rate, amount, due = ws[2]
    assert name.value == "Bolt"
    assert (qty.value, qty.number_format) == (3, "#,##0")
    assert (price.value, price.number_format) == (1234.5, "#,##0.00")
    assert (rate.value, rate.number_format) == (0.15, "0%")
    assert amount.value == 1234.5
    assert amount.number_format == '#,##0.00 "€"'
    assert due.value == datetime(2026, 10, 21)
    assert due.number_format == "yyyy-mm-dd"


def test_percent_keeps_needed_decimals():
    ws = _ws(_sheet(columns=[{"header": "Rate", "type": "percent"}], rows=[[0.125]]))
    assert ws["A2"].number_format == "0.0%"


@pytest.mark.parametrize(
    ("currency", "fmt"),
    [
        ("USD", '"$"#,##0.00'),
        ("gbp", '"£"#,##0.00'),
        ("JPY", '"¥"#,##0'),
        (None, "#,##0.00"),
    ],
)
def test_currency_formats(currency, fmt):
    column = {"header": "Amount", "type": "currency", "currency": currency}
    ws = _ws(_sheet(columns=[column], rows=[[10]]))
    assert ws["A2"].number_format == fmt


def test_enum_values_are_case_insensitive():
    request = _request(
        _sheet(columns=[{"header": "N", "type": "Number", "total": "SUM"}], rows=[[1]])
    )
    column = request.sheets[0].columns[0]
    assert (column.type, column.total) == ("number", "sum")


def test_header_is_bold_frozen_and_filtered():
    ws = _ws(_sheet(columns=TYPED_COLUMNS[:2], rows=[["a", 1], ["b", 2]]))
    assert all(cell.font.b for cell in ws[1])
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:B3"


def test_widths_are_declared_or_computed_and_capped():
    columns = [
        {"header": "Short"},
        {"header": "Fixed", "width": 30},
        {"header": "Long"},
    ]
    ws = _ws(_sheet(columns=columns, rows=[["abc", "x", "y" * 200]]))
    assert ws.column_dimensions["A"].width == len("Short") + 2
    assert ws.column_dimensions["B"].width == 30
    assert ws.column_dimensions["C"].width == 60


def test_totals_row_holds_formulas_with_column_formats():
    columns = [
        {"header": "Item"},
        {"header": "Qty", "type": "integer", "total": "average"},
        {"header": "Amount", "type": "currency", "currency": "EUR", "total": "sum"},
        {"header": "Min", "type": "number", "total": "min"},
        {"header": "Max", "type": "number", "total": "max"},
        {"header": "Label", "total": "count"},
    ]
    rows = [[f"i{n}", n, n * 10, n, n, "x"] for n in range(1, 11)]
    ws = _ws(_sheet(columns=columns, rows=rows))
    total = [c.value for c in ws[12]]
    assert total == [
        "Total",
        "=AVERAGE(B2:B11)",
        "=SUM(C2:C11)",
        "=MIN(D2:D11)",
        "=MAX(E2:E11)",
        "=COUNTA(F2:F11)",
    ]
    assert ws["B12"].number_format == "#,##0.00"
    assert ws["C12"].number_format == '#,##0.00 "€"'
    assert ws["F12"].number_format == "#,##0"
    assert ws["A12"].font.b
    # The totals row stays outside the filter range.
    assert ws.auto_filter.ref == "A1:F11"


def test_no_totals_row_without_data():
    ws = _ws(_sheet(columns=[{"header": "N", "type": "number", "total": "sum"}]))
    assert ws.max_row == 1


def test_formula_like_text_is_stored_as_literal_text():
    payload = '=HYPERLINK("http://example.test","x")'
    ws = _ws(
        _sheet(columns=[{"header": "Note"}], rows=[[payload], ["+1"], ["@SUM(A1)"]])
    )
    for row, expected in ((2, payload), (3, "+1"), (4, "@SUM(A1)")):
        cell = ws.cell(row=row, column=1)
        assert cell.value == expected
        assert cell.data_type == "s"
        assert cell.quotePrefix


def test_multiple_sheets_and_empty_cells():
    workbook = _build(
        _sheet("Q1", rows=[["a"], [None], [""]]),
        _sheet("Q2", columns=[{"header": "N", "type": "number"}], rows=[[1]]),
    )
    assert workbook.sheetnames == ["Q1", "Q2"]
    q1 = workbook["Q1"]
    assert q1["A3"].value is None and q1["A4"].value is None
    assert workbook.properties.creator == "Fred"


def test_text_column_renders_non_strings():
    ws = _ws(_sheet(rows=[[12.0], [True], [3.5]]))
    assert [ws.cell(row=r, column=1).value for r in (2, 3, 4)] == ["12", "TRUE", "3.5"]


@pytest.mark.parametrize(
    ("sheets", "fragment"),
    [
        ([_sheet(name=" ")], "sheet name is empty"),
        ([_sheet(name="x" * 32)], "limit is 31"),
        ([_sheet(name="a/b")], "cannot contain"),
        ([_sheet(name="'quoted'")], "cannot contain"),
        ([_sheet("Data"), _sheet("data")], "used twice"),
        ([{"name": "Data", "columns": [], "rows": []}], "has no columns"),
    ],
)
def test_structure_errors(sheets, fragment):
    assert fragment in _error(*sheets)


def test_row_length_mismatch_names_sheet_and_row():
    message = _error(
        _sheet("Sales", columns=TYPED_COLUMNS[:3], rows=[["a", 1, 2], ["b", 1, 2, 3]])
    )
    assert "Sheet 'Sales', row 3: 4 values for 3 columns" in message


@pytest.mark.parametrize(
    ("column", "value", "fragment"),
    [
        ({"header": "Qty", "type": "integer"}, 1.5, "a whole number"),
        ({"header": "Due", "type": "date"}, "21/10/2026", "YYYY-MM-DD"),
        ({"header": "Price", "type": "number"}, "cheap", "a number"),
        ({"header": "Rate", "type": "percent"}, "high", "0.15"),
        ({"header": "Price", "type": "number"}, True, "a number"),
    ],
)
def test_conversion_errors_name_sheet_row_and_column(column, value, fragment):
    message = _error(
        _sheet("Sales", columns=[{"header": "Name"}, column], rows=[["a", value]])
    )
    assert f"Sheet 'Sales', row 2, column 2 ('{column['header']}')" in message
    assert fragment in message


def test_numeric_total_on_text_column_is_rejected():
    message = _error(_sheet(columns=[{"header": "Name", "total": "sum"}], rows=[["a"]]))
    assert "needs a numeric column" in message


def test_limits():
    assert "limit is 10 sheets" in _error(*[_sheet(f"S{i}") for i in range(11)])
    wide = [{"header": f"c{i}"} for i in range(51)]
    assert "limit is 50 columns" in _error(_sheet(columns=wide))
    tall = _sheet(rows=[["x"]] * 5001)
    assert "limit is 5000 rows" in _error(tall)
    cells = _sheet(
        columns=[{"header": f"c{i}"} for i in range(20)], rows=[["x"] * 20] * 2600
    )
    assert "limit is 50000 cells" in _error(cells)
    assert f"limit is {MAX_CELL_CHARS}" in _error(
        _sheet(rows=[["x" * (MAX_CELL_CHARS + 1)]])
    )


def test_limits_are_inclusive():
    build_workbook(_request(_sheet(rows=[["x"]] * 5000)))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Q3 budget", "Q3 budget"),
        ("../etc/passwd", "passwd"),
        ("report.xlsx", "report"),
        ('a<b>:"c', "abc"),
        ("   ", "spreadsheet"),
    ],
)
def test_sanitize_file_name(raw, expected):
    assert sanitize_file_name(raw) == expected


def _preview(*sheets: dict[str, Any]) -> dict[str, Any]:
    return json.loads(build_preview(_request(*sheets)))


def test_preview_carries_typed_values_and_display_formats():
    columns = [
        *TYPED_COLUMNS[:4],
        {"header": "Amount", "type": "currency", "currency": "JPY"},
        {"header": "Due", "type": "date"},
    ]
    rows = [["Pen", "3", "1,5", "12.5%", 1200, "2026-01-31T10:00:00"]]
    sheet = _preview(_sheet(columns=columns, rows=rows))["sheets"][0]

    assert sheet["name"] == "Data"
    assert sheet["rows"] == [["Pen", 3, 1.5, 0.125, 1200, "2026-01-31"]]
    assert sheet["row_count"] == 1
    assert sheet["totals"] is None
    assert sheet["columns"] == [
        {"header": "Name", "type": "text"},
        {"header": "Qty", "type": "integer", "decimals": 0},
        {"header": "Price", "type": "number", "decimals": 2},
        {"header": "Rate", "type": "percent", "decimals": 1},
        {"header": "Amount", "type": "currency", "decimals": 0, "currency": "JPY"},
        {"header": "Due", "type": "date"},
    ]


def test_preview_totals_mirror_the_excel_functions():
    columns = [
        {"header": "Line"},
        {"header": "Sum", "type": "currency", "currency": "EUR", "total": "sum"},
        {"header": "Avg", "type": "integer", "total": "average"},
        {"header": "Min", "type": "number", "total": "min"},
        {"header": "Max", "type": "percent", "total": "max"},
        {"header": "Count", "type": "text", "total": "count"},
    ]
    rows = [
        ["a", 1200, 1, 4.5, 0.1, "x"],
        ["b", 350.5, 2, None, "25%", None],
        ["c", None, None, -2, None, "y"],
    ]
    sheet = _preview(_sheet(columns=columns, rows=rows))["sheets"][0]
    assert sheet["totals"] == ["Total", 1550.5, 1.5, -2, 0.25, 2]
    assert sheet["columns"][1]["total"] == "sum"


def test_preview_total_of_an_empty_numeric_column():
    columns = [
        {"header": "Sum", "type": "number", "total": "sum"},
        {"header": "Avg", "type": "number", "total": "average"},
    ]
    sheet = _preview(_sheet(columns=columns, rows=[[None, None]]))["sheets"][0]
    assert sheet["totals"] == [0, None]


def test_preview_caps_rows_but_totals_cover_every_row():
    count = MAX_PREVIEW_ROWS + 20
    columns = [{"header": "N", "type": "integer", "total": "sum"}]
    rows = [[1] for _ in range(count)]
    sheet = _preview(_sheet(columns=columns, rows=rows))["sheets"][0]
    assert len(sheet["rows"]) == MAX_PREVIEW_ROWS
    assert sheet["row_count"] == count
    assert sheet["totals"] == [count]


def test_preview_keeps_every_sheet_and_formula_like_text():
    preview = _preview(_sheet("One", rows=[["=1+1"]]), _sheet("Two", rows=[["été"]]))
    assert preview["version"] == 1
    assert [s["name"] for s in preview["sheets"]] == ["One", "Two"]
    assert preview["sheets"][0]["rows"] == [["=1+1"]]
    assert preview["sheets"][1]["rows"] == [["été"]]
