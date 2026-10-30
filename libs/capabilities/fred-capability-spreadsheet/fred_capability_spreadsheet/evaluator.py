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

"""Evaluate the allow-listed Excel functions with Excel's semantics.

The results become the formulas' cached values and the preview's cells. Pure
Python, bounded by a cell-read budget; ranges are materialized once and lookups
use per-range indexes, so a column of SUMIFs stays linear (design.md D15).
"""

from __future__ import annotations

import bisect
import calendar
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    ROUND_UP,
    Context,
    Decimal,
)
from typing import cast

from fred_capability_spreadsheet.formulas import (
    Binary,
    Bool,
    Call,
    Err,
    FormulaError,
    Group,
    Missing,
    Name,
    Node,
    Num,
    Percent,
    Ref,
    Str,
    Unary,
    column_letters,
)

MAX_CELL_READS = 2_000_000
# Formulas waiting on later formulas (a reversed running total) nest the evaluation.
MAX_CHAIN = 64
# Newton steps of IRR and RATE; each step is charged to the cell-read budget.
MAX_SOLVER_ITERATIONS = 50
_ROUND_CONTEXT = Context(prec=400)
_EPOCH = date(1899, 12, 30)
_MAX_SERIAL = 2_958_465  # 9999-12-31


@dataclass(frozen=True, slots=True)
class XLError:
    code: str


DIV0 = XLError("#DIV/0!")
NA = XLError("#N/A")
VALUE = XLError("#VALUE!")
REF = XLError("#REF!")
NUM = XLError("#NUM!")
CALC = XLError("#CALC!")

Scalar = float | str | bool | XLError | None


@dataclass(slots=True)
class Array:
    rows: list[list[Scalar]]
    # Set for a materialized range: its key makes calls over it memoizable.
    key: tuple[object, ...] | None = None

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def flat(self) -> list[Scalar]:
        return [v for row in self.rows for v in row]


Value = Scalar | Array


class BudgetExceededError(FormulaError):
    pass


class LocatedFormulaError(FormulaError):
    """An evaluation error prefixed with the sheet and cell it happened in."""

    def __init__(self, message: str, *, budget: bool = False) -> None:
        super().__init__(message)
        self.budget = budget


class _Raise(Exception):
    def __init__(self, error: XLError) -> None:
        self.error = error


@dataclass(slots=True)
class FormulaCell:
    node: Node
    # Rows a column formula is filled down by (0 for the first data row).
    rows: int = 0
    # A cell formula may spill an array; a column formula must give one value.
    may_spill: bool = False


@dataclass(slots=True)
class SheetGrid:
    name: str
    columns: int
    # Last row a spill may reach (the row above a totals row, or the row limit).
    spill_limit: int = 0
    values: dict[tuple[int, int], Scalar] = field(default_factory=dict)
    formulas: dict[tuple[int, int], FormulaCell] = field(default_factory=dict)


@dataclass(slots=True)
class Spill:
    height: int
    width: int


class Evaluator:
    """Evaluates every formula of a workbook; results keyed by (sheet, row, col)."""

    def __init__(
        self,
        sheets: Sequence[SheetGrid],
        max_rows: int,
        now: datetime | None = None,
    ) -> None:
        # TODAY and NOW read one frozen build time, so every cell agrees.
        self.now = now
        self.clock_read = False
        self._env: list[dict[str, Value]] = []
        self._sorted: dict[tuple[object, ...], list[float]] = {}
        self.sheets = {s.name.casefold(): s for s in sheets}
        self.order = list(sheets)
        self.max_rows = max_rows
        self.results: dict[tuple[str, int, int], Scalar] = {}
        self.spills: dict[tuple[str, int, int], Spill] = {}
        self._spilled: dict[tuple[str, int, int], Scalar] = {}
        self._active: set[tuple[str, int, int]] = set()
        self._stack: list[tuple[str, int, int]] = []
        self._ranges: dict[tuple[object, ...], Array] = {}
        self._memo: dict[tuple[object, ...], Value] = {}
        self._indexes: dict[tuple[object, ...], dict[object, list[int]]] = {}
        self.reads = 0

    # -- driving ---------------------------------------------------------------

    def run(self) -> None:
        # Spilling formulas first, so formulas reading their cells see them.
        for sheet in self.order:
            for (row, col), cell in sorted(sheet.formulas.items()):
                if cell.may_spill:
                    self.cell_value(sheet, row, col)
        for sheet in self.order:
            for row, col in sorted(sheet.formulas):
                self.cell_value(sheet, row, col)

    def charge(self, cells: int) -> None:
        self.reads += cells
        if self.reads > MAX_CELL_READS:
            raise BudgetExceededError(
                "the formulas read too many cells to compute (more than "
                f"{MAX_CELL_READS:,} cell reads); use `total` on columns, fewer "
                "lookups or smaller ranges, and for a running total add the row "
                "above (=C1+B2) instead of summing from the top"
            )

    def cell_value(self, sheet: SheetGrid, row: int, col: int) -> Scalar:
        key = (sheet.name, row, col)
        if key in self.results:
            return self.results[key]
        cell = sheet.formulas.get((row, col))
        if cell is None:
            if key in self._spilled:
                return self._spilled[key]
            return sheet.values.get((row, col))
        if key in self._active:
            raise FormulaError(
                f"this formula depends on its own result "
                f"(circular reference through {column_letters(col)}{row}); "
                "remove the loop"
            )
        if len(self._stack) >= MAX_CHAIN:
            raise FormulaError(
                f"formulas wait on later formulas more than {MAX_CHAIN} levels deep "
                "; compute in the other direction (each row "
                "from the rows above it)"
            )
        self._active.add(key)
        self._stack.append(key)
        # LET names are local to the formula being evaluated.
        outer_env, self._env = self._env, []
        try:
            value = self.evaluate(cell.node, sheet, cell.rows, top=True)
            result = self._place(sheet, row, col, cell, value)
        except LocatedFormulaError:
            raise
        except FormulaError as exc:
            raise LocatedFormulaError(
                f"Sheet '{sheet.name}', cell {column_letters(col)}{row}: {exc}",
                budget=isinstance(exc, BudgetExceededError),
            ) from None
        finally:
            self._env = outer_env
            self._active.discard(key)
            self._stack.pop()
        self.results[key] = result
        return result

    def _place(
        self, sheet: SheetGrid, row: int, col: int, cell: FormulaCell, value: Value
    ) -> Scalar:
        if not isinstance(value, Array):
            return 0.0 if value is None else value
        if value.height * value.width == 1:
            first = value.rows[0][0]
            return 0.0 if first is None else first
        if not cell.may_spill:
            raise FormulaError(
                f"this formula gives {value.height}x{value.width} "
                "values; a column formula must give one value per row (wrap the "
                "range in SUM, INDEX or XLOOKUP)"
            )
        if value.height == 0 or value.width == 0:
            return CALC
        last_row, last_col = row + value.height - 1, col + value.width - 1
        if last_col > sheet.columns or last_row > (sheet.spill_limit or self.max_rows):
            raise FormulaError(
                f"this formula spills {value.height} rows x "
                f"{value.width} columns, past the sheet's columns (A to "
                f"{column_letters(sheet.columns)}) or into the totals row or the row "
                "limit; move it or "
                "narrow the result"
            )
        for r in range(row, last_row + 1):
            for c in range(col, last_col + 1):
                if (r, c) == (row, col):
                    continue
                if (r, c) in sheet.formulas or sheet.values.get((r, c)) is not None:
                    raise FormulaError(
                        f"this formula spills {value.height} rows x "
                        f"{value.width} columns, but {column_letters(c)}{r} is not "
                        "empty; leave the spill area empty or move the formula"
                    )
                # An empty source cell shows as 0 in a spilled array, as in Excel.
                spilled = value.rows[r - row][c - col]
                self._spilled[(sheet.name, r, c)] = 0.0 if spilled is None else spilled
        self.spills[(sheet.name, row, col)] = Spill(value.height, value.width)
        first = value.rows[0][0]
        return 0.0 if first is None else first

    def spilled(self) -> dict[tuple[str, int, int], Scalar]:
        return self._spilled

    # -- expressions -----------------------------------------------------------

    def evaluate(
        self, node: Node, sheet: SheetGrid, rows: int, *, top: bool = False
    ) -> Value:
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Str):
            return node.value
        if isinstance(node, Bool):
            return node.value
        if isinstance(node, Err):
            return XLError(node.code)
        if isinstance(node, Missing):
            return None
        if isinstance(node, Ref):
            return self.reference(node, sheet, rows, as_array=False)
        if isinstance(node, Name):
            value = self.bound(node)
            # A name bound to one cell reads as that cell's value.
            if isinstance(value, Array) and value.key is not None:
                if value.height * value.width == 1:
                    return value.rows[0][0]
            return value
        if isinstance(node, Group):
            return self.evaluate(node.inner, sheet, rows)
        if isinstance(node, Unary):
            operand = self.evaluate(node.operand, sheet, rows)
            if node.op == "+":
                return operand
            return _lift1(operand, lambda v: -_num(v))
        if isinstance(node, Percent):
            return _lift1(
                self.evaluate(node.operand, sheet, rows), lambda v: _num(v) / 100
            )
        if isinstance(node, Binary):
            left = self.evaluate(node.left, sheet, rows)
            right = self.evaluate(node.right, sheet, rows)
            return _lift2(left, right, _BINARY[node.op])
        assert isinstance(node, Call)
        return self.call(node, sheet, rows)

    def reference(
        self, ref: Ref, sheet: SheetGrid, rows: int, *, as_array: bool
    ) -> Value:
        target = self.sheets[(ref.sheet or sheet.name).casefold()]
        r1 = ref.r1 if ref.abs_r1 else ref.r1 + rows
        r2 = ref.r2 if ref.abs_r2 else ref.r2 + rows
        if not ref.is_range and not as_array:
            self.charge(1)
            return self.cell_value(target, r1, ref.c1)
        key = (target.name, r1, ref.c1, r2, ref.c2)
        cached = self._ranges.get(key)
        if cached is None:
            self.charge((r2 - r1 + 1) * (ref.c2 - ref.c1 + 1))
            cached = Array(
                [
                    [self.cell_value(target, r, c) for c in range(ref.c1, ref.c2 + 1)]
                    for r in range(r1, r2 + 1)
                ],
                key=key,
            )
            self._ranges[key] = cached
        return cached

    def arg(self, node: Node, sheet: SheetGrid, rows: int) -> Value:
        # A reference passed to a function stays a reference (an array), as in
        # Excel: SUM(A1) ignores text in A1, SUM("x") does not.
        if isinstance(node, Ref):
            return self.reference(node, sheet, rows, as_array=True)
        if isinstance(node, Name):
            return self.bound(node)
        return self.evaluate(node, sheet, rows)

    def bound(self, node: Name) -> Value:
        for scope in reversed(self._env):
            if node.name in scope:
                return scope[node.name]
        raise FormulaError(f"'{node.name.lower()}' is not defined by a LET")

    def clock(self) -> datetime:
        self.clock_read = True
        if self.now is None:
            self.now = datetime.now().astimezone()
        return self.now

    def sorted_numbers(self, value: Value) -> list[float]:
        """The numbers of a range, sorted once per range (RANK, LARGE...)."""

        if not isinstance(value, Array):
            return [_num(value)]
        cached = self._sorted.get(value.key) if value.key is not None else None
        if cached is None:
            self.charge(value.height * value.width)
            cached = sorted(_numbers([value]))
            if value.key is not None:
                self._sorted[value.key] = cached
        self.charge(1)
        return cached

    def call(self, node: Call, sheet: SheetGrid, rows: int) -> Value:
        lazy = _LAZY.get(node.name)
        if lazy is not None:
            try:
                return lazy(self, node.args, sheet, rows)
            except _Raise as exc:
                return exc.error
        args = [self.arg(a, sheet, rows) for a in node.args]
        memo_key = _memo_key(node.name, args)
        if memo_key is not None and memo_key in self._memo:
            return self._memo[memo_key]
        if node.name not in _SELF_CHARGING:
            self.charge(sum(a.height * a.width for a in args if isinstance(a, Array)))
        try:
            result = _FUNCTIONS[node.name](self, args)
        except _Raise as exc:
            result = exc.error
        if memo_key is not None:
            self._memo[memo_key] = result
        return result

    def index(
        self, array: Array, column: int = 0, by_row: bool = True
    ) -> dict[object, list[int]]:
        """Positions of each normalized value in one column (or row) of a range."""

        values = _vector(array, column, by_row)
        key = (array.key, column, by_row) if array.key is not None else None
        if key is not None and key in self._indexes:
            return self._indexes[key]
        self.charge(len(values))
        built: dict[object, list[int]] = {}
        for position, value in enumerate(values):
            built.setdefault(_norm(value), []).append(position)
        if key is not None:
            self._indexes[key] = built
        return built


def _memo_key(name: str, args: list[Value]) -> tuple[object, ...] | None:
    parts: list[object] = [name]
    for arg in args:
        if isinstance(arg, Array) and arg.height * arg.width == 1:
            # A one-cell reference: keyed by its value, so equal cells share results.
            value = arg.rows[0][0]
            parts.append(("C", type(value).__name__, value))
        elif isinstance(arg, Array):
            if arg.key is None:
                return None
            parts.append(("R", arg.key))
        else:
            parts.append(("S", type(arg).__name__, arg))
    return tuple(parts)


# --- coercion ------------------------------------------------------------------


def _err(value: object) -> None:
    if isinstance(value, XLError):
        raise _Raise(value)


def _scalar(value: Value) -> Scalar:
    if isinstance(value, Array):
        if value.height == 1 and value.width == 1:
            return value.rows[0][0]
        raise _Raise(VALUE)
    return value


def _num(value: Value) -> float:
    value = _scalar(value)
    if isinstance(value, XLError):
        raise _Raise(value)
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, float | int):
        return float(value)
    number = text_to_number(value)
    if number is None:
        raise _Raise(VALUE)
    return number


def text_to_number(text: str) -> float | None:
    raw = text.strip().replace(",", "")
    if not raw:
        return None
    try:
        if raw.endswith("%"):
            return float(raw[:-1]) / 100
        return float(raw)
    except ValueError:
        return None


def _text(value: Value) -> str:
    value = _scalar(value)
    if isinstance(value, XLError):
        raise _Raise(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float | int):
        return general(float(value))
    return value


def general(value: float) -> str:
    """Excel's General format: up to 15 significant digits."""

    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    text = f"{value:.15g}"
    if "e" in text:
        mantissa, exponent = text.split("e")
        sign = "-" if exponent.startswith("-") else "+"
        return f"{mantissa}E{sign}{abs(int(exponent)):02d}"
    return text


def _bool(value: Value) -> bool:
    value = _scalar(value)
    if isinstance(value, XLError):
        raise _Raise(value)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, float | int):
        return value != 0
    upper = value.strip().upper()
    if upper in ("TRUE", "FALSE"):
        return upper == "TRUE"
    raise _Raise(VALUE)


def _int(value: Value) -> int:
    return int(math.floor(_num(value)))


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise _Raise(NUM)
    return value


def _norm(value: Scalar) -> object:
    if value is None or value == "":
        return ("e",)
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, float | int):
        return ("n", float(value))
    if isinstance(value, XLError):
        return ("x", value.code)
    return ("s", value.casefold())


def _rank(value: Scalar) -> int:
    # Excel's ordering across types: numbers < text < logical.
    if isinstance(value, bool):
        return 2
    if isinstance(value, str):
        return 1
    return 0


def compare(left: Scalar, right: Scalar) -> int:
    if left is None:
        left = (
            "" if isinstance(right, str) else False if isinstance(right, bool) else 0.0
        )
    if right is None:
        right = (
            "" if isinstance(left, str) else False if isinstance(left, bool) else 0.0
        )
    a, b = _rank(left), _rank(right)
    if a != b:
        return -1 if a < b else 1
    if isinstance(left, str):
        x, y = left.casefold(), str(right).casefold()
        return (x > y) - (x < y)
    p, q = float(cast(float, left)), float(cast(float, right))
    return (p > q) - (p < q)


# --- operators and lifting ---------------------------------------------------------


def _arith(fn: Callable[[float, float], float]) -> Callable[[Scalar, Scalar], Scalar]:
    def apply(left: Scalar, right: Scalar) -> Scalar:
        return _finite(fn(_num(left), _num(right)))

    return apply


def _divide(a: float, b: float) -> float:
    if b == 0:
        raise _Raise(DIV0)
    return a / b


def _power(a: float, b: float) -> float:
    if a == 0 and b <= 0:
        raise _Raise(NUM if b == 0 else DIV0)
    try:
        result = a**b
    except (OverflowError, ZeroDivisionError):
        raise _Raise(NUM) from None
    if isinstance(result, complex):
        raise _Raise(NUM)
    return result


def _comparison(test: Callable[[int], bool]) -> Callable[[Scalar, Scalar], Scalar]:
    def apply(left: Scalar, right: Scalar) -> Scalar:
        _err(left)
        _err(right)
        return test(compare(left, right))

    return apply


_BINARY: dict[str, Callable[[Scalar, Scalar], Scalar]] = {
    "+": _arith(lambda a, b: a + b),
    "-": _arith(lambda a, b: a - b),
    "*": _arith(lambda a, b: a * b),
    "/": _arith(_divide),
    "^": _arith(_power),
    "&": lambda a, b: _text(a) + _text(b),
    "=": _comparison(lambda c: c == 0),
    "<>": _comparison(lambda c: c != 0),
    "<": _comparison(lambda c: c < 0),
    ">": _comparison(lambda c: c > 0),
    "<=": _comparison(lambda c: c <= 0),
    ">=": _comparison(lambda c: c >= 0),
}


def _safe(fn: Callable[[], Scalar]) -> Scalar:
    try:
        return fn()
    except _Raise as exc:
        return exc.error


def _lift1(value: Value, fn: Callable[[Scalar], Scalar]) -> Value:
    if isinstance(value, Array):
        return Array([[_safe(lambda v=v: fn(v)) for v in row] for row in value.rows])
    return _safe(lambda: fn(value))


def _lift2(left: Value, right: Value, fn: Callable[[Scalar, Scalar], Scalar]) -> Value:
    if not isinstance(left, Array) and not isinstance(right, Array):
        return _safe(lambda: fn(left, right))
    a = left if isinstance(left, Array) else Array([[left]])
    b = right if isinstance(right, Array) else Array([[right]])
    height = max(a.height, b.height)
    width = max(a.width, b.width)
    for side in (a, b):
        if side.height not in (1, height) or side.width not in (1, width):
            return VALUE
    return Array(
        [
            [
                _safe(
                    lambda r=r, c=c: fn(
                        a.rows[0 if a.height == 1 else r][0 if a.width == 1 else c],
                        b.rows[0 if b.height == 1 else r][0 if b.width == 1 else c],
                    )
                )
                for c in range(width)
            ]
            for r in range(height)
        ]
    )


def _scalar_function(
    fn: Callable[..., Scalar],
) -> Callable[[Evaluator, list[Value]], Value]:
    """A function of single values; an array argument maps it over each element."""

    def apply(_: Evaluator, args: list[Value]) -> Value:
        arrays = [a for a in args if isinstance(a, Array) and a.height * a.width != 1]
        if not arrays:
            return fn(*[_scalar(a) for a in args])
        height = max(a.height for a in arrays)
        width = max(a.width for a in arrays)

        def pick(arg: Value, r: int, c: int) -> Scalar:
            if not isinstance(arg, Array):
                return arg
            if arg.height * arg.width == 1:
                return arg.rows[0][0]
            if r >= arg.height or c >= arg.width:
                return NA
            return arg.rows[r][c]

        return Array(
            [
                [
                    _safe(lambda r=r, c=c: fn(*[pick(a, r, c) for a in args]))
                    for c in range(width)
                ]
                for r in range(height)
            ]
        )

    return apply


# --- aggregates ------------------------------------------------------------------


def _numbers(args: list[Value], *, count_direct: bool = True) -> list[float]:
    """Numbers as SUM/AVERAGE see them: from arrays only numbers count (text,
    logical and empty skipped, errors raise); direct values are coerced."""

    numbers: list[float] = []
    for arg in args:
        if isinstance(arg, Array):
            for value in arg.flat():
                _err(value)
                if isinstance(value, float | int) and not isinstance(value, bool):
                    numbers.append(float(value))
        elif arg is not None and count_direct:
            numbers.append(_num(arg))
    return numbers


def _sum(_: Evaluator, args: list[Value]) -> Value:
    return math.fsum(_numbers(args))


def _product(_: Evaluator, args: list[Value]) -> Value:
    return _finite(math.prod(_numbers(args)))


def _average(_: Evaluator, args: list[Value]) -> Value:
    numbers = _numbers(args)
    if not numbers:
        return DIV0
    return math.fsum(numbers) / len(numbers)


def _median(_: Evaluator, args: list[Value]) -> Value:
    numbers = sorted(_numbers(args))
    if not numbers:
        return NUM
    middle = len(numbers) // 2
    if len(numbers) % 2:
        return numbers[middle]
    return (numbers[middle - 1] + numbers[middle]) / 2


def _min(_: Evaluator, args: list[Value]) -> Value:
    return min(_numbers(args), default=0.0)


def _max(_: Evaluator, args: list[Value]) -> Value:
    return max(_numbers(args), default=0.0)


def _count(_: Evaluator, args: list[Value]) -> Value:
    count = 0
    for arg in args:
        if isinstance(arg, Array):
            count += sum(
                1
                for v in arg.flat()
                if isinstance(v, float | int) and not isinstance(v, bool)
            )
        elif isinstance(arg, bool) or isinstance(arg, float | int):
            count += 1
        elif isinstance(arg, str) and text_to_number(arg) is not None:
            count += 1
    return float(count)


def _counta(_: Evaluator, args: list[Value]) -> Value:
    count = 0
    for arg in args:
        if isinstance(arg, Array):
            count += sum(1 for v in arg.flat() if v is not None)
        elif arg is not None:
            count += 1
    return float(count)


def _countblank(_: Evaluator, args: list[Value]) -> Value:
    arg = args[0]
    values = arg.flat() if isinstance(arg, Array) else [arg]
    return float(sum(1 for v in values if v is None or v == ""))


def _sumproduct(_: Evaluator, args: list[Value]) -> Value:
    arrays = [a if isinstance(a, Array) else Array([[a]]) for a in args]
    shape = (arrays[0].height, arrays[0].width)
    if any((a.height, a.width) != shape for a in arrays):
        return VALUE
    total = 0.0
    columns = [a.flat() for a in arrays]
    for values in zip(*columns, strict=True):
        product = 1.0
        for v in values:
            _err(v)
            product *= (
                float(v)
                if isinstance(v, float | int) and not isinstance(v, bool)
                else 0.0
            )
        total += product
    return total


def aggregate(kind: str, values: Sequence[Scalar]) -> Scalar:
    """SUM/AVERAGE/MIN/MAX/COUNT over plain values, for code outside formulas."""

    array = Array([[v] for v in values])
    function = {
        "sum": _sum,
        "average": _average,
        "min": _min,
        "max": _max,
        "count": _count,
    }
    try:
        return _scalar(function[kind](None, [array]))  # type: ignore[arg-type]
    except _Raise as exc:
        return exc.error


# --- criteria (COUNTIF family) -----------------------------------------------------

_CRITERIA_OPS = ("<=", ">=", "<>", "=", "<", ">")


@dataclass(frozen=True, slots=True)
class _Criterion:
    op: str
    value: Scalar
    pattern: re.Pattern[str] | None

    def matches(self, cell: Scalar) -> bool:
        if isinstance(cell, XLError):
            return False
        target = self.value
        if self.op in ("=", "<>"):
            if target is None or target == "":
                hit = cell is None or cell == ""
            elif self.pattern is not None:
                hit = isinstance(cell, str) and bool(self.pattern.fullmatch(cell))
            elif isinstance(target, float):
                hit = (
                    isinstance(cell, float | int)
                    and not isinstance(cell, bool)
                    and float(cell) == target
                )
                if not hit and isinstance(cell, str):
                    hit = text_to_number(cell) == target
            elif isinstance(target, bool):
                hit = isinstance(cell, bool) and cell == target
            else:
                hit = (
                    isinstance(cell, str) and cell.casefold() == str(target).casefold()
                )
            return hit if self.op == "=" else not hit
        if cell is None or isinstance(cell, bool) != isinstance(target, bool):
            return False
        if isinstance(target, float) != (
            isinstance(cell, float | int) and not isinstance(cell, bool)
        ):
            return False
        order = compare(cell, target)
        return {"<": order < 0, ">": order > 0, "<=": order <= 0, ">=": order >= 0}[
            self.op
        ]

    @property
    def index_key(self) -> object | None:
        # An exact equality can use the range's value index.
        if self.op != "=" or self.pattern is not None or self.value in (None, ""):
            return None
        if isinstance(self.value, str) and text_to_number(self.value) is not None:
            return None
        return _norm(self.value)


def _wildcard(text: str) -> re.Pattern[str] | None:
    if not re.search(r"(?<!~)[*?]", text):
        return None
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "~" and i + 1 < len(text) and text[i + 1] in "*?~":
            out.append(re.escape(text[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(ch))
        i += 1
    return re.compile("".join(out), re.IGNORECASE | re.DOTALL)


def _criterion(raw: Value) -> _Criterion:
    value = _scalar(raw)
    _err(value)
    if not isinstance(value, str):
        return _Criterion("=", float(value) if isinstance(value, int) else value, None)
    op = next((o for o in _CRITERIA_OPS if value.startswith(o)), "=")
    rest = value[len(op) :] if value.startswith(op) else value
    number = text_to_number(rest) if rest.strip() else None
    if number is not None:
        return _Criterion(op, number, None)
    upper = rest.strip().upper()
    if upper in ("TRUE", "FALSE"):
        return _Criterion(op, upper == "TRUE", None)
    pattern = _wildcard(rest) if op in ("=", "<>") else None
    return _Criterion(op, rest, pattern)


def _matching(
    ev: Evaluator, pairs: list[tuple[Value, Value]], size: tuple[int, int]
) -> list[int]:
    """Positions (row-major) where every (range, criterion) pair matches."""

    criteria: list[tuple[list[Scalar], _Criterion, Array]] = []
    for rng, crit in pairs:
        if not isinstance(rng, Array) or (rng.height, rng.width) != size:
            raise _Raise(VALUE)
        criteria.append((rng.flat(), _criterion(crit), rng))
    candidates: Sequence[int] | None = None
    for _, criterion, rng in criteria:
        key = criterion.index_key
        if key is not None and rng.width == 1:
            candidates = ev.index(rng).get(key, [])
            break
    positions = range(size[0] * size[1]) if candidates is None else candidates
    ev.charge(len(positions) * len(criteria))
    return [
        p for p in positions if all(c.matches(values[p]) for values, c, _ in criteria)
    ]


def _values_at(rng: Value, positions: list[int]) -> list[float]:
    if not isinstance(rng, Array):
        raise _Raise(VALUE)
    flat = rng.flat()
    out: list[float] = []
    for p in positions:
        if p >= len(flat):
            continue
        v = flat[p]
        _err(v)
        if isinstance(v, float | int) and not isinstance(v, bool):
            out.append(float(v))
    return out


def _size(rng: Value) -> tuple[int, int]:
    if not isinstance(rng, Array):
        raise _Raise(VALUE)
    return (rng.height, rng.width)


def _countif(ev: Evaluator, args: list[Value]) -> Value:
    return float(len(_matching(ev, [(args[0], args[1])], _size(args[0]))))


def _countifs(ev: Evaluator, args: list[Value]) -> Value:
    if len(args) % 2:
        return VALUE
    pairs = list(zip(args[0::2], args[1::2], strict=True))
    return float(len(_matching(ev, pairs, _size(args[0]))))


def _sumif(ev: Evaluator, args: list[Value]) -> Value:
    target = args[2] if len(args) > 2 and args[2] is not None else args[0]
    positions = _matching(ev, [(args[0], args[1])], _size(args[0]))
    return math.fsum(_values_at(target, positions))


def _ifs_family(
    reduce: Callable[[list[float]], Value],
) -> Callable[[Evaluator, list[Value]], Value]:
    def apply(ev: Evaluator, args: list[Value]) -> Value:
        target, rest = args[0], args[1:]
        if len(rest) % 2:
            return VALUE
        pairs = list(zip(rest[0::2], rest[1::2], strict=True))
        positions = _matching(ev, pairs, _size(target))
        return reduce(_values_at(target, positions))

    return apply


def _averageif(ev: Evaluator, args: list[Value]) -> Value:
    target = args[2] if len(args) > 2 and args[2] is not None else args[0]
    values = _values_at(target, _matching(ev, [(args[0], args[1])], _size(args[0])))
    return math.fsum(values) / len(values) if values else DIV0


# --- math ------------------------------------------------------------------------


def _round_with(mode: str) -> Callable[..., Scalar]:
    def apply(value: Scalar, digits: Scalar) -> Scalar:
        number = _num(value)
        places = int(_num(digits))
        step = Decimal(1).scaleb(-places)
        result = Decimal(repr(number)).quantize(
            step, rounding=mode, context=_ROUND_CONTEXT
        )
        return float(result)

    return apply


def _mod(a: Scalar, b: Scalar) -> Scalar:
    x, y = _num(a), _num(b)
    if y == 0:
        return DIV0
    return x - y * math.floor(x / y)


def _sqrt(value: Scalar) -> Scalar:
    number = _num(value)
    return NUM if number < 0 else math.sqrt(number)


# --- logical (lazy) -----------------------------------------------------------------


def _if(ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int) -> Value:
    condition = ev.evaluate(args[0], sheet, rows)
    if isinstance(condition, Array):
        then = ev.evaluate(args[1], sheet, rows) if len(args) > 1 else True
        other = ev.evaluate(args[2], sheet, rows) if len(args) > 2 else False
        return _scalar_function(lambda c, t, o: t if _bool(c) else o)(
            ev, [condition, then, other]
        )
    chosen = _bool(condition)
    if chosen:
        if len(args) < 2:
            return True
        branch = args[1]
    else:
        if len(args) < 3:
            return False
        branch = args[2]
    return 0.0 if isinstance(branch, Missing) else ev.evaluate(branch, sheet, rows)


def _iferror(
    ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int
) -> Value:
    value = ev.evaluate(args[0], sheet, rows)
    if isinstance(value, Array):
        fallback = ev.evaluate(args[1], sheet, rows)
        return _lift2(value, fallback, lambda v, f: f if isinstance(v, XLError) else v)
    if isinstance(value, XLError):
        return ev.evaluate(args[1], sheet, rows)
    return value


def _ifna(ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int) -> Value:
    value = ev.evaluate(args[0], sheet, rows)
    if value == NA:
        return ev.evaluate(args[1], sheet, rows)
    return value


def _ifs(ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int) -> Value:
    if len(args) % 2:
        return NA
    for i in range(0, len(args), 2):
        if _bool(ev.evaluate(args[i], sheet, rows)):
            return ev.evaluate(args[i + 1], sheet, rows)
    return NA


def _switch(
    ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int
) -> Value:
    subject = _scalar(ev.evaluate(args[0], sheet, rows))
    _err(subject)
    rest = args[1:]
    for i in range(0, len(rest) - 1, 2):
        candidate = _scalar(ev.evaluate(rest[i], sheet, rows))
        _err(candidate)
        if _rank(subject) == _rank(candidate) and compare(subject, candidate) == 0:
            return ev.evaluate(rest[i + 1], sheet, rows)
    if len(rest) % 2:
        return ev.evaluate(rest[-1], sheet, rows)
    return NA


def _logical(args: list[Value]) -> list[bool]:
    values: list[bool] = []
    for arg in args:
        if isinstance(arg, Array):
            for v in arg.flat():
                _err(v)
                if isinstance(v, bool):
                    values.append(v)
                elif isinstance(v, float | int):
                    values.append(v != 0)
        else:
            values.append(_bool(arg))
    if not values:
        raise _Raise(VALUE)
    return values


def _and(_: Evaluator, args: list[Value]) -> Value:
    return all(_logical(args))


def _or(_: Evaluator, args: list[Value]) -> Value:
    return any(_logical(args))


# --- text --------------------------------------------------------------------------


def _texts(args: list[Value]) -> list[str]:
    out: list[str] = []
    for arg in args:
        if isinstance(arg, Array):
            out.extend(_text(v) for v in arg.flat())
        else:
            out.append(_text(arg))
    return out


def _concat(_: Evaluator, args: list[Value]) -> Value:
    return "".join(_texts(args))


def _textjoin(_: Evaluator, args: list[Value]) -> Value:
    delimiter = _text(args[0])
    skip = _bool(args[1])
    parts = _texts(args[2:])
    return delimiter.join(p for p in parts if p or not skip)


def _left(text: Scalar, count: Scalar = 1.0) -> Scalar:
    n = int(_num(count))
    if n < 0:
        return VALUE
    return _text(text)[:n]


def _right(text: Scalar, count: Scalar = 1.0) -> Scalar:
    n = int(_num(count))
    if n < 0:
        return VALUE
    value = _text(text)
    return value[len(value) - n :] if n else ""


def _mid(text: Scalar, start: Scalar, count: Scalar) -> Scalar:
    s, n = int(_num(start)), int(_num(count))
    if s < 1 or n < 0:
        return VALUE
    return _text(text)[s - 1 : s - 1 + n]


def _proper(text: Scalar) -> Scalar:
    out, upper_next = [], True
    for ch in _text(text):
        out.append(ch.upper() if upper_next else ch.lower())
        upper_next = not ch.isalpha()
    return "".join(out)


def _substitute(
    text: Scalar, old: Scalar, new: Scalar, instance: Scalar = None
) -> Scalar:
    value, find, repl = _text(text), _text(old), _text(new)
    if not find:
        return value
    if instance is None:
        return value.replace(find, repl)
    nth = int(_num(instance))
    if nth < 1:
        return VALUE
    position = -1
    for _ in range(nth):
        position = value.find(find, position + 1)
        if position < 0:
            return value
    return value[:position] + repl + value[position + len(find) :]


def _value(text: Scalar) -> Scalar:
    if isinstance(text, float | int) and not isinstance(text, bool):
        return float(text)
    number = text_to_number(_text(text))
    return VALUE if number is None else number


# --- dates -------------------------------------------------------------------------


def to_serial(day: date) -> float:
    serial = (day - _EPOCH).days
    # Excel counts a nonexistent 1900-02-29 (serial 60).
    return float(serial if serial > 60 else serial - 1)


def from_serial(serial: float) -> date:
    whole = int(math.floor(serial))
    if whole < 1 or whole > _MAX_SERIAL:
        raise _Raise(NUM)
    if whole < 60:
        whole += 1
    elif whole == 60:
        whole = 61  # 1900-02-29 does not exist; show March 1st
    return _EPOCH + timedelta(days=whole)


def _date(year: Scalar, month: Scalar, day: Scalar) -> Scalar:
    y, m, d = int(_num(year)), int(_num(month)), int(_num(day))
    if 0 <= y < 1900:
        y += 1900
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    if not 1900 <= y <= 9999:
        return NUM
    serial = to_serial(date(y, m, 1)) + d - 1
    if serial < 1 or serial > _MAX_SERIAL:
        return NUM
    return serial


def _year(v: Scalar) -> Scalar:
    return float(from_serial(_num(v)).year)


def _month(v: Scalar) -> Scalar:
    return float(from_serial(_num(v)).month)


def _day(v: Scalar) -> Scalar:
    return float(from_serial(_num(v)).day)


def _weekday(v: Scalar, kind: Scalar = 1.0) -> Scalar:
    iso = from_serial(_num(v)).isoweekday()  # Monday 1 .. Sunday 7
    mode = int(_num(kind))
    if mode == 1:
        return float(iso % 7 + 1)
    if mode == 2:
        return float(iso)
    if mode == 3:
        return float(iso - 1)
    return NUM


def _add_months(day: date, months: int, end: bool) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    if not 1900 <= year <= 9999:
        raise _Raise(NUM)
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if end else min(day.day, last))


def _edate(start: Scalar, months: Scalar) -> Scalar:
    return to_serial(_add_months(from_serial(_num(start)), int(_num(months)), False))


def _eomonth(start: Scalar, months: Scalar) -> Scalar:
    return to_serial(_add_months(from_serial(_num(start)), int(_num(months)), True))


def _datedif(start: Scalar, end: Scalar, unit: Scalar) -> Scalar:
    a, b = from_serial(_num(start)), from_serial(_num(end))
    if a > b:
        return NUM
    kind = _text(unit).upper()
    months = (b.year - a.year) * 12 + b.month - a.month - (1 if b.day < a.day else 0)
    if kind == "D":
        return float((b - a).days)
    if kind == "M":
        return float(months)
    if kind == "Y":
        return float(months // 12)
    if kind == "YM":
        return float(months % 12)
    if kind == "MD":
        anchor = _add_months(a, months, False)
        return float((b - anchor).days)
    if kind == "YD":
        anchor = _add_months(a, (months // 12) * 12, False)
        return float((b - anchor).days)
    return NUM


# --- lookups -------------------------------------------------------------------------


def _vector(array: Array, index: int = 0, by_row: bool = True) -> list[Scalar]:
    """Column `index` of an array (or row `index` when `by_row` is False)."""

    if by_row:
        return [row[index] for row in array.rows]
    return list(array.rows[index])


def _as_array(value: Value) -> Array:
    if isinstance(value, Array):
        return value
    return Array([[value]])


def _is_vertical(array: Array) -> bool:
    return array.width == 1 or array.height > 1


def _sorted_ascending(values: list[Scalar]) -> bool:
    present = [v for v in values if v is not None and not isinstance(v, XLError)]
    return all(compare(a, b) <= 0 for a, b in zip(present, present[1:], strict=False))


def _find(
    ev: Evaluator,
    array: Array,
    values: list[Scalar],
    needle: Scalar,
    mode: int,
    reverse: bool = False,
    by_row: bool = True,
) -> int | None:
    """Position of `needle`: mode 0 exact (wildcards when text has them), 2 wildcard,
    -1 exact or next smaller, 1 exact or next larger; None when not found."""

    _err(needle)
    if needle is None:
        needle = 0.0
    pattern = _wildcard(needle) if isinstance(needle, str) and mode in (0, 2) else None
    if mode in (0, 2) and pattern is None:
        positions = ev.index(array, 0, by_row).get(_norm(needle))
        if not positions:
            return None
        return positions[-1] if reverse else positions[0]
    ev.charge(len(values))
    order = range(len(values) - 1, -1, -1) if reverse else range(len(values))
    if pattern is not None:
        for i in order:
            candidate = values[i]
            if isinstance(candidate, str) and pattern.fullmatch(candidate):
                return i
        return None
    best: int | None = None
    for i in order:
        value = values[i]
        if value is None or isinstance(value, XLError) or _rank(value) != _rank(needle):
            continue
        order_cmp = compare(value, needle)
        if order_cmp == 0:
            return i
        if (
            mode == -1
            and order_cmp < 0
            and (best is None or compare(value, values[best]) > 0)
        ):
            best = i
        if (
            mode == 1
            and order_cmp > 0
            and (best is None or compare(value, values[best]) < 0)
        ):
            best = i
    return best


def _approximate(values: list[Scalar], needle: Scalar, name: str) -> int | None:
    """Excel's sorted lookup (VLOOKUP TRUE, MATCH 1): the last value <= needle."""

    if not _sorted_ascending(values):
        raise FormulaError(
            f"{name} with an approximate match needs its lookup values sorted "
            "ascending; add FALSE (VLOOKUP, HLOOKUP) or 0 (MATCH) for an exact match, or "
            "use XLOOKUP"
        )
    best = None
    for i, value in enumerate(values):
        if value is None or isinstance(value, XLError) or _rank(value) != _rank(needle):
            continue
        if compare(value, needle) <= 0:
            best = i
        else:
            break
    return best


def _vlookup(ev: Evaluator, args: list[Value]) -> Value:
    needle = _scalar(args[0])
    table = _as_array(args[1])
    column = int(_num(args[2]))
    if column < 1:
        return VALUE
    if column > table.width:
        return REF
    exact = len(args) > 3 and args[3] is not None and not _bool(args[3])
    values = _vector(table, 0)
    if exact:
        found = _find(ev, table, values, needle, 0)
    else:
        _err(needle)
        ev.charge(len(values))
        found = _approximate(values, needle, "VLOOKUP")
    return NA if found is None else table.rows[found][column - 1]


def _match(ev: Evaluator, args: list[Value]) -> Value:
    needle = _scalar(args[0])
    array = _as_array(args[1])
    if array.height > 1 and array.width > 1:
        return NA
    by_row = array.width == 1
    values = _vector(array, 0, by_row)
    mode = int(_num(args[2])) if len(args) > 2 and args[2] is not None else 1
    if mode == 0:
        found = _find(ev, array, values, needle, 0, by_row=by_row)
    elif mode == 1:
        _err(needle)
        ev.charge(len(values))
        found = _approximate(values, needle, "MATCH")
    else:
        raise FormulaError(
            "MATCH with -1 (descending lookup) is not supported; use 0 for an exact "
            "match or XMATCH"
        )
    return NA if found is None else float(found + 1)


def _xlookup(ev: Evaluator, args: list[Value]) -> Value:
    needle = _scalar(args[0])
    lookup = _as_array(args[1])
    result = _as_array(args[2])
    if lookup.height > 1 and lookup.width > 1:
        return VALUE
    by_row = lookup.width == 1 and lookup.height >= 1
    values = _vector(lookup, 0, by_row)
    mode, search = _lookup_modes(args, 4)
    found = _find(ev, lookup, values, needle, mode, reverse=search == -1, by_row=by_row)
    if found is None:
        if len(args) > 3 and args[3] is not None:
            return args[3]
        return NA
    if by_row:
        if result.height != lookup.height:
            return VALUE
        row = result.rows[found]
        return row[0] if len(row) == 1 else Array([list(row)])
    if result.width != lookup.width:
        return VALUE
    column = [[r[found]] for r in result.rows]
    return column[0][0] if len(column) == 1 else Array(column)


def _lookup_modes(args: list[Value], start: int) -> tuple[int, int]:
    mode = (
        int(_num(args[start])) if len(args) > start and args[start] is not None else 0
    )
    search = (
        int(_num(args[start + 1]))
        if len(args) > start + 1 and args[start + 1] is not None
        else 1
    )
    if mode not in (-1, 0, 1, 2):
        raise _Raise(VALUE)
    if search not in (1, -1):
        raise FormulaError(
            "binary search modes (2, -2) are not supported; use 1 (first to last) "
            "or -1 (last to first)"
        )
    return mode, search


def _xmatch(ev: Evaluator, args: list[Value]) -> Value:
    needle = _scalar(args[0])
    array = _as_array(args[1])
    if array.height > 1 and array.width > 1:
        return VALUE
    by_row = array.width == 1
    values = _vector(array, 0, by_row)
    mode, search = _lookup_modes(args, 2)
    found = _find(ev, array, values, needle, mode, reverse=search == -1, by_row=by_row)
    return NA if found is None else float(found + 1)


def _index(_: Evaluator, args: list[Value]) -> Value:
    array = _as_array(args[0])
    row = int(_num(args[1])) if args[1] is not None else 0
    column = int(_num(args[2])) if len(args) > 2 and args[2] is not None else 0
    if array.height == 1 and len(args) == 2:
        row, column = 1, row
    if row < 0 or column < 0 or row > array.height or column > array.width:
        return REF
    if row and column:
        return array.rows[row - 1][column - 1]
    if row:
        if array.width == 1:
            return array.rows[row - 1][0]
        return Array([list(array.rows[row - 1])])
    if column:
        if array.height == 1:
            return array.rows[0][column - 1]
        return Array([[r[column - 1]] for r in array.rows])
    return Array([list(r) for r in array.rows])


def _filter(_: Evaluator, args: list[Value]) -> Value:
    array = _as_array(args[0])
    include = _as_array(args[1])
    if include.width == 1 and include.height == array.height:
        keep = [_bool(v) for v in _vector(include)]
        rows = [row for row, k in zip(array.rows, keep, strict=True) if k]
        if rows:
            return Array([list(r) for r in rows])
    elif include.height == 1 and include.width == array.width:
        keep = [_bool(v) for v in include.rows[0]]
        cols = [i for i, k in enumerate(keep) if k]
        if cols:
            return Array([[row[i] for i in cols] for row in array.rows])
    else:
        return VALUE
    if len(args) > 2 and args[2] is not None:
        return args[2]
    return CALC


def _sort_key(value: Scalar) -> tuple[int, object]:
    if value is None:
        return (4, 0)
    if isinstance(value, XLError):
        return (3, value.code)
    if isinstance(value, bool):
        return (2, value)
    if isinstance(value, str):
        return (1, value.casefold())
    return (0, float(value))


def _sort(_: Evaluator, args: list[Value]) -> Value:
    array = _as_array(args[0])
    index = int(_num(args[1])) if len(args) > 1 and args[1] is not None else 1
    order = int(_num(args[2])) if len(args) > 2 and args[2] is not None else 1
    by_col = _bool(args[3]) if len(args) > 3 and args[3] is not None else False
    if order not in (1, -1):
        return VALUE
    if by_col:
        if not 1 <= index <= array.height:
            return VALUE
        columns = sorted(
            range(array.width),
            key=lambda c: _sort_key(array.rows[index - 1][c]),
            reverse=order == -1,
        )
        return Array([[row[c] for c in columns] for row in array.rows])
    if not 1 <= index <= array.width:
        return VALUE
    present = [r for r in array.rows if r[index - 1] is not None]
    blank = [r for r in array.rows if r[index - 1] is None]
    present.sort(key=lambda r: _sort_key(r[index - 1]), reverse=order == -1)
    return Array([list(r) for r in present + blank])


def _unique(_: Evaluator, args: list[Value]) -> Value:
    array = _as_array(args[0])
    by_col = _bool(args[1]) if len(args) > 1 and args[1] is not None else False
    once = _bool(args[2]) if len(args) > 2 and args[2] is not None else False
    items = (
        [tuple(row[c] for row in array.rows) for c in range(array.width)]
        if by_col
        else [tuple(row) for row in array.rows]
    )
    counts: dict[tuple[object, ...], int] = {}
    first: dict[tuple[object, ...], tuple[Scalar, ...]] = {}
    for item in items:
        key = tuple(_norm(v) for v in item)
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, item)
    kept = [first[k] for k in first if not once or counts[k] == 1]
    if not kept:
        return CALC
    if by_col:
        return Array([[col[r] for col in kept] for r in range(array.height)])
    return Array([list(item) for item in kept])


# --- information and text (added) -------------------------------------------------


def _is_number(v: Scalar) -> Scalar:
    return isinstance(v, float | int) and not isinstance(v, bool)


def _find_text(find: Scalar, within: Scalar, start: Scalar, fold: bool) -> Scalar:
    needle, hay = _text(find), _text(within)
    begin = 1 if start is None else int(_num(start))
    if begin < 1 or begin > len(hay) + 1:
        return VALUE
    if not needle:
        return float(begin)
    if fold:
        pattern = _wildcard(needle)
        if pattern is not None:
            match = pattern.search(hay, begin - 1)
            return VALUE if match is None else float(match.start() + 1)
        needle = re.sub(r"~([*?~])", r"\1", needle).lower()
        hay = hay.lower()
    position = hay.find(needle, begin - 1)
    return VALUE if position < 0 else float(position + 1)


def _rept(text: Scalar, times: Scalar) -> Scalar:
    count = int(_num(times))
    value = _text(text)
    if count < 0 or len(value) * count > 32_767:
        return VALUE
    return value * count


# English names, as Excel en-US (the calendar module's follow the server locale).
_MONTH_NAMES = (
    ", January February March April May June July August September October "
    "November December"
).split(" ")
_DAY_NAMES = "Sunday Monday Tuesday Wednesday Thursday Friday Saturday".split()
_DATE_TOKEN_RE = re.compile(r"y+|m+|d+|h+|s+|[/\-.:, ]", re.IGNORECASE)
_NUMBER_FORMAT_RE = re.compile(
    r"(?P<pre>[$€£]?)(?P<int>[#0](?:[#0, ]*[#0])?)?"
    r"(?:\.(?P<dec>0*#*))?(?P<suf>%| ?[€$£])?"
)
TEXT_FORMATS_HINT = (
    "use 0, 0.00, #,##0, # ##0, 0%, 0.0%, dd/mm/yyyy, mmm yyyy or hh:mm, or a "
    "typed column instead"
)


def _text_function(value: Scalar, format_text: Scalar) -> Scalar:
    """TEXT with Excel's (en-US) reading of the common format codes."""

    fmt = _text(format_text)
    _err(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        converted = text_to_number(value)
        if converted is None:
            return value
        value = converted
    number = _num(value)
    if not fmt:
        return ""
    if fmt.strip().upper() == "GENERAL":
        return general(number)
    if re.search(r"[dmyhs]", fmt, re.IGNORECASE):
        return _format_date(number, fmt)
    return _format_number(number, fmt)


def _refuse_format(fmt: str) -> FormulaError:
    return FormulaError(f"TEXT format {fmt!r} is not supported; {TEXT_FORMATS_HINT}")


def _format_number(number: float, fmt: str) -> str:
    match = _NUMBER_FORMAT_RE.fullmatch(fmt)
    if match is None or (match["int"] is None and match["dec"] is None):
        raise _refuse_format(fmt)
    pattern, decimals = match["int"] or "", match["dec"] or ""
    grouped = "," in pattern
    if grouped and " " in pattern:
        raise _refuse_format(fmt)
    suffix = match["suf"] or ""
    scaled = abs(number) * (100 if suffix == "%" else 1)
    rounded = Decimal(repr(scaled)).quantize(
        Decimal(1).scaleb(-len(decimals)),
        rounding=ROUND_HALF_UP,
        context=_ROUND_CONTEXT,
    )
    whole, _, fraction = f"{rounded:f}".partition(".")
    fraction = fraction[: len(decimals)]
    keep = len(decimals.rstrip("#"))
    while len(fraction) > keep and fraction.endswith("0"):
        fraction = fraction[:-1]
    slots = pattern.replace(",", "")
    zero = slots.find("0")
    minimum = len(slots[zero:].replace(" ", "")) if zero >= 0 else 0
    digits = whole.lstrip("0").rjust(minimum, "0")
    if grouped:
        body = f"{int(digits):,}" if digits else ""
    else:
        # Literal spaces sit at fixed places from the right; extra digits go left.
        out: list[str] = []
        rest = digits
        for char in reversed(slots):
            if char == " ":
                out.append(" ")
            elif rest:
                out.append(rest[-1])
                rest = rest[:-1]
        body = rest + "".join(reversed(out))
    text = body + ("." + fraction if decimals else "")
    sign = "-" if number < 0 else ""
    return f"{sign}{match['pre']}{text}{suffix}"


def _format_date(number: float, fmt: str) -> str:
    if number < 0 or number >= _MAX_SERIAL + 1:
        raise _Raise(VALUE)
    whole = int(math.floor(number))
    seconds = round((number - whole) * 86_400)
    if seconds == 86_400:
        whole, seconds = whole + 1, 0
    if whole == 0:  # Excel shows serial 0 as 00/01/1900
        year, month, day, weekday = 1900, 1, 0, 6
    else:
        when = from_serial(whole)
        year, month, day = when.year, when.month, when.day
        weekday = (whole - 1) % 7  # Excel's serial 1 is a Sunday
    tokens: list[str] = []
    position = 0
    while position < len(fmt):
        match = _DATE_TOKEN_RE.match(fmt, position)
        if match is None:
            raise _refuse_format(fmt)
        tokens.append(match.group(0))
        position = match.end()
    codes = [t.lower() for t in tokens]

    def near(index: int, step: int, letter: str) -> bool:
        index += step
        while 0 <= index < len(codes) and not codes[index][0].isalpha():
            index += step
        return 0 <= index < len(codes) and codes[index][0] == letter

    out: list[str] = []
    for index, code in enumerate(codes):
        size = len(code)
        kind = code[0]
        if not kind.isalpha():
            out.append(code)
        elif kind == "y":
            out.append(f"{year:04d}" if size > 2 else f"{year % 100:02d}")
        elif (
            kind == "m" and size <= 2 and (near(index, -1, "h") or near(index, 1, "s"))
        ):
            out.append(f"{seconds // 60 % 60:0{size}d}")
        elif kind == "m":
            names = _MONTH_NAMES[month]
            out.append(
                f"{month:0{size}d}"
                if size <= 2
                else names[:3]
                if size == 3
                else names[0]
                if size == 5
                else names
            )
        elif kind == "d":
            out.append(
                f"{day:0{size}d}"
                if size <= 2
                else _DAY_NAMES[weekday][:3]
                if size == 3
                else _DAY_NAMES[weekday]
            )
        elif kind == "h" and size <= 2:
            out.append(f"{seconds // 3600:0{size}d}")
        elif kind == "s" and size <= 2:
            out.append(f"{seconds % 60:0{size}d}")
        else:
            raise _refuse_format(fmt)
    return "".join(out)


# --- statistics (added) -------------------------------------------------------------


def _variance(sample: bool, root: bool) -> Callable[[Evaluator, list[Value]], Value]:
    def apply(_: Evaluator, args: list[Value]) -> Value:
        numbers = _numbers(args)
        count = len(numbers)
        if count < (2 if sample else 1):
            return DIV0
        mean = math.fsum(numbers) / count
        spread = math.fsum((x - mean) ** 2 for x in numbers) / (
            count - 1 if sample else count
        )
        return math.sqrt(spread) if root else spread

    return apply


def _averagea(_: Evaluator, args: list[Value]) -> Value:
    numbers: list[float] = []
    for arg in args:
        if isinstance(arg, Array):
            for value in arg.flat():
                _err(value)
                if value is None:
                    continue
                numbers.append(0.0 if isinstance(value, str) else _num(value))
        elif arg is not None:
            numbers.append(_num(arg))
    return math.fsum(numbers) / len(numbers) if numbers else DIV0


def _over(value: Value, fn: Callable[[Scalar], Scalar]) -> Value:
    """Apply `fn` to one value, or to each value of a multi-cell array."""

    if isinstance(value, Array) and value.height * value.width != 1:
        return _lift1(value, fn)
    return fn(_scalar(value))


def _percentile_of(numbers: list[float], k: float) -> Scalar:
    if not numbers or not 0 <= k <= 1:
        return NUM
    rank = k * (len(numbers) - 1)
    low = int(math.floor(rank))
    if low + 1 >= len(numbers):
        return numbers[low]
    return numbers[low] + (rank - low) * (numbers[low + 1] - numbers[low])


def _percentile(ev: Evaluator, args: list[Value]) -> Value:
    numbers = ev.sorted_numbers(args[0])
    return _over(args[1], lambda k: _percentile_of(numbers, _num(k)))


def _quartile(ev: Evaluator, args: list[Value]) -> Value:
    numbers = ev.sorted_numbers(args[0])

    def at(q: Scalar) -> Scalar:
        quart = int(_num(q))
        return NUM if not 0 <= quart <= 4 else _percentile_of(numbers, quart / 4)

    return _over(args[1], at)


def _nth(largest: bool) -> Callable[[Evaluator, list[Value]], Value]:
    def apply(ev: Evaluator, args: list[Value]) -> Value:
        numbers = ev.sorted_numbers(args[0])

        def at(k: Scalar) -> Scalar:
            n = math.ceil(_num(k))
            if not 1 <= n <= len(numbers):
                return NUM
            return numbers[-n] if largest else numbers[n - 1]

        return _over(args[1], at)

    return apply


def _rank_eq(ev: Evaluator, args: list[Value]) -> Value:
    if not isinstance(args[1], Array):
        return VALUE
    numbers = ev.sorted_numbers(args[1])
    ascending = len(args) > 2 and args[2] is not None and _num(args[2]) != 0

    def at(v: Scalar) -> Scalar:
        x = _num(v)
        low = bisect.bisect_left(numbers, x)
        if low == len(numbers) or numbers[low] != x:
            return NA
        if ascending:
            return float(low + 1)
        return float(len(numbers) - bisect.bisect_right(numbers, x) + 1)

    return _over(args[0], at)


# --- finance -------------------------------------------------------------------------


def _growth(rate: float, periods: float) -> float:
    try:
        result = (1 + rate) ** periods
    except (OverflowError, ZeroDivisionError):
        raise _Raise(NUM) from None
    if isinstance(result, complex) or not math.isfinite(result):
        raise _Raise(NUM)
    return result


def _due(kind: Scalar) -> float:
    return 1.0 if _num(kind) != 0 else 0.0


def _pmt(
    rate: Scalar, nper: Scalar, pv: Scalar, fv: Scalar = None, kind: Scalar = None
) -> Scalar:
    r, n, p, f, t = _num(rate), _num(nper), _num(pv), _num(fv), _due(kind)
    if n == 0:
        return NUM
    if r == 0:
        return -(p + f) / n
    g = _growth(r, n)
    if g == 1:
        return DIV0
    return _finite(-(r * (f + p * g)) / ((1 + r * t) * (g - 1)))


def _fv(
    rate: Scalar, nper: Scalar, pmt: Scalar, pv: Scalar = None, kind: Scalar = None
) -> Scalar:
    r, n, a, p, t = _num(rate), _num(nper), _num(pmt), _num(pv), _due(kind)
    if r == 0:
        return -(p + a * n)
    g = _growth(r, n)
    return _finite(-(p * g + a * (1 + r * t) * (g - 1) / r))


def _pv(
    rate: Scalar, nper: Scalar, pmt: Scalar, fv: Scalar = None, kind: Scalar = None
) -> Scalar:
    r, n, a, f, t = _num(rate), _num(nper), _num(pmt), _num(fv), _due(kind)
    if r == 0:
        return -(f + a * n)
    g = _growth(r, n)
    return _finite(-(f + a * (1 + r * t) * (g - 1) / r) / g)


def _npv(_: Evaluator, args: list[Value]) -> Value:
    rate = _num(args[0])
    if rate == -1:
        return DIV0
    values = _numbers(args[1:])
    return _finite(math.fsum(v / _growth(rate, i + 1) for i, v in enumerate(values)))


def _solve(
    ev: Evaluator, f: Callable[[float], float], guess: float, cost: int
) -> float:
    """Newton's method from `guess`; #NUM! when it does not converge."""

    rate = guess
    for _ in range(MAX_SOLVER_ITERATIONS):
        ev.charge(cost)
        step_size = 1e-7 * max(1.0, abs(rate))
        try:
            value = f(rate)
            slope = (f(rate + step_size) - f(rate - step_size)) / (2 * step_size)
            step = value / slope
        except (OverflowError, ZeroDivisionError, _Raise):
            raise _Raise(NUM) from None
        if not math.isfinite(step):
            raise _Raise(NUM)
        rate -= step
        if rate <= -1:
            raise _Raise(NUM)
        if abs(step) < 1e-12 * max(1.0, abs(rate)):
            return rate
    raise _Raise(NUM)


def _irr(ev: Evaluator, args: list[Value]) -> Value:
    if not isinstance(args[0], Array):
        return VALUE
    flows = _numbers(args[:1])
    if not any(v > 0 for v in flows) or not any(v < 0 for v in flows):
        return NUM
    guess = _num(args[1]) if len(args) > 1 and args[1] is not None else 0.1

    def npv(rate: float) -> float:
        return math.fsum(v / _growth(rate, i) for i, v in enumerate(flows))

    return _solve(ev, npv, guess, 3 * len(flows))


def _rate(ev: Evaluator, args: list[Value]) -> Value:
    def opt(i: int, default: float) -> float:
        return _num(args[i]) if len(args) > i and args[i] is not None else default

    n, a, p = _num(args[0]), _num(args[1]), _num(args[2])
    f, t, guess = opt(3, 0.0), (1.0 if opt(4, 0.0) != 0 else 0.0), opt(5, 0.1)
    if n <= 0:
        return NUM

    def balance(r: float) -> float:
        if abs(r) < 1e-12:
            return p + a * n + f
        g = _growth(r, n)
        return p * g + a * (1 + r * t) * (g - 1) / r + f

    return _solve(ev, balance, guess, 3)


# --- lookup (added) -----------------------------------------------------------------


def _hlookup(ev: Evaluator, args: list[Value]) -> Value:
    needle = _scalar(args[0])
    table = _as_array(args[1])
    row = int(_num(args[2]))
    if row < 1:
        return VALUE
    if row > table.height:
        return REF
    exact = len(args) > 3 and args[3] is not None and not _bool(args[3])
    values = _vector(table, 0, by_row=False)
    if exact:
        found = _find(ev, table, values, needle, 0, by_row=False)
    else:
        _err(needle)
        ev.charge(len(values))
        found = _approximate(values, needle, "HLOOKUP")
    return NA if found is None else table.rows[row - 1][found]


def _choose(
    ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int
) -> Value:
    index = ev.evaluate(args[0], sheet, rows)
    if isinstance(index, Array) and index.height * index.width != 1:
        options = [ev.evaluate(a, sheet, rows) for a in args[1:]]

        def pick(i: Scalar, *values: Scalar) -> Scalar:
            n = int(_num(i))
            return values[n - 1] if 1 <= n <= len(values) else VALUE

        return _scalar_function(pick)(ev, [index, *options])
    n = int(_num(index))
    if not 1 <= n < len(args):
        return VALUE
    chosen = args[n]
    return 0.0 if isinstance(chosen, Missing) else ev.arg(chosen, sheet, rows)


def _let(ev: Evaluator, args: tuple[Node, ...], sheet: SheetGrid, rows: int) -> Value:
    scope: dict[str, Value] = {}
    ev._env.append(scope)
    try:
        for i in range(0, len(args) - 1, 2):
            scope[cast(Name, args[i]).name] = ev.arg(args[i + 1], sheet, rows)
        return ev.evaluate(args[-1], sheet, rows)
    finally:
        ev._env.pop()


def _sequence(ev: Evaluator, args: list[Value]) -> Value:
    def opt(i: int, default: float) -> float:
        return _num(args[i]) if len(args) > i and args[i] is not None else default

    height, width = int(opt(0, 1)), int(opt(1, 1))
    start, step = opt(2, 1), opt(3, 1)
    if height < 0 or width < 0:
        return VALUE
    if height == 0 or width == 0:
        return CALC
    ev.charge(height * width)
    return Array(
        [[start + (r * width + c) * step for c in range(width)] for r in range(height)]
    )


# --- dates (added) ----------------------------------------------------------------------


def _day_serial(value: Value) -> int:
    serial = int(math.floor(_num(value)))
    if not 0 <= serial <= _MAX_SERIAL:
        raise _Raise(NUM)
    return serial


def _is_workday(serial: int) -> bool:
    return (serial - 1) % 7 not in (0, 6)  # Excel's serial 1 is a Sunday


def _holidays(args: list[Value], index: int) -> set[int]:
    if len(args) <= index or args[index] is None:
        return set()
    days: set[int] = set()
    for value in _as_array(args[index]).flat():
        _err(value)
        if value is None:
            continue
        if isinstance(value, bool | str):
            raise _Raise(VALUE)
        days.add(_day_serial(value))
    return days


def _days(end: Scalar, start: Scalar) -> Scalar:
    return float(_day_serial(end) - _day_serial(start))


def _networkdays(ev: Evaluator, args: list[Value]) -> Value:
    a, b = _day_serial(_scalar(args[0])), _day_serial(_scalar(args[1]))
    holidays = _holidays(args, 2)
    ev.charge(len(holidays))
    sign = 1
    if a > b:
        a, b, sign = b, a, -1
    span = b - a + 1
    count = span // 7 * 5
    count += sum(1 for d in range(a + span // 7 * 7, b + 1) if _is_workday(d))
    count -= sum(1 for d in holidays if a <= d <= b and _is_workday(d))
    return float(sign * count)


def _workday(ev: Evaluator, args: list[Value]) -> Value:
    current = _day_serial(_scalar(args[0]))
    remaining = int(_num(_scalar(args[1])))
    holidays = _holidays(args, 2)
    step = 1 if remaining > 0 else -1
    remaining = abs(remaining)
    if remaining > _MAX_SERIAL:
        return NUM
    # Any 7 days hold 5 weekdays: jump whole weeks, then walk the rest.
    while remaining > 5:
        ev.charge(len(holidays) + 1)
        weeks = (remaining - 1) // 5
        target = current + step * 7 * weeks
        low, high = sorted((current + step, target))
        off = sum(1 for d in holidays if low <= d <= high and _is_workday(d))
        remaining -= 5 * weeks - off
        current = target
        if not 0 <= current <= _MAX_SERIAL:
            return NUM
    while remaining:
        ev.charge(1)
        current += step
        if not 0 < current <= _MAX_SERIAL:
            return NUM
        if _is_workday(current) and current not in holidays:
            remaining -= 1
    return float(current)


def _yearfrac(start: Scalar, end: Scalar, basis: Scalar = None) -> Scalar:
    kind = 0 if basis is None else int(_num(basis))
    if not 0 <= kind <= 4:
        return NUM
    a, b = _day_serial(start), _day_serial(end)
    if a > b:
        a, b = b, a
    if a == b:
        return 0.0
    if kind == 2:
        return (b - a) / 360
    if kind == 3:
        return (b - a) / 365
    first, last = from_serial(a), from_serial(b)
    if kind == 1:
        return _actual_actual(first, last, b - a)
    d1, d2 = first.day, last.day
    if kind == 4:
        d1, d2 = min(d1, 30), min(d2, 30)
    else:  # US (NASD) 30/360, as Excel applies it
        end_of_feb1 = first.month == 2 and d1 == calendar.monthrange(first.year, 2)[1]
        end_of_feb2 = last.month == 2 and d2 == calendar.monthrange(last.year, 2)[1]
        if d1 == 31 and d2 == 31:
            d1 = d2 = 30
        elif d1 == 31:
            d1 = 30
        elif d1 == 30 and d2 == 31:
            d2 = 30
        elif end_of_feb1 and end_of_feb2:
            d1 = d2 = 30
        elif end_of_feb1:
            d1 = 30
    days = (last.year - first.year) * 360 + (last.month - first.month) * 30 + d2 - d1
    return days / 360


def _actual_actual(first: date, last: date, days: int) -> float:
    within_year = first.year == last.year or (
        last.year == first.year + 1
        and (first.month, first.day) >= (last.month, last.day)
    )
    if within_year:
        leap = calendar.isleap(first.year) and first.year == last.year
        for year in {first.year, last.year}:
            if calendar.isleap(year) and first <= date(year, 2, 29) <= last:
                leap = True
        return days / (366 if leap else 365)
    years = last.year - first.year + 1
    span = (date(last.year + 1, 1, 1) - date(first.year, 1, 1)).days
    return days / (span / years)


# --- rounding (added) ------------------------------------------------------------------


def _to_multiple(value: float, multiple: float, mode: str) -> float:
    quotient = _ROUND_CONTEXT.divide(Decimal(repr(value)), Decimal(repr(multiple)))
    steps = quotient.to_integral_value(rounding=mode)
    return float(steps * Decimal(repr(multiple)))


def _ceiling(number: Scalar, significance: Scalar) -> Scalar:
    x, s = _num(number), _num(significance)
    if s == 0 or x == 0:
        return 0.0
    if x > 0 and s < 0:
        return NUM
    return _to_multiple(x, s, ROUND_CEILING)


def _floor(number: Scalar, significance: Scalar) -> Scalar:
    x, s = _num(number), _num(significance)
    if s == 0:
        return 0.0 if x == 0 else DIV0
    if x > 0 and s < 0:
        return NUM
    return _to_multiple(x, s, ROUND_FLOOR)


def _math_rounding(up: bool) -> Callable[..., Scalar]:
    def apply(
        number: Scalar, significance: Scalar = None, mode: Scalar = None
    ) -> Scalar:
        x = _num(number)
        s = 1.0 if significance is None else abs(_num(significance))
        if s == 0 or x == 0:
            return 0.0
        away = mode is not None and _num(mode) != 0
        if x < 0 and away:
            direction = ROUND_FLOOR if up else ROUND_CEILING
        else:
            direction = ROUND_CEILING if up else ROUND_FLOOR
        return _to_multiple(x, s, direction)

    return apply


def _mround(number: Scalar, multiple: Scalar) -> Scalar:
    x, m = _num(number), _num(multiple)
    if m == 0 or x == 0:
        return 0.0
    if (x > 0) != (m > 0):
        return NUM
    return _to_multiple(x, m, ROUND_HALF_UP)


def _trunc(number: Scalar, digits: Scalar = None) -> Scalar:
    return _round_with(ROUND_DOWN)(number, 0.0 if digits is None else digits)


def _clock(date_only: bool) -> Callable[[Evaluator, list[Value]], Value]:
    def apply(ev: Evaluator, _: list[Value]) -> Value:
        now = ev.clock()
        serial = to_serial(now.date())
        if date_only:
            return serial
        return serial + (now.hour * 3600 + now.minute * 60 + now.second) / 86_400

    return apply


# These scan through indexes or count their own reads.
_SELF_CHARGING = frozenset(
    {
        "COUNTIF",
        "COUNTIFS",
        "SUMIF",
        "SUMIFS",
        "AVERAGEIF",
        "AVERAGEIFS",
        "MINIFS",
        "MAXIFS",
        "VLOOKUP",
        "MATCH",
        "XLOOKUP",
        "XMATCH",
        "INDEX",
        "HLOOKUP",
        "PERCENTILE.INC",
        "QUARTILE.INC",
        "RANK.EQ",
        "RANK",
        "LARGE",
        "SMALL",
        "WORKDAY",
        "NETWORKDAYS",
        "SEQUENCE",
    }
)

_LAZY: dict[str, Callable[[Evaluator, tuple[Node, ...], SheetGrid, int], Value]] = {
    "IF": _if,
    "IFERROR": _iferror,
    "IFNA": _ifna,
    "IFS": _ifs,
    "SWITCH": _switch,
    "CHOOSE": _choose,
    "LET": _let,
}

_FUNCTIONS: dict[str, Callable[[Evaluator, list[Value]], Value]] = {
    "SUM": _sum,
    "SUMPRODUCT": _sumproduct,
    "PRODUCT": _product,
    "ROUND": _scalar_function(_round_with(ROUND_HALF_UP)),
    "ROUNDUP": _scalar_function(_round_with(ROUND_UP)),
    "ROUNDDOWN": _scalar_function(_round_with(ROUND_DOWN)),
    "INT": _scalar_function(lambda v: float(math.floor(_num(v)))),
    "ABS": _scalar_function(lambda v: abs(_num(v))),
    "MOD": _scalar_function(_mod),
    "POWER": _scalar_function(lambda a, b: _finite(_power(_num(a), _num(b)))),
    "SQRT": _scalar_function(_sqrt),
    "AVERAGE": _average,
    "MEDIAN": _median,
    "MIN": _min,
    "MAX": _max,
    "COUNT": _count,
    "COUNTA": _counta,
    "COUNTBLANK": _countblank,
    "COUNTIF": _countif,
    "COUNTIFS": _countifs,
    "SUMIF": _sumif,
    "SUMIFS": _ifs_family(lambda v: math.fsum(v)),
    "AVERAGEIF": _averageif,
    "AVERAGEIFS": _ifs_family(lambda v: math.fsum(v) / len(v) if v else DIV0),
    "MINIFS": _ifs_family(lambda v: min(v, default=0.0)),
    "MAXIFS": _ifs_family(lambda v: max(v, default=0.0)),
    "AND": _and,
    "OR": _or,
    "NOT": _scalar_function(lambda v: not _bool(v)),
    "TRUE": lambda _, __: True,
    "FALSE": lambda _, __: False,
    "CONCAT": _concat,
    "CONCATENATE": _scalar_function(lambda *v: "".join(_text(x) for x in v)),
    "TEXTJOIN": _textjoin,
    "LEFT": _scalar_function(_left),
    "RIGHT": _scalar_function(_right),
    "MID": _scalar_function(_mid),
    "LEN": _scalar_function(lambda v: float(len(_text(v)))),
    "UPPER": _scalar_function(lambda v: _text(v).upper()),
    "LOWER": _scalar_function(lambda v: _text(v).lower()),
    "PROPER": _scalar_function(_proper),
    "TRIM": _scalar_function(lambda v: " ".join(p for p in _text(v).split(" ") if p)),
    "SUBSTITUTE": _scalar_function(_substitute),
    "VALUE": _scalar_function(_value),
    "DATE": _scalar_function(_date),
    "YEAR": _scalar_function(_year),
    "MONTH": _scalar_function(_month),
    "DAY": _scalar_function(_day),
    "WEEKDAY": _scalar_function(_weekday),
    "EDATE": _scalar_function(_edate),
    "EOMONTH": _scalar_function(_eomonth),
    "DATEDIF": _scalar_function(_datedif),
    "VLOOKUP": _vlookup,
    "INDEX": _index,
    "MATCH": _match,
    "XLOOKUP": _xlookup,
    "XMATCH": _xmatch,
    "FILTER": _filter,
    "SORT": _sort,
    "UNIQUE": _unique,
    "SEQUENCE": _sequence,
    "HLOOKUP": _hlookup,
    "TRUNC": _scalar_function(_trunc),
    "MROUND": _scalar_function(_mround),
    "CEILING": _scalar_function(_ceiling),
    "FLOOR": _scalar_function(_floor),
    "CEILING.MATH": _scalar_function(_math_rounding(up=True)),
    "FLOOR.MATH": _scalar_function(_math_rounding(up=False)),
    "AVERAGEA": _averagea,
    "STDEV.S": _variance(sample=True, root=True),
    "STDEV": _variance(sample=True, root=True),
    "STDEV.P": _variance(sample=False, root=True),
    "VAR.S": _variance(sample=True, root=False),
    "VAR.P": _variance(sample=False, root=False),
    "PERCENTILE.INC": _percentile,
    "QUARTILE.INC": _quartile,
    "RANK.EQ": _rank_eq,
    "RANK": _rank_eq,
    "LARGE": _nth(largest=True),
    "SMALL": _nth(largest=False),
    "PMT": _scalar_function(_pmt),
    "FV": _scalar_function(_fv),
    "PV": _scalar_function(_pv),
    "NPV": _npv,
    "IRR": _irr,
    "RATE": _rate,
    "ISBLANK": _scalar_function(lambda v: v is None),
    "ISNUMBER": _scalar_function(_is_number),
    "ISTEXT": _scalar_function(lambda v: isinstance(v, str)),
    "ISERROR": _scalar_function(lambda v: isinstance(v, XLError)),
    "ISNA": _scalar_function(lambda v: v == NA),
    "TEXT": _scalar_function(_text_function),
    "FIND": _scalar_function(lambda f, w, s=None: _find_text(f, w, s, fold=False)),
    "SEARCH": _scalar_function(lambda f, w, s=None: _find_text(f, w, s, fold=True)),
    "REPT": _scalar_function(_rept),
    "EXACT": _scalar_function(lambda a, b: _text(a) == _text(b)),
    "DAYS": _scalar_function(_days),
    "WORKDAY": _workday,
    "NETWORKDAYS": _networkdays,
    "YEARFRAC": _scalar_function(_yearfrac),
    "TODAY": _clock(date_only=True),
    "NOW": _clock(date_only=False),
}
