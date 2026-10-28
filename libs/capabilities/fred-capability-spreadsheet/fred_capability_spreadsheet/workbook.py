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
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, cast

import xlsxwriter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from fred_capability_spreadsheet.evaluator import (
    Evaluator,
    FormulaCell,
    LocatedFormulaError,
    SheetGrid,
    XLError,
    aggregate,
    from_serial,
    to_serial,
)
from fred_capability_spreadsheet.formulas import (
    Binary,
    Call,
    FormulaError,
    Group,
    Node,
    Num,
    Ref,
    SheetLayout,
    Str,
    Unary,
    check,
    column_letters,
    emit,
    fill_down,
    is_formula_like,
    parse,
    row_template,
    uses_dynamic_arrays,
)

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
# Formula results add booleans and Excel error values to the literal types.
Converted = str | int | float | bool | date | XLError | None

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
# Text a spreadsheet would follow to another program (DDE `cmd|`) or file
# (`[book.xlsx]`, a path before `!`): refused even as text (CSV re-import runs it).
_LINK_TRIGGERS = "=+-@\uff1d\uff0b\uff0d\uff20"
_LINK_TEXT = re.compile(
    r"\|[^|]*!|\[[^\]]*\][^!]*!|(?:[A-Za-z]:\\|\\\\|https?://|file:)[^!]*!",
    re.IGNORECASE,
)
LINK_TEXT_REJECTED = (
    "this text looks like a link to another program or file (DDE or an external "
    "workbook) and is not accepted, even as text. Drop the leading sign or rephrase."
)
MAX_MODEL_FORMULAS = 5_000
FORMULA_REJECTED = (
    "a formula is not accepted as a plain value: send it as a formula cell "
    '{"formula": "=..."} (or set `formula` on the column for every row), set '
    "`compute` on the column for a per-row calculation (add, subtract, multiply, "
    "divide, share_of_total), and set `total` on the column for sums/averages."
)
# A `"` inside a text value that closed it early: the rest of the row (and often
# the next row's start) lands in this cell, e.g. 'Loyer", 1200, null], ['. No `[`
# before the `]`, so 'Écran 27", 2 ports [HDMI]' stays text.
_LEAKED_ROW = re.compile(
    r'"\s*,\s*(?:null|true|false|-?\d|")[^\[\]]*\](?:\s*,\s*\[|\s*\]*\s*$)'
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
_HEADER_STYLE: dict[str, object] = {
    "bold": True,
    "bg_color": "#D9D9D9",
    "pattern": 1,
    "bottom": 1,
    "bottom_color": "#808080",
}
# Built-in numFmtId 14: Excel shows it as the reader's system short date.
_DATE_FORMAT_ID = 14
# Control characters (often pasted from PDFs) are invalid in the xlsx XML.
ILLEGAL_CHARACTERS_RE = re.compile(r"[\000-\010]|[\013-\014]|[\016-\037]")
# A string is always text: never a formula, number or link guessed from its content.
_WORKBOOK_OPTIONS: dict[str, object] = {
    "in_memory": True,
    "strings_to_formulas": False,
    "strings_to_numbers": False,
    "strings_to_urls": False,
}
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
    formula: str | None = Field(
        default=None,
        description=(
            "Excel formula of the first data row (row 2), filled down like Excel, "
            "e.g. '=XLOOKUP(A2,Prices!A2:A40,Prices!B2:B40,\"\")'; send null for "
            "this column in rows."
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
        # A computed column without an explicit type is numeric, never text; a
        # formula column's type follows its results unless it is given.
        if "type" not in self.model_fields_set:
            if self.compute is not None:
                self.type = (
                    "percent" if self.compute.op == "share_of_total" else "number"
                )
            elif self.formula is not None:
                self.type = "number"
                self.type_inferred = True
        return self

    # Set when a formula column's type was not given (it becomes text if the
    # results are text); hidden from the model.
    type_inferred: SkipJsonSchema[bool] = False


class FormulaValue(BaseModel):
    """A cell holding an Excel formula, e.g. a summary cell reading other sheets."""

    model_config = ConfigDict(extra="ignore")

    formula: str = Field(description="The Excel formula, starting with '='.")


_CHART_KEYS = frozenset({"chart", "charts", "graph", "graphs", "plot", "plots"})


def _has_chart_key(data: dict[str, object]) -> bool:
    return any(str(key).strip().lower() in _CHART_KEYS for key in data)


class SheetSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Sheet tab name, at most 31 characters.")
    columns: list[ColumnSpec] = Field(description="The sheet's columns, in order.")
    rows: list[list[CellValue | FormulaValue]] = Field(
        default_factory=list,
        description=(
            "Data rows; each row has exactly one value per column (null for "
            "empty, and null for a compute or formula column). A cell formula "
            "is an object {formula: '=...'}, never a plain string."
        ),
    )


class CreateSpreadsheetInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_name: str | None = Field(
        default=None,
        description=(
            "Short file name without extension, e.g. 'Q3 budget'. With changes, "
            "leave it out to keep the name."
        ),
    )
    sheets: list[SheetSpec] = Field(
        default_factory=list,
        description=(
            "The whole workbook: one or more sheets (at most 10). Leave it out when "
            "sending changes."
        ),
    )
    changes: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Instead of sheets: changes to the last file you created here; "
            "everything else stays as delivered. Each is {op, sheet, ...}: "
            "add_column {column, after?, values?}, remove_column {column}, "
            "edit_column {column, header?, type?, total?, compute?, formula?}, "
            "add_rows {rows, after?}, remove_rows {rows|where}, edit_rows "
            "{rows|where, values: {header: value}}, edit_cell {cell: 'C5', value}, "
            "rename_sheet {name}, add_sheet {sheet: {name, columns, rows}}, "
            "remove_sheet, move_rows {rows|where, to_sheet} (a new to_sheet is "
            "created with the same columns). column is a header; rows are row "
            "numbers as in the file (first data row = 2); where is {column, "
            "equals}. Names and numbers are those of the delivered file."
        ),
    )
    language: str | None = Field(
        default=None,
        description=(
            "Language of the conversation, 'fr' or 'en'; sets the totals row label "
            "(Total, Moyenne... or Total, Average...). Defaults to 'fr'."
        ),
    )
    # Set from the raw input, hidden from the model: charts are not supported, so
    # chart arguments are dropped and the tool tells the model to say so.
    charts_ignored: SkipJsonSchema[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _flag_chart_arguments(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw = cast(dict[str, object], data)
        sheets = raw.get("sheets")
        sheet_dicts = (
            [cast(dict[str, object], s) for s in sheets if isinstance(s, dict)]
            if isinstance(sheets, list)
            else []
        )
        if _has_chart_key(raw) or any(_has_chart_key(s) for s in sheet_dicts):
            return {**raw, "charts_ignored": True}
        return data


@dataclass(frozen=True)
class PreparedSheet:
    name: str
    columns: list[ColumnSpec]
    headers: list[str]
    # Converted once; both the writer and the preview read these. Formula cells
    # hold the value their formula yields (None for an empty result).
    rows: list[list[Converted]]
    formats: list[str]
    # Each formula column's formula at the first data row; filled down when written.
    column_formulas: list[Node | None]
    # The totals row: one formula per totals column, and its evaluated values.
    total_formulas: list[Node | None]
    totals: list[Converted] | None
    data_rows: int
    # Formula cells by (row index, column index); spills by anchor as (rows, cols).
    cell_formulas: dict[tuple[int, int], Node] = field(default_factory=dict)
    spills: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)


@dataclass
class _Draft:
    """A sheet after conversion, before its formulas are evaluated."""

    name: str
    columns: list[ColumnSpec]
    headers: list[str]
    rows: list[list[Converted]]
    column_formulas: list[Node | None]
    total_formulas: list[Node | None]
    cell_formulas: dict[tuple[int, int], Node] = field(default_factory=dict)
    # The model's formula texts, parsed once every sheet's layout is known.
    raw_column_formulas: dict[int, str] = field(default_factory=dict)
    raw_cells: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedWorkbook:
    sheets: list[PreparedSheet]
    language: Language
    # The build time TODAY/NOW were evaluated with; None when no value reads it.
    computed_at: datetime | None = None


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


def prepare(
    request: CreateSpreadsheetInput, now: datetime | None = None
) -> PreparedWorkbook:
    """Validate the request and convert each value once; `now` feeds TODAY/NOW."""

    _check_structure(request)
    language = normalize_language(request.language)
    drafts = [_prepare_sheet(sheet) for sheet in request.sheets]
    _check_model_formulas(drafts)
    evaluator = Evaluator(
        [_grid(draft, language) for draft in drafts], max_rows=MAX_ROWS + 1, now=now
    )
    sheets = _evaluate(drafts, language, evaluator)
    computed_at = evaluator.now if evaluator.clock_read else None
    return PreparedWorkbook(sheets=sheets, language=language, computed_at=computed_at)


def _check_model_formulas(drafts: list[_Draft]) -> None:
    """Parse and check the model's formulas against the whole workbook's layout."""

    layouts = [
        SheetLayout(
            d.name,
            len(d.columns),
            len(d.rows),
            any(t is not None for t in d.total_formulas),
        )
        for d in drafts
    ]
    names = [d.name for d in drafts]
    count = sum(
        len(d.rows) * len(d.raw_column_formulas) + len(d.raw_cells) for d in drafts
    )
    if count > MAX_MODEL_FORMULAS:
        raise SpreadsheetInputError(
            f"The workbook holds {count} formula cells; the limit is "
            f"{MAX_MODEL_FORMULAS}. Use `total` and `compute` where they fit, or "
            "fewer formula columns." + _LIMIT_HINT
        )
    for draft in drafts:
        for index, text in draft.raw_column_formulas.items():
            where = (
                f"Sheet '{draft.name}', column {index + 1} ('{draft.headers[index]}')"
            )
            draft.column_formulas[index] = _checked(
                text, names, layouts, draft.name, where, max(len(draft.rows) - 1, 0)
            )
        for (r, c), text in sorted(draft.raw_cells.items()):
            where = (
                f"Sheet '{draft.name}', row {r + 2}, column {c + 1} "
                f"('{draft.headers[c]}')"
            )
            draft.cell_formulas[(r, c)] = _checked(
                text, names, layouts, draft.name, where, 0
            )


def _checked(
    text: str,
    names: list[str],
    layouts: list[SheetLayout],
    here: str,
    where: str,
    fill_rows: int,
) -> Node:
    try:
        return check(parse(text, names), layouts, here, fill_rows=fill_rows)
    except FormulaError as exc:
        raise SpreadsheetInputError(
            f"{where}: formula {text.strip()!r}: {exc}."
        ) from None


def _stored_formula(formula: str, expand_future_functions: bool = False) -> str:
    del expand_future_functions
    return formula[1:] if formula.startswith("=") else formula


def build_workbook(prepared: PreparedWorkbook) -> bytes:
    """Return the `.xlsx` bytes of a prepared request."""

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, _WORKBOOK_OPTIONS)
    workbook.set_properties({"author": "Fred"})
    formats = _Formats(workbook)
    for sheet in prepared.sheets:
        worksheet = workbook.add_worksheet(sheet.name)
        # Our formulas are already in stored form (prefixes added from the AST):
        # skip XlsxWriter's regex rewrite, which costs ~30 scans per formula and
        # would also rename function names inside quoted text.
        worksheet._prepare_formula = _stored_formula
        _write_sheet(worksheet, sheet, prepared.language, formats)
    workbook.close()
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

    sheets = [_preview_sheet(sheet) for sheet in prepared.sheets]
    payload: dict[str, object] = {"version": 1, "sheets": sheets}
    if prepared.computed_at is not None:
        payload["computed_at"] = prepared.computed_at.date().isoformat()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


_HINT_MAX_NUMERIC_COLUMNS = 12
_HINT_SAMPLE_ROWS = 20
_HINT_MAX = 3


def derived_column_hints(prepared: PreparedWorkbook) -> list[str]:
    """Name literal columns whose values the model computed from other columns.

    The file is kept; the hint asks for `compute` so Excel holds a live formula.
    Bounded: few numeric columns, first rows only, the first mismatch moves on.
    """

    hints: list[str] = []
    for sheet in prepared.sheets:
        numeric = [i for i, c in enumerate(sheet.columns) if c.type in NUMERIC_TYPES]
        if len(numeric) > _HINT_MAX_NUMERIC_COLUMNS:
            continue
        for target in numeric:
            if sheet.column_formulas[target] is not None:
                continue
            found = _derivation(sheet, target, numeric)
            if found is None:
                continue
            op, left, right = found
            if right is None:
                spec = f"{{op: 'share_of_total', column: '{sheet.headers[left]}'}}"
            else:
                spec = (
                    f"{{op: '{op}', left: '{sheet.headers[left]}', "
                    f"right: '{sheet.headers[right]}'}}"
                )
            hints.append(f"'{sheet.headers[target]}' -> compute {spec}")
    return hints[:_HINT_MAX]


def _derivation(
    sheet: PreparedSheet, target: int, numeric: list[int]
) -> tuple[str, int, int | None] | None:
    sample = sheet.rows[:_HINT_SAMPLE_ROWS]
    expected = [row[target] for row in sample]
    if sum(isinstance(v, int | float) for v in expected) < 2:
        return None
    # Only columns placed before it: otherwise C = A - B also "derives" B = A - C.
    before = [i for i in numeric if i < target]
    for left in before:
        sources = [row[left] for row in sample]
        total = math.fsum(
            float(v) for row in sheet.rows if isinstance(v := row[left], int | float)
        )
        if total and _matches(
            expected, [_combine("divide", v, total) for v in sources]
        ):
            return ("share_of_total", left, None)
        for right in before:
            if right == left:
                continue
            others = [row[right] for row in sample]
            for op in ("subtract", "divide", "add", "multiply"):
                if op in ("add", "multiply") and right < left:
                    continue  # commutative: one order is enough
                values = [_combine(op, row[left], row[right]) for row in sample]
                # A copy of an operand (the other all 0 or 1) is no derivation.
                if values not in (sources, others) and _matches(expected, values):
                    return (op, left, right)
    return None


def _combine(op: str, left: Converted, right: Converted | float) -> float | None:
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        return None
    a, b = float(left), float(right)
    if op == "subtract":
        return a - b
    if op == "add":
        return a + b
    if op == "multiply":
        return a * b
    return a / b if b else None


def _matches(expected: list[Converted], values: list[float | None]) -> bool:
    """Every literal equals the computed value up to the literal's own rounding."""

    for literal, value in zip(expected, values, strict=True):
        if literal is None:
            continue
        if not isinstance(literal, int | float) or value is None:
            return False
        number = float(literal)
        places = 0 if number.is_integer() else _decimals(number)
        tolerance = 0.5 * 10**-places if places else 1e-9 * max(1.0, abs(value))
        if abs(number - value) > tolerance + 1e-12:
            return False
    return True


_TOTAL_LABELS = frozenset(
    (
        "total",
        "totaux",
        "total général",
        "total general",
        "grand total",
        "sum",
        "somme",
        "sous-total",
        "sous total",
        "subtotal",
        "sub-total",
    )
)


def manual_total_hints(prepared: PreparedWorkbook) -> list[str]:
    """Name, once per sheet, a data row that repeats the automatic totals row.

    The file is kept (a company may be called "Total"): the row counts only when
    its total-column cells are all empty or equal what the totals row computes.
    """

    hints: list[str] = []
    for sheet in prepared.sheets:
        kept = [
            i for i, c in enumerate(sheet.columns) if c.total and c.total != "count"
        ]
        if not any(column.total for column in sheet.columns):
            continue
        labelled = [
            (i, label)
            for i, row in enumerate(sheet.rows)
            if (label := _total_label(row))
        ]
        if not labelled:
            continue
        skip = {i for i, _ in labelled}
        others = [r for i, r in enumerate(sheet.rows) if i not in skip]
        expected = {
            i: aggregate(
                cast(str, sheet.columns[i].total), [_scalar(r[i]) for r in others]
            )
            for i in kept
        }
        for index, label in labelled:
            cells = [sheet.rows[index][i] for i in kept]
            if all(v is None for v in cells) or _matches(
                cells, [_number(expected[i]) for i in kept]
            ):
                hints.append(f"sheet '{sheet.name}', row {index + 2} ('{label}')")
                break
    return hints


def _total_label(row: list[Converted]) -> str | None:
    label = next((v for v in row if isinstance(v, str)), None)
    if label is None:
        return None
    key = " ".join(label.lower().split()).rstrip(" :")
    # "Total HT" counts, "TotalEnergies" does not.
    if key in _TOTAL_LABELS or key.split(" ", 1)[0] in _TOTAL_LABELS:
        return label.strip()
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None


def _scalar(value: Converted) -> float | str | bool | XLError | None:
    """A converted value as the evaluator reads it (dates as serial numbers)."""

    if isinstance(value, date):
        return to_serial(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _prepare_sheet(sheet: SheetSpec) -> _Draft:
    headers: list[str] = []
    for index, column in enumerate(sheet.columns, start=1):
        header = _strip_illegal(column.header)
        if links_out(header):
            raise SpreadsheetInputError(
                f"Sheet '{sheet.name}', column {index}: {header!r}: {LINK_TEXT_REJECTED}"
            )
        if len(header) > MAX_CELL_CHARS:
            raise SpreadsheetInputError(
                f"Sheet '{sheet.name}', column {index}: the header has {len(header)} "
                f"characters; the limit is {MAX_CELL_CHARS}. Use a short title."
            )
        headers.append(header)
    last_row = len(sheet.rows) + 1
    raw_column_formulas: dict[int, str] = {}
    for index, column in enumerate(sheet.columns):
        if column.formula is None:
            continue
        if column.compute is not None:
            raise SpreadsheetInputError(
                f"Sheet '{sheet.name}', column {index + 1} ('{headers[index]}'): set "
                "either `compute` or `formula` on a column, not both."
            )
        raw_column_formulas[index] = column.formula
    column_formulas = _compile_computes(sheet, headers, last_row)
    placeholder = [
        node is not None or index in raw_column_formulas
        for index, node in enumerate(column_formulas)
    ]
    raw_cells: dict[tuple[int, int], str] = {}
    rows: list[list[Converted]] = []
    for r, row in enumerate(sheet.rows):
        if len(row) != len(sheet.columns):
            # Rows that leave computed columns out get their placeholders back.
            values = iter(row)
            row = [None if hole else next(values) for hole in placeholder]
        converted: list[Converted] = []
        for index, (column, raw) in enumerate(zip(sheet.columns, row, strict=True)):
            if placeholder[index]:
                converted.append(None)
            elif isinstance(raw, FormulaValue):
                raw_cells[(r, index)] = raw.formula
                converted.append(None)
            else:
                converted.append(
                    _convert(
                        raw,
                        column.type,
                        f"Sheet '{sheet.name}', row {r + 2}, column {index + 1} "
                        f"('{headers[index]}')",
                    )
                )
        rows.append(converted)
    total_formulas: list[Node | None] = [
        _total_node(column, index, last_row) if column.total and sheet.rows else None
        for index, column in enumerate(sheet.columns)
    ]
    return _Draft(
        name=sheet.name,
        columns=sheet.columns,
        headers=headers,
        rows=rows,
        column_formulas=column_formulas,
        total_formulas=total_formulas,
        raw_column_formulas=raw_column_formulas,
        raw_cells=raw_cells,
    )


def _compile_computes(
    sheet: SheetSpec, headers: list[str], last_row: int
) -> list[Node | None]:
    """Each `compute` as the formula of its first data row; only earlier computed
    columns may be referenced, so there is no cycle."""

    nodes: list[Node | None] = [None] * len(sheet.columns)
    # A model formula can give "" (IFERROR), so computing on it can fail.
    may_fail = [column.formula is not None for column in sheet.columns]
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
        if op == "share_of_total":
            target = spec.column if spec.column is not None else spec.left
            left = (
                _operand(target, sheet, headers, index, where)
                if target is not None
                else None
            )
            if left is None or isinstance(left, float):
                raise SpreadsheetInputError(
                    f"{where}: share_of_total needs `column`, the header of the "
                    "column whose values are divided by its total."
                )
            whole = Ref(
                None, left + 1, 2, left + 1, last_row, True, True, True, True, True
            )
            expr: Node = Binary("/", _cell_ref(left), Call("SUM", (whole,)))
            failing = True
        else:
            if spec.left is None or spec.right is None:
                raise SpreadsheetInputError(
                    f"{where}: {op} needs `left` and `right`, each a column header "
                    "or a number."
                )
            left = _operand(spec.left, sheet, headers, index, where)
            right = _operand(spec.right, sheet, headers, index, where)
            if isinstance(left, float) and isinstance(right, float):
                raise SpreadsheetInputError(
                    f"{where}: compute needs at least one column header; with two "
                    "numbers, send the result as a value instead."
                )
            if op == "divide" and isinstance(right, float) and right == 0:
                raise SpreadsheetInputError(
                    f"{where}: divide by 0 is not possible; fix `right`."
                )
            expr = Binary(_OP_SYMBOLS[op], _operand_node(left), _operand_node(right))
            failing = op == "divide" or any(
                not isinstance(x, float) and may_fail[x] for x in (left, right)
            )
        if spec.round is not None:
            expr = Call("ROUND", (expr, Num(float(spec.round))))
        if failing:
            # An empty result would otherwise give #VALUE! in later formulas.
            expr = Call("IFERROR", (expr, Str("")))
        nodes[index] = expr
        may_fail[index] = failing
    return nodes


def _cell_ref(index: int) -> Ref:
    return Ref(None, index + 1, 2, index + 1, 2)


def _operand_node(operand: int | float) -> Node:
    if isinstance(operand, float):
        if operand < 0:
            return Group(Unary("-", Num(-operand)))
        return Num(operand)
    return _cell_ref(operand)


def _operand(
    raw: str | float, sheet: SheetSpec, headers: list[str], index: int, where: str
) -> int | float:
    """A column index, or a number (always a float)."""

    if not isinstance(raw, str):
        if isinstance(raw, bool) or not math.isfinite(raw):
            raise SpreadsheetInputError(
                f"{where}: compute operand {raw!r} must be a column header or a "
                "finite number."
            )
        return float(raw)
    name = raw.strip()
    matches = [i for i, h in enumerate(headers) if h.strip() == name] or [
        i for i, h in enumerate(headers) if h.strip().casefold() == name.casefold()
    ]
    if not matches:
        try:
            if name.endswith("%"):
                return float(_to_number(name[:-1])) / 100
            return float(_to_number(name))
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
    return ref


def _total_node(column: ColumnSpec, index: int, last_row: int) -> Node:
    function = _TOTAL_FUNCTIONS[cast(str, column.total)]
    if column.total == "count" and column.type in ("text", "date"):
        function = "COUNTA" if column.type == "text" else "COUNT"
    data = Ref(None, index + 1, 2, index + 1, last_row, is_range=True)
    return Call(function, (data,))


def _evaluate(
    drafts: list[_Draft], language: Language, evaluator: Evaluator
) -> list[PreparedSheet]:
    """Evaluate every formula of the workbook once, across sheets."""

    try:
        evaluator.run()
    except LocatedFormulaError as exc:
        hint = _LIMIT_HINT if exc.budget else ""
        raise SpreadsheetInputError(f"{exc}.{hint}") from None
    except FormulaError as exc:  # raised outside any cell
        raise SpreadsheetInputError(str(exc)) from None
    results = evaluator.results
    sheets: list[PreparedSheet] = []
    for draft in drafts:
        rows = [list(row) for row in draft.rows]
        for (name, r, c), value in evaluator.spilled().items():
            if name != draft.name:
                continue
            while len(rows) < r - 1:
                rows.append([None] * len(draft.columns))
            rows[r - 2][c - 1] = _from_result(value, draft.columns[c - 1].type)
        for index, node in enumerate(draft.column_formulas):
            if node is None:
                continue
            kind = draft.columns[index].type
            for r in range(len(draft.rows)):
                rows[r][index] = _from_result(
                    results[(draft.name, r + 2, index + 1)], kind
                )
        for r, c in draft.cell_formulas:
            rows[r][c] = _from_result(
                results[(draft.name, r + 2, c + 1)], draft.columns[c].type
            )
        totals = _totals_values(draft, results, language)
        columns = [
            column.model_copy(update={"type": "text"})
            if column.type_inferred
            and any(isinstance(row[i], str) for row in rows[: len(draft.rows)])
            else column
            for i, column in enumerate(draft.columns)
        ]
        sheets.append(
            PreparedSheet(
                name=draft.name,
                columns=columns,
                headers=draft.headers,
                rows=rows,
                formats=[
                    _number_format(column, [row[i] for row in rows])
                    for i, column in enumerate(columns)
                ],
                column_formulas=draft.column_formulas,
                total_formulas=draft.total_formulas,
                totals=totals,
                data_rows=len(draft.rows),
                cell_formulas=draft.cell_formulas,
                spills={
                    (r - 2, c - 1): (spill.height, spill.width)
                    for (name, r, c), spill in evaluator.spills.items()
                    if name == draft.name
                },
            )
        )
    return sheets


def _grid(draft: _Draft, language: Language) -> SheetGrid:
    has_totals = any(node is not None for node in draft.total_formulas)
    last_data_row = len(draft.rows) + 1
    grid = SheetGrid(
        draft.name,
        len(draft.columns),
        spill_limit=last_data_row if has_totals else MAX_ROWS + 1,
    )
    for c, header in enumerate(draft.headers, start=1):
        grid.values[(1, c)] = header
    for r, row in enumerate(draft.rows, start=2):
        for c, value in enumerate(row, start=1):
            if value is not None:
                grid.values[(r, c)] = _scalar(value)
    for c, node in enumerate(draft.column_formulas, start=1):
        if node is not None:
            for r in range(len(draft.rows)):
                grid.formulas[(r + 2, c)] = FormulaCell(node, rows=r)
    for (r, c), node in draft.cell_formulas.items():
        grid.formulas[(r + 2, c + 1)] = FormulaCell(node, may_spill=True)
    if has_totals:
        totals_row = last_data_row + 1
        label_index = _label_index(draft.columns)
        if label_index is not None:
            grid.values[(totals_row, label_index + 1)] = _totals_label(
                draft.columns, language
            )
        for c, node in enumerate(draft.total_formulas, start=1):
            if node is not None:
                grid.formulas[(totals_row, c)] = FormulaCell(node)
    return grid


def _from_result(value: object, column_type: str) -> Converted:
    """An evaluated value as the writer and preview read it."""

    if value is None or value == "":
        return None
    if (
        column_type == "date"
        and isinstance(value, float)
        and not isinstance(value, bool)
    ):
        try:
            return from_serial(value)
        except Exception:  # an out-of-range serial stays a number
            return value
    return cast(Converted, value)


def _totals_values(
    draft: _Draft, results: Mapping[tuple[str, int, int], object], language: Language
) -> list[Converted] | None:
    if not any(node is not None for node in draft.total_formulas):
        return None
    totals_row = len(draft.rows) + 2
    totals: list[Converted] = [None] * len(draft.columns)
    label_index = _label_index(draft.columns)
    if label_index is not None:
        totals[label_index] = _totals_label(draft.columns, language)
    for index, node in enumerate(draft.total_formulas):
        if node is not None:
            value = results[(draft.name, totals_row, index + 1)]
            totals[index] = None if value == "" else cast(Converted, value)
    return totals


def _preview_sheet(sheet: PreparedSheet) -> dict[str, object]:
    columns: list[dict[str, object]] = []
    for column, header, fmt, node, total in zip(
        sheet.columns,
        sheet.headers,
        sheet.formats,
        sheet.column_formulas,
        sheet.total_formulas,
        strict=True,
    ):
        entry: dict[str, object] = {"header": header, "type": column.type}
        if column.type not in ("text", "date"):
            entry["decimals"] = _format_decimals(fmt)
        if column.currency and column.type == "currency":
            entry["currency"] = column.currency
        if column.total:
            entry["total"] = column.total
            if total is not None:
                entry["total_formula"] = emit(total)
        if node is not None and (template := row_template(node, ROW_PLACEHOLDER)):
            # One template per column; the viewer puts the row number in.
            entry["formula"] = template
        columns.append(entry)
    shown = min(len(sheet.rows), MAX_PREVIEW_ROWS)
    payload: dict[str, object] = {
        "name": sheet.name,
        "columns": columns,
        "rows": [[_preview_value(v) for v in row] for row in sheet.rows[:shown]],
        "row_count": len(sheet.rows),
        "totals": None
        if sheet.totals is None
        else [_preview_value(v) for v in sheet.totals],
    }
    cell_formulas = _preview_cell_formulas(sheet, shown)
    if cell_formulas:
        payload["cell_formulas"] = cell_formulas
    return payload


def _preview_cell_formulas(sheet: PreparedSheet, shown: int) -> dict[str, str]:
    """Formula-bar text for cells no column template covers, by A1 address."""

    out: dict[str, str] = {}
    for (r, c), node in sorted(sheet.cell_formulas.items()):
        if r < shown:
            out[f"{column_letters(c + 1)}{r + 2}"] = emit(node)
    for c, node in enumerate(sheet.column_formulas):
        if node is not None and row_template(node, ROW_PLACEHOLDER) is None:
            for r in range(min(shown, sheet.data_rows)):
                out[f"{column_letters(c + 1)}{r + 2}"] = emit(node, rows=r)
    return out


def _preview_value(value: Converted) -> str | int | float | None:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, XLError):
        return value.code
    return value


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
        computed = sum(
            1
            for column in sheet.columns
            if column.compute is not None or column.formula is not None
        )
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
    if links_out(name):
        raise SpreadsheetInputError(f"Sheet name {name!r}: {LINK_TEXT_REJECTED}")
    if name.strip().lower() in _RESERVED_SHEET_NAMES:
        raise SpreadsheetInputError(
            f"Sheet name '{name}' is reserved by Excel; choose another name."
        )
    if name.lower() in seen:
        raise SpreadsheetInputError(f"Sheet name '{name}' is used twice.")
    seen.add(name.lower())


class _Formats:
    """One XlsxWriter format per distinct style, created on first use."""

    def __init__(self, workbook: Any) -> None:
        self._workbook = workbook
        self._cache: dict[tuple[object, ...], Any] = {}

    def get(
        self, number_format: str = "", *, bold: bool = False, quote: bool = False
    ) -> Any:
        key = (number_format, bold, quote)
        if key not in self._cache:
            props: dict[str, object] = {}
            if number_format:
                props["num_format"] = (
                    _DATE_FORMAT_ID
                    if number_format == NUMBER_FORMATS["date"]
                    else number_format
                )
            if bold:
                props["bold"] = True
            if quote:
                props["quote_prefix"] = True
            self._cache[key] = self._workbook.add_format(props) if props else None
        return self._cache[key]

    def header(self, quote: bool) -> Any:
        key: tuple[object, ...] = ("header", quote)
        if key not in self._cache:
            self._cache[key] = self._workbook.add_format(
                {**_HEADER_STYLE, **({"quote_prefix": True} if quote else {})}
            )
        return self._cache[key]


def _write_sheet(
    ws: Any, sheet: PreparedSheet, language: Language, formats: _Formats
) -> None:
    columns = sheet.columns
    widths = [len(header) for header in sheet.headers]

    for index, header in enumerate(sheet.headers):
        ws.write_string(0, index, header, formats.header(_is_trigger(header)))

    fills = [
        None if node is None else fill_down(node, stored=True)
        for node in sheet.column_formulas
    ]
    for r, row in enumerate(sheet.rows):
        for index, value in enumerate(row):
            fmt = formats.get(sheet.formats[index])
            fill = fills[index] if r < sheet.data_rows else None
            cell = sheet.cell_formulas.get((r, index))
            if fill is not None:
                ws.write_formula(r + 1, index, fill(r), fmt, _cached(value))
            elif cell is not None:
                _write_cell_formula(ws, sheet, r, index, cell, value, fmt)
            elif value is not None:
                _write_value(ws, r + 1, index, value, sheet.formats[index], formats)
            if value is not None:
                widths[index] = max(widths[index], _display_length(value))

    last_row = len(sheet.rows) + 1
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, last_row - 1, len(columns) - 1)
    if sheet.totals is not None:
        _write_totals(ws, sheet, last_row, language, formats)

    for index, column in enumerate(columns):
        width = (
            min(max(column.width, 4), 100)
            if column.width is not None
            else min(widths[index] + 2, 60)
        )
        ws.set_column(index, index, width)


def _write_cell_formula(
    ws: Any,
    sheet: PreparedSheet,
    r: int,
    c: int,
    node: Node,
    value: Converted,
    fmt: Any,
) -> None:
    text = emit(node, stored=True)
    spill = sheet.spills.get((r, c))
    if spill is None and not uses_dynamic_arrays(node):
        ws.write_formula(r + 1, c, text, fmt, _cached(value))
        return
    height, width = spill or (1, 1)
    # Spill metadata, so Excel does not show a legacy `@` array formula.
    ws.write_dynamic_array_formula(
        r + 1, c, r + height, c + width - 1, text, fmt, _cached(value)
    )


def _cached(value: Converted) -> object:
    if value is None:
        return ""
    if isinstance(value, XLError):
        return value.code
    if isinstance(value, date):
        return to_serial(value)
    return value


def _write_value(
    ws: Any, row: int, column: int, value: Converted, fmt: str, formats: _Formats
) -> None:
    if isinstance(value, str):
        ws.write_string(row, column, value, formats.get(quote=_is_trigger(value)))
    elif isinstance(value, bool):
        ws.write_boolean(row, column, value)
    elif isinstance(value, XLError):
        ws.write_string(row, column, value.code)
    elif isinstance(value, date):
        ws.write_datetime(row, column, value, formats.get(fmt))
    elif value is not None:
        ws.write_number(row, column, value, formats.get(fmt))


def _write_totals(
    ws: Any, sheet: PreparedSheet, last_row: int, language: Language, formats: _Formats
) -> None:
    columns = sheet.columns
    row = last_row  # 0-based index of the row after the data
    label_index = _label_index(columns)
    if label_index is not None:
        ws.write_string(
            row, label_index, _totals_label(columns, language), formats.get(bold=True)
        )
    values = sheet.totals or [None] * len(columns)
    for index, column in enumerate(columns):
        node = sheet.total_formulas[index]
        if node is None:
            continue
        if column.total == "count":
            fmt = NUMBER_FORMATS["integer"]
        elif column.total == "average" and column.type == "integer":
            fmt = NUMBER_FORMATS["number"]
        else:
            fmt = sheet.formats[index]
        ws.write_formula(
            row,
            index,
            emit(node, stored=True),
            formats.get(fmt, bold=True),
            _cached(values[index]),
        )


def _number_format(column: ColumnSpec, values: list[Converted]) -> str:
    decimals = column.compute.round if column.compute is not None else None
    if column.type == "number" and decimals is not None:
        # Show the decimals `round` keeps, not the default two.
        return "#,##0" + ("." + "0" * decimals if decimals else "")
    if column.type == "currency" and column.currency:
        return CURRENCY_FORMATS[column.currency]
    if column.type == "percent":
        decimals = max(
            (
                _decimals(value * 100)
                for value in values
                if isinstance(value, float) and math.isfinite(value)
            ),
            default=0,
        )
        return "0%" if decimals == 0 else "0." + "0" * min(decimals, 2) + "%"
    return NUMBER_FORMATS.get(column.type, "")


def _decimals(value: float) -> int:
    text = f"{round(value, 6):.6f}".rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0


def _is_trigger(value: str) -> bool:
    # Stored as a literal string; the quote prefix keeps it text when edited.
    return value.startswith(_FORMULA_TRIGGERS)


def _display_length(value: object) -> int:
    if isinstance(value, bool):
        return 5
    if isinstance(value, XLError):
        return len(value.code)
    if isinstance(value, int | float):
        # Two decimals plus room for a currency symbol or a percent sign.
        return len(f"{value:,.2f}") + 3
    if isinstance(value, date):
        return 10
    return max((len(line) for line in str(value).splitlines()), default=0)


def links_out(text: str) -> bool:
    stripped = text.lstrip()
    return (
        bool(stripped)
        and stripped[0] in _LINK_TRIGGERS
        and bool(_LINK_TEXT.search(stripped))
    )


def _strip_illegal(text: str) -> str:
    return ILLEGAL_CHARACTERS_RE.sub("", text)


def _convert(raw: CellValue, column_type: str, where: str) -> Converted:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str) and len(raw) > MAX_CELL_CHARS:
        raise SpreadsheetInputError(
            f"{where}: the value has {len(raw)} characters; the limit is {MAX_CELL_CHARS}."
        )
    if isinstance(raw, str) and links_out(raw):
        raise SpreadsheetInputError(f"{where}: {raw!r}: {LINK_TEXT_REJECTED}")
    if (
        isinstance(raw, str)
        and raw.lstrip().startswith("=")
        and (column_type != "text" or is_formula_like(raw.strip()))
    ):
        cell = json.dumps({"formula": raw.strip()}, ensure_ascii=False)
        raise SpreadsheetInputError(
            f"{where}: {raw!r}: {FORMULA_REJECTED} For this cell: {cell}."
        )
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
