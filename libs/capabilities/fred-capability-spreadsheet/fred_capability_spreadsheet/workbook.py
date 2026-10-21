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

"""Tool input models and the synchronous `.xlsx` and preview builders.

`prepare` validates the whole request and converts every value once, or raises
`SpreadsheetInputError` with a message the model can act on; `build_workbook` and
`build_preview` both read its result. CPU-bound: callers run them in a worker thread.
"""

from __future__ import annotations

import io
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, cast

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
Language = Literal["fr", "en"]
CellValue = str | int | float | bool | None
Converted = str | int | float | date | None

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
    # Built-in numFmtId 14: Excel shows it as the reader's system short date.
    "date": "mm-dd-yy",
}
TOTAL_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "sum": "Total",
        "average": "Moyenne",
        "min": "Min",
        "max": "Max",
        "count": "Nombre",
    },
    "en": {
        "sum": "Total",
        "average": "Average",
        "min": "Min",
        "max": "Max",
        "count": "Count",
    },
}

_FORBIDDEN_SHEET_CHARS = set("[]:*?/\\")
# Excel reserves this sheet name for its change history.
_RESERVED_SHEET_NAMES = {"history"}
# Text starting with one of these would be read as a formula by a spreadsheet.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
# A model-written formula (`=SUM(`, `=B2/...`, `=$B$2`): rejected so it sends the
# computed value; other `=` text (`=1+1`, `=== x ===`) stays literal text.
_FORMULA_LIKE = re.compile(r"^=\s*(?:[A-Za-z][A-Za-z0-9.]*\s*\(|\$?[A-Za-z]{1,3}\$?\d)")
FORMULA_REJECTED = (
    "formulas are not accepted in cells: send the computed value, set `compute` "
    "on the column for a per-row calculation (add, subtract, multiply, divide, "
    "share_of_total), and set `total` on the column for sums/averages."
)
# A `"` inside a text value that closed it early: the rest of the row (and often
# the next row's start) lands in this cell, e.g. 'Loyer", 1200, null], ['.
_LEAKED_ROW = re.compile(
    r'"\s*,\s*(?:null|true|false|-?\d|")[^\]]*\](?:\s*,\s*\[|\s*\]*\s*$)'
)
LEAKED_ROW_REJECTED = (
    "this text holds other cells' JSON (values, null, brackets): a quote closed "
    "the text early and shifted the row. Resend the rows with one plain value "
    "per cell, without escaped quotes around values."
)
# Placeholder for the Excel row number in the preview's per-column formula.
ROW_PLACEHOLDER = "{row}"
COMPUTE_OPS = ("add", "subtract", "multiply", "divide", "share_of_total")
_OP_ALIASES = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide"}
_OP_SYMBOLS = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
NUMERIC_TYPES = ("number", "integer", "percent", "currency")
MAX_ROUND_DECIMALS = 10
_NUMERIC_JUNK = re.compile(r"[\s  _$€£¥]")
# "1,234" reads as 1234 in English and 1.234 in French: refuse to guess.
_AMBIGUOUS_COMMA = re.compile(r"^[+-]?\d{1,3},\d{3}$")
_LIMIT_HINT = (
    " Tell the user plainly about this limit and suggest splitting the data "
    "across several sheets or files."
)
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


class _AmbiguousNumberError(ValueError):
    pass


def _lower(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


class ComputeSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: str = Field(
        description=(
            "add, subtract, multiply or divide (left op right), or share_of_total "
            "(each value of `column` divided by that column's total)."
        )
    )
    left: str | float | None = Field(
        default=None, description="Another column's header, or a number."
    )
    right: str | float | None = Field(
        default=None, description="Another column's header, or a number."
    )
    column: str | None = Field(
        default=None, description="For share_of_total: the column's header."
    )
    round: int | None = Field(
        default=None, description="Optional: decimals to round the result to."
    )

    @field_validator("op", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return _lower(value)


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
    compute: ComputeSpec | None = Field(
        default=None,
        description=(
            "Per-row calculation from other columns, written as an Excel formula "
            "on every row; send null for this column in rows."
        ),
    )

    @field_validator("type", "total", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return _lower(value)

    @field_validator("currency", mode="before")
    @classmethod
    def _uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _computed_type_defaults_to_numeric(self) -> ColumnSpec:
        # A computed column without an explicit type is numeric, never text.
        if self.compute is not None and "type" not in self.model_fields_set:
            self.type = "percent" if self.compute.op == "share_of_total" else "number"
        return self


class SheetSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Sheet tab name, at most 31 characters.")
    columns: list[ColumnSpec] = Field(description="The sheet's columns, in order.")
    rows: list[list[CellValue]] = Field(
        default_factory=list,
        description=(
            "Data rows; each row has exactly one literal value per column (null "
            "for empty, and null for a computed column). No formulas: send "
            "computed values."
        ),
    )


class CreateSpreadsheetInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_name: str = Field(
        description="Short file name without extension, e.g. 'Q3 budget'."
    )
    sheets: list[SheetSpec] = Field(description="One or more sheets (at most 10).")
    language: str | None = Field(
        default=None,
        description=(
            "Language of the conversation, 'fr' or 'en'; sets the totals row label "
            "(Total, Moyenne... or Total, Average...). Defaults to 'fr'."
        ),
    )


@dataclass(frozen=True)
class Operand:
    column: int | None = None
    number: float = 0.0


@dataclass(frozen=True)
class ComputePlan:
    op: str
    left: Operand
    right: Operand | None
    decimals: int | None
    # Can yield "" in the file (division by zero, or an operand that can).
    may_fail: bool


@dataclass(frozen=True)
class PreparedSheet:
    name: str
    columns: list[ColumnSpec]
    headers: list[str]
    # Converted once; both the writer and the preview read these. Computed cells
    # hold the value their formula yields (None for an empty result).
    rows: list[list[Converted]]
    formats: list[str]
    computes: list[ComputePlan | None]


@dataclass(frozen=True)
class PreparedWorkbook:
    sheets: list[PreparedSheet]
    language: Language


def sanitize_file_name(raw: str) -> str:
    """Keep a safe, non-empty base name; the caller adds the extension."""

    name = raw.replace("\\", "/").split("/")[-1].strip().strip("\"'").strip()
    # `#` and `%` break the download URL path.
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"|?*#%')
    if name.lower().endswith(".xlsx"):
        name = name[:-5].rstrip()
    return name[:100].strip() or "spreadsheet"


def normalize_language(raw: str | None) -> Language:
    return "en" if (raw or "").strip().lower().startswith("en") else "fr"


def prepare(request: CreateSpreadsheetInput) -> PreparedWorkbook:
    """Validate the request and convert each value once."""

    _check_structure(request)
    return PreparedWorkbook(
        sheets=[_prepare_sheet(sheet) for sheet in request.sheets],
        language=normalize_language(request.language),
    )


def build_workbook(prepared: PreparedWorkbook) -> bytes:
    """Return the `.xlsx` bytes of a prepared request."""

    workbook = Workbook()
    for default_sheet in workbook.worksheets:
        workbook.remove(default_sheet)
    workbook.properties.creator = "Fred"
    for sheet in prepared.sheets:
        _write_sheet(workbook.create_sheet(title=sheet.name), sheet, prepared.language)
    buffer = io.BytesIO()
    workbook.save(buffer)
    data = buffer.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise SpreadsheetInputError(
            f"The workbook is too large ({len(data) // 1024} KB; the limit is "
            f"{MAX_OUTPUT_BYTES // (1024 * 1024)} MB). No file was written."
            + _LIMIT_HINT
        )
    return data


def build_preview(prepared: PreparedWorkbook) -> bytes:
    """Return the chat preview of a prepared request, as UTF-8 JSON.

    Display only: typed values, the decimals each number format shows, the first
    `MAX_PREVIEW_ROWS` rows per sheet and computed totals (the file keeps formulas).
    """

    sheets = [_preview_sheet(sheet, prepared.language) for sheet in prepared.sheets]
    payload = {"version": 1, "sheets": sheets}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _prepare_sheet(sheet: SheetSpec) -> PreparedSheet:
    headers: list[str] = []
    for index, column in enumerate(sheet.columns, start=1):
        header = _strip_illegal(column.header)
        if len(header) > MAX_CELL_CHARS:
            raise SpreadsheetInputError(
                f"Sheet '{sheet.name}', column {index}: the header has {len(header)} "
                f"characters; the limit is {MAX_CELL_CHARS}. Use a short title."
            )
        headers.append(header)
    computes = _plan_computes(sheet, headers)
    rows: list[list[Converted]] = []
    for row_number, row in enumerate(sheet.rows, start=2):
        if len(row) != len(sheet.columns):
            # Rows that leave computed columns out get their placeholders back.
            values = iter(row)
            row = [None if plan else next(values) for plan in computes]
        rows.append(
            [
                None
                if computes[index]
                else _convert(
                    raw,
                    column.type,
                    f"Sheet '{sheet.name}', row {row_number}, column {index + 1} "
                    f"('{headers[index]}')",
                )
                for index, (column, raw) in enumerate(
                    zip(sheet.columns, row, strict=True)
                )
            ]
        )
    _evaluate(computes, rows)
    formats = [
        _number_format(column, [row[index] for row in rows])
        for index, column in enumerate(sheet.columns)
    ]
    return PreparedSheet(
        name=sheet.name,
        columns=sheet.columns,
        headers=headers,
        rows=rows,
        formats=formats,
        computes=computes,
    )


def _plan_computes(sheet: SheetSpec, headers: list[str]) -> list[ComputePlan | None]:
    """Resolve each `compute` to column indexes; only earlier computed columns count."""

    plans: list[ComputePlan | None] = [None] * len(sheet.columns)
    for index, column in enumerate(sheet.columns):
        spec = column.compute
        if spec is None:
            continue
        where = f"Sheet '{sheet.name}', column {index + 1} ('{headers[index]}')"
        op = _OP_ALIASES.get(spec.op, spec.op)
        if op not in COMPUTE_OPS:
            raise SpreadsheetInputError(
                f"{where}: compute op {spec.op!r} is not supported; use add, "
                "subtract, multiply, divide or share_of_total."
            )
        if column.type not in NUMERIC_TYPES:
            raise SpreadsheetInputError(
                f"{where}: a computed column must be number, integer, percent or "
                f"currency, not '{column.type}'."
            )
        if spec.round is not None and not 0 <= spec.round <= MAX_ROUND_DECIMALS:
            raise SpreadsheetInputError(
                f"{where}: round must be between 0 and {MAX_ROUND_DECIMALS} decimals."
            )
        right: Operand | None = None
        if op == "share_of_total":
            target = spec.column if spec.column is not None else spec.left
            left = (
                _operand(target, sheet, headers, index, where)
                if target is not None
                else None
            )
            if left is None or left.column is None:
                raise SpreadsheetInputError(
                    f"{where}: share_of_total needs `column`, the header of the "
                    "column whose values are divided by its total."
                )
        else:
            if spec.left is None or spec.right is None:
                raise SpreadsheetInputError(
                    f"{where}: {op} needs `left` and `right`, each a column header "
                    "or a number."
                )
            left = _operand(spec.left, sheet, headers, index, where)
            right = _operand(spec.right, sheet, headers, index, where)
            if left.column is None and right.column is None:
                raise SpreadsheetInputError(
                    f"{where}: compute needs at least one column header; with two "
                    "numbers, send the result as a value instead."
                )
            if op == "divide" and right.column is None and right.number == 0:
                raise SpreadsheetInputError(
                    f"{where}: divide by 0 is not possible; fix `right`."
                )
        failing = [
            plans[operand.column]
            for operand in (left, right)
            if operand is not None and operand.column is not None
        ]
        plans[index] = ComputePlan(
            op=op,
            left=left,
            right=right,
            decimals=spec.round,
            may_fail=op in ("divide", "share_of_total")
            or any(plan is not None and plan.may_fail for plan in failing),
        )
    return plans


def _operand(
    raw: str | float, sheet: SheetSpec, headers: list[str], index: int, where: str
) -> Operand:
    if not isinstance(raw, str):
        if isinstance(raw, bool) or not math.isfinite(raw):
            raise SpreadsheetInputError(
                f"{where}: compute operand {raw!r} must be a column header or a "
                "finite number."
            )
        return Operand(number=float(raw))
    name = raw.strip()
    matches = [i for i, h in enumerate(headers) if h.strip() == name] or [
        i for i, h in enumerate(headers) if h.strip().casefold() == name.casefold()
    ]
    if not matches:
        try:
            if name.endswith("%"):
                return Operand(number=float(_to_number(name[:-1])) / 100)
            return Operand(number=float(_to_number(name)))
        except (TypeError, ValueError):
            known = ", ".join(f"'{h}'" for h in headers)
            raise SpreadsheetInputError(
                f"{where}: compute refers to '{raw}', which is not a column header "
                f"of this sheet. Use one of: {known}."
            ) from None
    if len(matches) > 1:
        raise SpreadsheetInputError(
            f"{where}: compute refers to '{raw}', a header used by several "
            "columns; give the columns distinct headers."
        )
    ref = matches[0]
    target = sheet.columns[ref]
    if ref == index:
        raise SpreadsheetInputError(
            f"{where}: compute refers to its own column; use other columns."
        )
    if target.compute is not None and ref > index:
        raise SpreadsheetInputError(
            f"{where}: compute refers to '{headers[ref]}', a computed column placed "
            "after it. Move this column after it, or compute from source columns."
        )
    if target.type not in NUMERIC_TYPES:
        raise SpreadsheetInputError(
            f"{where}: compute refers to '{headers[ref]}', a {target.type} column; "
            "only number, integer, percent and currency columns can be computed on."
        )
    return Operand(column=ref)


def _evaluate(plans: list[ComputePlan | None], rows: list[list[Converted]]) -> None:
    """Fill computed cells with what Excel shows: a blank source cell counts as 0,
    a division by zero (or a failed operand) is empty."""

    for index, plan in enumerate(plans):
        if plan is None:
            continue
        total = 0.0
        if plan.op == "share_of_total":
            source = cast(int, plan.left.column)
            total = math.fsum(
                float(v) for row in rows if isinstance(v := row[source], int | float)
            )
        for row in rows:
            row[index] = _apply(plan, row, plans, total)


def _apply(
    plan: ComputePlan,
    row: list[Converted],
    plans: list[ComputePlan | None],
    total: float,
) -> float | None:
    left = _operand_value(plan.left, row, plans)
    right = total if plan.right is None else _operand_value(plan.right, row, plans)
    if left is None or right is None:
        return None
    if plan.op == "add":
        result = left + right
    elif plan.op == "subtract":
        result = left - right
    elif plan.op == "multiply":
        result = left * right
    elif right == 0:
        return None
    else:
        result = left / right
    if not math.isfinite(result):
        return None
    if plan.decimals is not None:
        # Excel's ROUND rounds halves away from zero, unlike Python's round().
        step = Decimal(1).scaleb(-plan.decimals)
        result = float(Decimal(repr(result)).quantize(step, rounding=ROUND_HALF_UP))
    return result


def _operand_value(
    operand: Operand, row: list[Converted], plans: list[ComputePlan | None]
) -> float | None:
    if operand.column is None:
        return operand.number
    value = row[operand.column]
    if value is None:
        # An empty source cell is 0 in Excel; an empty computed one is "" (fails).
        return None if plans[operand.column] else 0.0
    return float(cast(int | float, value))


def _formula(plan: ComputePlan, row: int | str, last_row: int) -> str:
    def ref(operand: Operand) -> str:
        if operand.column is not None:
            return f"{get_column_letter(operand.column + 1)}{row}"
        number = operand.number
        text = str(int(number)) if number.is_integer() else repr(number).upper()
        return f"({text})" if number < 0 else text

    if plan.right is None:
        letter = get_column_letter(cast(int, plan.left.column) + 1)
        expr = f"{letter}{row}/SUM(${letter}$2:${letter}${last_row})"
    else:
        expr = f"{ref(plan.left)}{_OP_SYMBOLS[plan.op]}{ref(plan.right)}"
    if plan.decimals is not None:
        expr = f"ROUND({expr},{plan.decimals})"
    if plan.may_fail:
        expr = f'IFERROR({expr},"")'
    return "=" + expr


def _total_formula(column: ColumnSpec, index: int, last_row: int) -> str:
    letter = get_column_letter(index + 1)
    function = _TOTAL_FUNCTIONS[cast(str, column.total)]
    if column.total == "count" and column.type in ("text", "date"):
        function = "COUNTA" if column.type == "text" else "COUNT"
    return f"={function}({letter}2:{letter}{last_row})"


def _preview_sheet(sheet: PreparedSheet, language: Language) -> dict[str, object]:
    columns: list[dict[str, object]] = []
    last_row = len(sheet.rows) + 1
    for index, (column, header, fmt, plan) in enumerate(
        zip(sheet.columns, sheet.headers, sheet.formats, sheet.computes, strict=True)
    ):
        entry: dict[str, object] = {"header": header, "type": column.type}
        if column.type not in ("text", "date"):
            entry["decimals"] = _format_decimals(fmt)
        if column.currency and column.type == "currency":
            entry["currency"] = column.currency
        if column.total:
            entry["total"] = column.total
            if sheet.rows:
                entry["total_formula"] = _total_formula(column, index, last_row)
        if plan is not None:
            # One template per column; the viewer puts the row number in.
            entry["formula"] = _formula(plan, ROW_PLACEHOLDER, last_row)
        columns.append(entry)
    values = [
        [_preview_value(value) for value in row]
        for row in sheet.rows[:MAX_PREVIEW_ROWS]
    ]
    return {
        "name": sheet.name,
        "columns": columns,
        "rows": values,
        "row_count": len(sheet.rows),
        "totals": _preview_totals(sheet, language),
    }


def _preview_value(value: Converted) -> str | int | float | None:
    return value.isoformat() if isinstance(value, date) else value


def _format_decimals(fmt: str) -> int:
    if "." not in fmt:
        return 0
    tail = fmt.split(".", 1)[1]
    return len(tail) - len(tail.lstrip("0"))


def _label_index(columns: list[ColumnSpec]) -> int | None:
    return next(
        (i for i, c in enumerate(columns) if c.type == "text" and not c.total), None
    )


def _totals_label(columns: list[ColumnSpec], language: Language) -> str:
    """Name the functions the totals row applies, in column order, without repeats."""

    labels = TOTAL_LABELS[language]
    seen: list[str] = []
    for column in columns:
        if column.total and labels[column.total] not in seen:
            seen.append(labels[column.total])
    return " / ".join(seen)


def _preview_totals(
    sheet: PreparedSheet, language: Language
) -> list[str | int | float | None] | None:
    # Same placement as `_write_totals`; values mirror the Excel functions.
    columns = sheet.columns
    if not sheet.rows or not any(column.total for column in columns):
        return None
    totals: list[str | int | float | None] = [None] * len(columns)
    label_index = _label_index(columns)
    if label_index is not None:
        totals[label_index] = _totals_label(columns, language)
    for index, column in enumerate(columns):
        present = [row[index] for row in sheet.rows if row[index] is not None]
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
            f"{len(sheets)} sheets were sent; the limit is {MAX_SHEETS} sheets. "
            "No file was written." + _LIMIT_HINT
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
                f"{where} has {len(sheet.columns)} columns; the limit is "
                f"{MAX_COLUMNS} columns. No file was written." + _LIMIT_HINT
            )
        if len(sheet.rows) > MAX_ROWS:
            raise SpreadsheetInputError(
                f"{where} has {len(sheet.rows)} rows; the limit is {MAX_ROWS} rows per sheet. "
                "No data was truncated and no file was written." + _LIMIT_HINT
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
        computed = sum(1 for column in sheet.columns if column.compute is not None)
        for row_number, row in enumerate(sheet.rows, start=2):
            if len(row) not in (len(sheet.columns), len(sheet.columns) - computed):
                raise SpreadsheetInputError(
                    f"{where}, row {row_number}: expected {len(sheet.columns)} "
                    f"values (one per column), got {len(row)}. Use null for an "
                    "empty cell" + (" and for a computed column." if computed else ".")
                )
        total_cells += len(sheet.columns) * (len(sheet.rows) + 1)
    if total_cells > MAX_CELLS:
        raise SpreadsheetInputError(
            f"The workbook holds {total_cells} cells; the limit is {MAX_CELLS} cells "
            "in total. No file was written." + _LIMIT_HINT
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
    if ILLEGAL_CHARACTERS_RE.search(name):
        raise SpreadsheetInputError(
            f"Sheet name {name!r} contains control characters; use plain text."
        )
    if name.strip().lower() in _RESERVED_SHEET_NAMES:
        raise SpreadsheetInputError(
            f"Sheet name '{name}' is reserved by Excel; choose another name."
        )
    if name.lower() in seen:
        raise SpreadsheetInputError(f"Sheet name '{name}' is used twice.")
    seen.add(name.lower())


def _write_sheet(ws: Worksheet, sheet: PreparedSheet, language: Language) -> None:
    columns = sheet.columns
    widths = [len(header) for header in sheet.headers]

    for index, header in enumerate(sheet.headers, start=1):
        cell = _cell(ws, 1, index)
        _set_text(cell, header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _HEADER_BORDER

    last_row = len(sheet.rows) + 1
    for row_number, row in enumerate(sheet.rows, start=2):
        for index, value in enumerate(row):
            plan = sheet.computes[index]
            if plan is not None:
                cell = _cell(ws, row_number, index + 1)
                cell.value = _formula(plan, row_number, last_row)
                if sheet.formats[index]:
                    cell.number_format = sheet.formats[index]
                if value is not None:
                    widths[index] = max(widths[index], _display_length(value))
                continue
            if value is None:
                continue
            cell = _cell(ws, row_number, index + 1)
            if isinstance(value, str):
                _set_text(cell, value)
            else:
                cell.value = value
                if sheet.formats[index]:
                    cell.number_format = sheet.formats[index]
            widths[index] = max(widths[index], _display_length(value))

    last_column = get_column_letter(len(columns))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{last_column}{last_row}"
    if sheet.rows and any(column.total for column in columns):
        _write_totals(ws, sheet, last_row, language)

    for index, column in enumerate(columns):
        width = (
            min(max(column.width, 4), 100)
            if column.width is not None
            else min(widths[index] + 2, 60)
        )
        ws.column_dimensions[get_column_letter(index + 1)].width = width


def _write_totals(
    ws: Worksheet, sheet: PreparedSheet, last_row: int, language: Language
) -> None:
    columns = sheet.columns
    total_row = last_row + 1
    label_index = _label_index(columns)
    if label_index is not None:
        label = ws.cell(
            row=total_row,
            column=label_index + 1,
            value=_totals_label(columns, language),
        )
        label.font = _HEADER_FONT
    for index, column in enumerate(columns):
        if not column.total:
            continue
        cell = ws.cell(
            row=total_row,
            column=index + 1,
            value=_total_formula(column, index, last_row),
        )
        cell.font = _HEADER_FONT
        if column.total == "count":
            cell.number_format = NUMBER_FORMATS["integer"]
        elif column.total == "average" and column.type == "integer":
            cell.number_format = NUMBER_FORMATS["number"]
        elif sheet.formats[index]:
            cell.number_format = sheet.formats[index]


def _number_format(column: ColumnSpec, values: list[Converted]) -> str:
    if column.type == "currency" and column.currency:
        return CURRENCY_FORMATS[column.currency]
    if column.type == "percent":
        decimals = max(
            (_decimals(value * 100) for value in values if isinstance(value, float)),
            default=0,
        )
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


def _strip_illegal(text: str) -> str:
    # Control characters (often pasted from PDFs) are invalid in the xlsx XML.
    return ILLEGAL_CHARACTERS_RE.sub("", text)


def _convert(raw: CellValue, column_type: str, where: str) -> Converted:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str) and len(raw) > MAX_CELL_CHARS:
        raise SpreadsheetInputError(
            f"{where}: the value has {len(raw)} characters; the limit is {MAX_CELL_CHARS}."
        )
    if (
        isinstance(raw, str)
        and raw.lstrip().startswith("=")
        and (column_type != "text" or _FORMULA_LIKE.match(raw.strip()))
    ):
        raise SpreadsheetInputError(f"{where}: {raw!r}: {FORMULA_REJECTED}")
    if isinstance(raw, str) and _LEAKED_ROW.search(raw):
        raise SpreadsheetInputError(f"{where}: {raw!r}: {LEAKED_ROW_REJECTED}")
    try:
        if column_type == "text":
            return _strip_illegal(_to_text(raw)) or None
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
    except _AmbiguousNumberError:
        raise SpreadsheetInputError(
            f"{where}: {raw!r} is ambiguous (the comma may separate thousands or "
            "decimals). Send amounts and numbers as JSON numbers, e.g. 1234 or "
            "1.234, not as text."
        ) from None
    except (TypeError, ValueError):
        expected = {
            "date": "a date written YYYY-MM-DD",
            "percent": "a fraction like 0.15 or a string like '15%'",
            "integer": "a whole number",
        }.get(column_type, "a number (send a finite JSON number)")
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
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if not math.isfinite(raw):
            raise ValueError
        return raw
    assert raw is not None
    text = _NUMERIC_JUNK.sub("", raw)
    if _AMBIGUOUS_COMMA.match(text):
        raise _AmbiguousNumberError
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
