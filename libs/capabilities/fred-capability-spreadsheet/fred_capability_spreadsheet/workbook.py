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

"""Tool input models and the synchronous `.xlsx` builder.

`build_workbook` validates the whole request and returns the workbook bytes, or
raises `SpreadsheetInputError` with a message the model can act on. It is
CPU-bound: callers run it in a worker thread.
"""

from __future__ import annotations

import io
import json
import math
import re
from datetime import date, datetime
from typing import Literal, cast

from openpyxl import Workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SHEETS = 10
MAX_COLUMNS = 50
MAX_ROWS = 5_000
MAX_CELLS = 50_000
MAX_CELL_CHARS = 2_000
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_ROWS = 500

ColumnType = Literal["text", "number", "integer", "percent", "currency", "date"]
TotalKind = Literal["sum", "average", "min", "max", "count"]
CurrencyCode = Literal["EUR", "USD", "GBP", "CHF", "JPY", "CNY", "CAD", "AUD"]
CellValue = str | int | float | bool | None

# Excel number formats; the quoted symbol is literal text, so it renders the same
# in every locale (the `,` and `.` placeholders still follow the reader's locale).
CURRENCY_FORMATS: dict[str, str] = {
    "EUR": '#,##0.00 "€"',
    "USD": '"$"#,##0.00',
    "GBP": '"£"#,##0.00',
    "CHF": '"CHF "#,##0.00',
    "JPY": '"¥"#,##0',
    "CNY": '"¥"#,##0.00',
    "CAD": '"CA$"#,##0.00',
    "AUD": '"A$"#,##0.00',
}
NUMBER_FORMATS: dict[str, str] = {
    "number": "#,##0.00",
    "integer": "#,##0",
    "currency": "#,##0.00",
    "date": "yyyy-mm-dd",
}

_FORBIDDEN_SHEET_CHARS = set("[]:*?/\\")
# Text starting with one of these would be read as a formula by a spreadsheet.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_NUMERIC_JUNK = re.compile(r"[\s  _$€£¥]")
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(
    fill_type="solid", start_color="FFD9D9D9", end_color="FFD9D9D9"
)
_HEADER_BORDER = Border(bottom=Side(style="thin", color="FF808080"))
_TOTAL_FUNCTIONS = {
    "sum": "SUM",
    "average": "AVERAGE",
    "min": "MIN",
    "max": "MAX",
    "count": "COUNT",
}


class SpreadsheetInputError(ValueError):
    """The request cannot become a workbook; the message is shown to the model."""


def _lower(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    header: str = Field(description="Column title shown in the header row.")
    type: ColumnType = Field(
        default="text",
        description=(
            "Cell type: text, number, integer, percent (0.15 or '15%'), "
            "currency (an amount) or date ('YYYY-MM-DD')."
        ),
    )
    currency: CurrencyCode | None = Field(
        default=None,
        description="For a currency column: the currency whose symbol is shown, e.g. EUR or USD.",
    )
    width: int | None = Field(
        default=None, description="Column width in characters; computed when omitted."
    )
    total: TotalKind | None = Field(
        default=None,
        description="Add a totals row computing this column with an Excel formula.",
    )

    @field_validator("type", "total", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return _lower(value)

    @field_validator("currency", mode="before")
    @classmethod
    def _uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class SheetSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Sheet tab name, at most 31 characters.")
    columns: list[ColumnSpec] = Field(description="The sheet's columns, in order.")
    rows: list[list[CellValue]] = Field(
        default_factory=list,
        description="Data rows; each row has exactly one value per column (null for empty).",
    )


class CreateSpreadsheetInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_name: str = Field(
        description="Short file name without extension, e.g. 'Q3 budget'."
    )
    sheets: list[SheetSpec] = Field(description="One or more sheets (at most 10).")


def sanitize_file_name(raw: str) -> str:
    """Keep a safe, non-empty base name; the caller adds the extension."""

    name = raw.replace("\\", "/").split("/")[-1].strip().strip("\"'").strip()
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"|?*')
    if name.lower().endswith(".xlsx"):
        name = name[:-5].rstrip()
    return name[:100].strip() or "spreadsheet"


def build_workbook(request: CreateSpreadsheetInput) -> bytes:
    """Validate the request and return the `.xlsx` bytes."""

    _check_structure(request)
    workbook = Workbook()
    for default_sheet in workbook.worksheets:
        workbook.remove(default_sheet)
    workbook.properties.creator = "Fred"
    for sheet in request.sheets:
        _write_sheet(workbook.create_sheet(title=sheet.name), sheet)
    buffer = io.BytesIO()
    workbook.save(buffer)
    data = buffer.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise SpreadsheetInputError(
            f"The workbook is too large ({len(data) // 1024} KB; the limit is "
            f"{MAX_OUTPUT_BYTES // (1024 * 1024)} MB). Split it or reduce the data."
        )
    return data


def build_preview(request: CreateSpreadsheetInput) -> bytes:
    """Return the chat preview of an already validated request, as UTF-8 JSON.

    Display only: typed values, the decimals each number format shows, the first
    `MAX_PREVIEW_ROWS` rows per sheet and computed totals (the file keeps formulas).
    """

    sheets = [_preview_sheet(sheet) for sheet in request.sheets]
    payload = {"version": 1, "sheets": sheets}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _preview_sheet(sheet: SheetSpec) -> dict[str, object]:
    columns: list[dict[str, object]] = []
    values: list[list[str | int | float | None]] = []
    for row in sheet.rows:
        values.append(
            [
                _preview_value(_convert(raw, column.type, column.header))
                for column, raw in zip(sheet.columns, row, strict=True)
            ]
        )
    for index, column in enumerate(sheet.columns):
        entry: dict[str, object] = {"header": column.header, "type": column.type}
        if column.type not in ("text", "date"):
            fmt = _number_format(column, sheet.rows, index)
            entry["decimals"] = _format_decimals(fmt)
        if column.currency and column.type == "currency":
            entry["currency"] = column.currency
        if column.total:
            entry["total"] = column.total
        columns.append(entry)
    return {
        "name": sheet.name,
        "columns": columns,
        "rows": values[:MAX_PREVIEW_ROWS],
        "row_count": len(values),
        "totals": _preview_totals(sheet.columns, values),
    }


def _preview_value(value: str | float | date | None) -> str | float | None:
    return value.isoformat() if isinstance(value, date) else value


def _format_decimals(fmt: str) -> int:
    if "." not in fmt:
        return 0
    tail = fmt.split(".", 1)[1]
    return len(tail) - len(tail.lstrip("0"))


def _preview_totals(
    columns: list[ColumnSpec], rows: list[list[str | int | float | None]]
) -> list[str | int | float | None] | None:
    # Same placement as `_write_totals`; values mirror the Excel functions.
    if not rows or not any(column.total for column in columns):
        return None
    label_index = next(
        (i for i, c in enumerate(columns) if c.type == "text" and not c.total), None
    )
    totals: list[str | int | float | None] = [None] * len(columns)
    if label_index is not None:
        totals[label_index] = "Total"
    for index, column in enumerate(columns):
        present = [row[index] for row in rows if row[index] is not None]
        if column.total == "count":
            totals[index] = len(present)
            continue
        if not column.total:
            continue
        numbers = [float(value) for value in present if isinstance(value, int | float)]
        if column.total == "sum":
            totals[index] = math.fsum(numbers)
        elif column.total == "average":
            totals[index] = math.fsum(numbers) / len(numbers) if numbers else None
        elif column.total == "min":
            totals[index] = min(numbers, default=0)
        else:
            totals[index] = max(numbers, default=0)
    return totals


def _check_structure(request: CreateSpreadsheetInput) -> None:
    sheets = request.sheets
    if not sheets:
        raise SpreadsheetInputError("Provide at least one sheet.")
    if len(sheets) > MAX_SHEETS:
        raise SpreadsheetInputError(
            f"{len(sheets)} sheets were sent; the limit is {MAX_SHEETS} sheets."
        )
    seen: set[str] = set()
    total_cells = 0
    for sheet in sheets:
        _check_sheet_name(sheet.name, seen)
        where = f"Sheet '{sheet.name}'"
        if not sheet.columns:
            raise SpreadsheetInputError(f"{where} has no columns.")
        if len(sheet.columns) > MAX_COLUMNS:
            raise SpreadsheetInputError(
                f"{where} has {len(sheet.columns)} columns; the limit is {MAX_COLUMNS} columns."
            )
        if len(sheet.rows) > MAX_ROWS:
            raise SpreadsheetInputError(
                f"{where} has {len(sheet.rows)} rows; the limit is {MAX_ROWS} rows per sheet. "
                "No data was truncated and no file was written."
            )
        for index, column in enumerate(sheet.columns, start=1):
            if column.total in ("sum", "average", "min", "max") and column.type in (
                "text",
                "date",
            ):
                raise SpreadsheetInputError(
                    f"{where}, column {index} ('{column.header}'): a '{column.total}' "
                    f"total needs a numeric column, not '{column.type}'."
                )
        for row_number, row in enumerate(sheet.rows, start=2):
            if len(row) != len(sheet.columns):
                raise SpreadsheetInputError(
                    f"{where}, row {row_number}: {len(row)} values for "
                    f"{len(sheet.columns)} columns. Send exactly one value per "
                    "column (null for an empty cell)."
                )
        total_cells += len(sheet.columns) * (len(sheet.rows) + 1)
    if total_cells > MAX_CELLS:
        raise SpreadsheetInputError(
            f"The workbook holds {total_cells} cells; the limit is {MAX_CELLS} cells in total."
        )


def _check_sheet_name(name: str, seen: set[str]) -> None:
    if not name.strip():
        raise SpreadsheetInputError("A sheet name is empty.")
    if len(name) > 31:
        raise SpreadsheetInputError(
            f"Sheet name '{name}' is {len(name)} characters long; the limit is 31."
        )
    bad = sorted(_FORBIDDEN_SHEET_CHARS.intersection(name))
    if bad or name.startswith("'") or name.endswith("'"):
        raise SpreadsheetInputError(
            f"Sheet name '{name}' cannot contain [ ] : * ? / \\ or start or end with '."
        )
    if name.lower() in seen:
        raise SpreadsheetInputError(f"Sheet name '{name}' is used twice.")
    seen.add(name.lower())


def _write_sheet(ws: Worksheet, sheet: SheetSpec) -> None:
    columns = sheet.columns
    widths = [len(column.header) for column in columns]
    formats = [
        _number_format(column, sheet.rows, i) for i, column in enumerate(columns)
    ]

    for index, column in enumerate(columns, start=1):
        cell = _cell(ws, 1, index)
        _set_text(cell, column.header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _HEADER_BORDER

    for row_number, row in enumerate(sheet.rows, start=2):
        for index, (column, raw) in enumerate(zip(columns, row, strict=True)):
            where = f"Sheet '{sheet.name}', row {row_number}, column {index + 1} ('{column.header}')"
            value = _convert(raw, column.type, where)
            if value is None:
                continue
            cell = _cell(ws, row_number, index + 1)
            if isinstance(value, str):
                _set_text(cell, value)
            else:
                cell.value = value
                if formats[index]:
                    cell.number_format = formats[index]
            widths[index] = max(widths[index], _display_length(value))

    last_row = len(sheet.rows) + 1
    last_column = get_column_letter(len(columns))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{last_column}{last_row}"
    if sheet.rows and any(column.total for column in columns):
        _write_totals(ws, columns, formats, last_row)

    for index, column in enumerate(columns):
        width = (
            min(max(column.width, 4), 100)
            if column.width is not None
            else min(widths[index] + 2, 60)
        )
        ws.column_dimensions[get_column_letter(index + 1)].width = width


def _write_totals(
    ws: Worksheet, columns: list[ColumnSpec], formats: list[str], last_row: int
) -> None:
    total_row = last_row + 1
    label_index = next(
        (i for i, c in enumerate(columns) if c.type == "text" and not c.total), None
    )
    if label_index is not None:
        label = ws.cell(row=total_row, column=label_index + 1, value="Total")
        label.font = _HEADER_FONT
    for index, column in enumerate(columns):
        if not column.total:
            continue
        letter = get_column_letter(index + 1)
        function = _TOTAL_FUNCTIONS[column.total]
        if column.total == "count" and column.type in ("text", "date"):
            function = "COUNTA" if column.type == "text" else "COUNT"
        cell = ws.cell(
            row=total_row,
            column=index + 1,
            value=f"={function}({letter}2:{letter}{last_row})",
        )
        cell.font = _HEADER_FONT
        if column.total == "count":
            cell.number_format = NUMBER_FORMATS["integer"]
        elif column.total == "average" and column.type == "integer":
            cell.number_format = NUMBER_FORMATS["number"]
        elif formats[index]:
            cell.number_format = formats[index]


def _number_format(column: ColumnSpec, rows: list[list[CellValue]], index: int) -> str:
    if column.type == "currency" and column.currency:
        return CURRENCY_FORMATS[column.currency]
    if column.type == "percent":
        decimals = 0
        for row in rows:
            raw = row[index] if index < len(row) else None
            try:
                value = _to_percent(raw)
            except (TypeError, ValueError):
                continue
            if value is not None:
                decimals = max(decimals, _decimals(value * 100))
        return "0%" if decimals == 0 else "0." + "0" * min(decimals, 2) + "%"
    return NUMBER_FORMATS.get(column.type, "")


def _decimals(value: float) -> int:
    text = f"{round(value, 6):.6f}".rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0


def _cell(ws: Worksheet, row: int, column: int) -> Cell:
    # Never a MergedCell: this builder merges nothing.
    return cast(Cell, ws.cell(row=row, column=column))


def _set_text(cell: Cell, value: str) -> None:
    cell.value = value
    if value.startswith(_FORMULA_TRIGGERS):
        # Stored as a literal string; the quote prefix keeps it text when edited.
        cell.data_type = "s"
        cell.quotePrefix = True


def _display_length(value: object) -> int:
    if isinstance(value, int | float):
        # Two decimals plus room for a currency symbol or a percent sign.
        return len(f"{value:,.2f}") + 3
    if isinstance(value, date):
        return 10
    return max((len(line) for line in str(value).splitlines()), default=0)


def _convert(
    raw: CellValue, column_type: str, where: str
) -> str | int | float | date | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str) and len(raw) > MAX_CELL_CHARS:
        raise SpreadsheetInputError(
            f"{where}: the value has {len(raw)} characters; the limit is {MAX_CELL_CHARS}."
        )
    try:
        if column_type == "text":
            return _to_text(raw)
        if column_type == "date":
            return _to_date(raw)
        if column_type == "percent":
            return _to_percent(raw)
        number = _to_number(raw)
        if column_type == "integer":
            if not float(number).is_integer():
                raise ValueError
            return int(number)
        return number
    except (TypeError, ValueError):
        expected = {
            "date": "a date written YYYY-MM-DD",
            "percent": "a fraction like 0.15 or a string like '15%'",
            "integer": "a whole number",
        }.get(column_type, "a number")
        raise SpreadsheetInputError(
            f"{where}: {raw!r} is not {expected}. Fix the value or change the column type."
        ) from None


def _to_text(raw: CellValue) -> str:
    if isinstance(raw, bool):
        return "TRUE" if raw else "FALSE"
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw)


def _to_number(raw: CellValue) -> int | float:
    if isinstance(raw, bool):
        raise TypeError
    if isinstance(raw, int | float):
        return raw
    assert raw is not None
    text = _NUMERIC_JUNK.sub("", raw)
    if "," in text and "." in text:
        # The last separator is the decimal one.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") == 1:
        text = text.replace(",", ".")
    elif "," in text:
        raise ValueError
    number = float(text)
    if not math.isfinite(number):
        raise ValueError
    return number


def _to_percent(raw: CellValue) -> float | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str) and raw.strip().endswith("%"):
        return float(_to_number(raw.strip()[:-1])) / 100
    return float(_to_number(raw))


def _to_date(raw: CellValue) -> date:
    if not isinstance(raw, str):
        raise TypeError
    text = raw.strip()
    if len(text) > 10:
        return datetime.fromisoformat(text).date()
    return date.fromisoformat(text)
