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

"""Excel formulas: parse, check against the allow-list, emit and adjust.

One AST serves the writer (canonical text with Excel's stored prefixes), the
checker (allow-list, sheets, bounds) and the evaluator (`evaluator.py`).
Rationale: openspec/changes/add-spreadsheet-generation/design.md D13-D14.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from typing import cast

MAX_FORMULA_CHARS = 8_192
MAX_DEPTH = 32
MAX_COLUMN = 16_384
MAX_ROW = 1_048_576


class FormulaError(ValueError):
    """A formula the tool refuses; the message tells the model what to send."""


class FormulaReferenceError(FormulaError):
    """A refused reference form (another sheet, file or program, a whole column)."""


# --- AST ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Num:
    value: float


@dataclass(frozen=True, slots=True)
class Str:
    value: str


@dataclass(frozen=True, slots=True)
class Bool:
    value: bool


@dataclass(frozen=True, slots=True)
class Err:
    code: str


@dataclass(frozen=True, slots=True)
class Missing:
    """An empty argument, as in `IF(A1,,1)`."""


@dataclass(frozen=True, slots=True)
class Ref:
    """A cell or range, 1-based; `abs_*` mark `$` parts that never shift."""

    sheet: str | None
    c1: int
    r1: int
    c2: int
    r2: int
    abs_c1: bool = False
    abs_r1: bool = False
    abs_c2: bool = False
    abs_r2: bool = False
    is_range: bool = False


@dataclass(frozen=True, slots=True)
class Unary:
    op: str
    operand: Node


@dataclass(frozen=True, slots=True)
class Percent:
    operand: Node


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Call:
    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Group:
    inner: Node


Node = Num | Str | Bool | Err | Missing | Ref | Unary | Percent | Binary | Call | Group


# --- Allow-list ----------------------------------------------------------------

# name -> (min args, max args or None for "any")
FUNCTIONS: dict[str, tuple[int, int | None]] = {
    # math
    "SUM": (1, None),
    "SUMPRODUCT": (1, None),
    "PRODUCT": (1, None),
    "ROUND": (2, 2),
    "ROUNDUP": (2, 2),
    "ROUNDDOWN": (2, 2),
    "INT": (1, 1),
    "ABS": (1, 1),
    "MOD": (2, 2),
    "POWER": (2, 2),
    "SQRT": (1, 1),
    # statistics
    "AVERAGE": (1, None),
    "MEDIAN": (1, None),
    "MIN": (1, None),
    "MAX": (1, None),
    "COUNT": (1, None),
    "COUNTA": (1, None),
    "COUNTBLANK": (1, 1),
    "COUNTIF": (2, 2),
    "COUNTIFS": (2, None),
    "SUMIF": (2, 3),
    "SUMIFS": (3, None),
    "AVERAGEIF": (2, 3),
    "AVERAGEIFS": (3, None),
    "MINIFS": (3, None),
    "MAXIFS": (3, None),
    # logical
    "IF": (1, 3),
    "IFS": (2, None),
    "IFERROR": (2, 2),
    "IFNA": (2, 2),
    "AND": (1, None),
    "OR": (1, None),
    "NOT": (1, 1),
    "SWITCH": (3, None),
    "TRUE": (0, 0),
    "FALSE": (0, 0),
    # text
    "CONCAT": (1, None),
    "CONCATENATE": (1, None),
    "TEXTJOIN": (3, None),
    "LEFT": (1, 2),
    "RIGHT": (1, 2),
    "MID": (3, 3),
    "LEN": (1, 1),
    "UPPER": (1, 1),
    "LOWER": (1, 1),
    "PROPER": (1, 1),
    "TRIM": (1, 1),
    "SUBSTITUTE": (3, 4),
    "VALUE": (1, 1),
    # date
    "DATE": (3, 3),
    "YEAR": (1, 1),
    "MONTH": (1, 1),
    "DAY": (1, 1),
    "WEEKDAY": (1, 2),
    "EDATE": (2, 2),
    "EOMONTH": (2, 2),
    "DATEDIF": (3, 3),
    # lookup and dynamic arrays
    "VLOOKUP": (3, 4),
    "INDEX": (2, 3),
    "MATCH": (2, 3),
    "XLOOKUP": (3, 6),
    "XMATCH": (2, 4),
    "FILTER": (2, 3),
    "SORT": (1, 4),
    "UNIQUE": (1, 3),
}
DYNAMIC_ARRAY_FUNCTIONS = frozenset({"FILTER", "SORT", "UNIQUE"})
# The stored form Excel expects for functions newer than the 2007 file format.
_STORED_PREFIX = {
    "XLOOKUP": "_xlfn.",
    "XMATCH": "_xlfn.",
    "IFS": "_xlfn.",
    "IFNA": "_xlfn.",
    "SWITCH": "_xlfn.",
    "CONCAT": "_xlfn.",
    "TEXTJOIN": "_xlfn.",
    "MINIFS": "_xlfn.",
    "MAXIFS": "_xlfn.",
    "UNIQUE": "_xlfn.",
    "FILTER": "_xlfn._xlws.",
    "SORT": "_xlfn._xlws.",
}
_VOLATILE = "its value changes each time the file opens"
DENIED_FUNCTIONS: dict[str, str] = {
    "INDIRECT": "it builds references from text, which hides them from the check; write the reference itself",
    "OFFSET": f"{_VOLATILE}; write the range itself",
    "NOW": _VOLATILE,
    "TODAY": f"{_VOLATILE}; write the date as a value",
    "RAND": _VOLATILE,
    "RANDBETWEEN": _VOLATILE,
    "RANDARRAY": _VOLATILE,
    "WEBSERVICE": "it calls the network",
    "FILTERXML": "it goes with network calls",
    "ENCODEURL": "it goes with network calls",
    "IMAGE": "it loads a picture from the network",
    "RTD": "it reads live data from another program",
    "HYPERLINK": "a link can send cell contents to a website or open a file; put the address as plain text",
    "CELL": "it reads the file's location and environment",
    "INFO": "it reads the computer's environment",
    "CALL": "it runs code outside the workbook",
    "REGISTER.ID": "it runs code outside the workbook",
    "EXEC": "it runs code outside the workbook",
}
# Common French names, to give the English one in the refusal.
_FRENCH_NAMES = {
    "SOMME": "SUM",
    "MOYENNE": "AVERAGE",
    "NB": "COUNT",
    "NBVAL": "COUNTA",
    "NB.SI": "COUNTIF",
    "NB.SI.ENS": "COUNTIFS",
    "SOMME.SI": "SUMIF",
    "SOMME.SI.ENS": "SUMIFS",
    "MOYENNE.SI": "AVERAGEIF",
    "SI": "IF",
    "SIERREUR": "IFERROR",
    "SI.CONDITIONS": "IFS",
    "ET": "AND",
    "OU": "OR",
    "NON": "NOT",
    "ARRONDI": "ROUND",
    "ARRONDI.SUP": "ROUNDUP",
    "ARRONDI.INF": "ROUNDDOWN",
    "ENT": "INT",
    "RECHERCHEV": "VLOOKUP",
    "RECHERCHEX": "XLOOKUP",
    "EQUIV": "MATCH",
    "EQUIVX": "XMATCH",
    "FILTRE": "FILTER",
    "TRIER": "SORT",
    "CONCATENER": "CONCATENATE",
    "GAUCHE": "LEFT",
    "DROITE": "RIGHT",
    "STXT": "MID",
    "NBCAR": "LEN",
    "MAJUSCULE": "UPPER",
    "MINUSCULE": "LOWER",
    "SUPPRESPACE": "TRIM",
    "SUBSTITUE": "SUBSTITUTE",
    "CNUM": "VALUE",
    "ANNEE": "YEAR",
    "MOIS": "MONTH",
    "JOUR": "DAY",
    "JOURSEM": "WEEKDAY",
    "MOIS.DECALER": "EDATE",
    "FIN.MOIS": "EOMONTH",
    "MEDIANE": "MEDIAN",
    "PRODUIT": "PRODUCT",
    "RACINE": "SQRT",
    "PUISSANCE": "POWER",
}
FUNCTION_FAMILIES = (
    "math (SUM, ROUND, ABS, MOD, SUMPRODUCT...), statistics (AVERAGE, MEDIAN, MIN, "
    "MAX, COUNT, COUNTA, COUNTIF(S), SUMIF(S), AVERAGEIF(S), MINIFS, MAXIFS), logical "
    "(IF, IFS, IFERROR, IFNA, AND, OR, NOT, SWITCH), text (CONCAT, TEXTJOIN, LEFT, "
    "RIGHT, MID, LEN, UPPER, LOWER, PROPER, TRIM, SUBSTITUTE, VALUE, &), date (DATE, "
    "YEAR, MONTH, DAY, WEEKDAY, EDATE, EOMONTH, DATEDIF), lookup (VLOOKUP, INDEX, "
    "MATCH, XLOOKUP, XMATCH, FILTER, SORT, UNIQUE)"
)


# --- Tokenizer -----------------------------------------------------------------

_CELL = r"(\$?)([A-Za-z]{1,3})(\$?)([0-9]+)"
_CELL_RE = re.compile(_CELL)
_RANGE_RE = re.compile(_CELL + r"(?::" + _CELL + r")?")
_WHOLE_COLUMN_RE = re.compile(r"\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3}(?![A-Za-z0-9])")
_WHOLE_ROW_RE = re.compile(r"\$?[0-9]+:\$?[0-9]+")
_IDENT_RE = re.compile(r"[A-Za-z_\\][A-Za-z0-9_.\\]*")
_UNQUOTED_SHEET_RE = re.compile(r"([^\W\d][\w.]*)!", re.UNICODE)
_NUMBER_RE = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_ERROR_RE = re.compile(
    r"#(?:DIV/0!|N/A|NAME\?|NULL!|NUM!|REF!|VALUE!|CALC!|SPILL!)", re.IGNORECASE
)
_R1C1_RE = re.compile(r"^R(\[?-?\d*\]?)C(\[?-?\d*\]?)$", re.IGNORECASE)
_PATH_RE = re.compile(r"[\\/]|^[A-Za-z]:|https?:|file:", re.IGNORECASE)
_STRING_RE = re.compile(r'"(?:[^"]|"")*"')
_PREFIX_RE = re.compile(r"^(?:_xlfn\.)?(?:_xlws\.)?", re.IGNORECASE)
_SIMPLE_SHEET_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_CELL_LIKE_NAME_RE = re.compile(r"[A-Za-z]{1,3}[0-9]+|R[0-9]*C?[0-9]*|C[0-9]*", re.I)

EXTERNAL_REFUSED = (
    "references to another workbook or file are not accepted; copy the values "
    "into a sheet of this workbook"
)
DDE_REFUSED = (
    "'|' links to another program (DDE) and is not accepted; use \"|\" only "
    "inside a quoted text"
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str  # NUM STR BOOL ERR REF FUNC OP LP RP COMMA
    value: object
    pos: int


def column_number(letters: str) -> int:
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - 64
    return number


def column_letters(index: int) -> str:
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _tokenize(text: str, sheet_names: Sequence[str] | None) -> list[_Token]:
    tokens: list[_Token] = []
    known = sorted(sheet_names or (), key=len, reverse=True)
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char in " \t\r\n":
            i += 1
            continue
        if char == '"':
            j = i + 1
            parts: list[str] = []
            while True:
                end = text.find('"', j)
                if end < 0:
                    raise FormulaError("a text in quotes is not closed")
                parts.append(text[j:end])
                if text.startswith('"', end + 1):
                    parts.append('"')
                    j = end + 2
                    continue
                i = end + 1
                break
            tokens.append(_Token("STR", "".join(parts), i))
            continue
        if char == "#":
            match = _ERROR_RE.match(text, i)
            if match is None:
                raise FormulaReferenceError(
                    "'#' after a reference (spill reference) is not supported; "
                    "write the range"
                )
            tokens.append(_Token("ERR", match.group(0).upper(), i))
            i = match.end()
            continue
        if char == "|":
            raise FormulaReferenceError(DDE_REFUSED)
        if char == ";":
            raise FormulaError(
                "use commas between arguments and English function names "
                "(for example =SUM(B2:B5,C2)), not semicolons"
            )
        if char == "{":
            raise FormulaError(
                "array constants in braces are not supported; use a range"
            )
        if char == "@":
            raise FormulaError("'@' (implicit intersection) is not supported")
        if char == "[":
            raise FormulaReferenceError(_bracket_message(text, i))
        if char in "(":
            tokens.append(_Token("LP", "(", i))
            i += 1
            continue
        if char == ")":
            tokens.append(_Token("RP", ")", i))
            i += 1
            continue
        if char == ",":
            tokens.append(_Token("COMMA", ",", i))
            i += 1
            continue
        two = text[i : i + 2]
        if two in ("<=", ">=", "<>"):
            tokens.append(_Token("OP", two, i))
            i += 2
            continue
        if char in "+-*/^&=<>%":
            tokens.append(_Token("OP", char, i))
            i += 1
            continue
        ref, end = _read_reference(text, i, known)
        if ref is not None:
            tokens.append(_Token("REF", ref, i))
            i = end
            continue
        if _WHOLE_ROW_RE.match(text, i):
            raise FormulaReferenceError(_WHOLE_REFUSED)
        number = _NUMBER_RE.match(text, i)
        if number is not None:
            tokens.append(_Token("NUM", float(number.group(0)), i))
            i = number.end()
            continue
        ident = _IDENT_RE.match(text, i)
        if ident is None:
            raise FormulaError(f"unexpected character {char!r}")
        name = ident.group(0)
        j = ident.end()
        while j < n and text[j] in " \t":
            j += 1
        if j < n and text[j] == "(":
            tokens.append(_Token("FUNC", name, i))
            i = ident.end()
            continue
        if j < n and text[j] == "[":
            raise FormulaReferenceError(
                f"structured references ({name}[...]) are not supported; use cell "
                "ranges such as B2:B20"
            )
        upper = name.upper()
        if upper in ("TRUE", "FALSE"):
            tokens.append(_Token("BOOL", upper == "TRUE", i))
            i = ident.end()
            continue
        if _R1C1_RE.match(name):
            raise FormulaReferenceError(
                f"R1C1 references ({name}) are not supported; use A1 references"
            )
        raise FormulaError(
            f"'{name}' is not a function, a cell or a sheet of this workbook; "
            "defined names are not supported (use a cell reference, or quote a "
            "text value)"
        )
    return tokens


_WHOLE_REFUSED = (
    "whole-column or whole-row references (B:B, 2:2) are not accepted: they "
    "would include the header and the totals row; use the data range such as "
    "B2:B20"
)


def _bracket_message(text: str, i: int) -> str:
    close = text.find("]", i)
    inside = text[i + 1 : close] if close > i else ""
    if re.search(r"\.(?:xl\w*|csv|ods)$", inside, re.I) or _PATH_RE.search(inside):
        return EXTERNAL_REFUSED
    if inside.isdigit():
        return EXTERNAL_REFUSED
    return "structured references in brackets are not supported; use cell ranges such as B2:B20"


def _read_reference(text: str, i: int, known: Sequence[str]) -> tuple[Ref | None, int]:
    sheet: str | None = None
    start = i
    if text[i] == "'":
        j = i + 1
        name_parts: list[str] = []
        while True:
            end = text.find("'", j)
            if end < 0:
                raise FormulaReferenceError("a sheet name in quotes is not closed")
            name_parts.append(text[j:end])
            if text.startswith("'", end + 1):
                name_parts.append("'")
                j = end + 2
                continue
            j = end + 1
            break
        if not text.startswith("!", j):
            raise FormulaReferenceError(
                "a quoted sheet name must be followed by '!' and a cell, as in "
                "'My sheet'!B2"
            )
        sheet = "".join(name_parts)
        if "[" in sheet or _PATH_RE.search(sheet):
            raise FormulaReferenceError(EXTERNAL_REFUSED)
        i = j + 1
    else:
        lowered = text[i:].casefold()
        for name in known:
            if lowered.startswith(name.casefold()) and text.startswith(
                "!", i + len(name)
            ):
                sheet = name
                i += len(name) + 1
                break
        else:
            match = _UNQUOTED_SHEET_RE.match(text, i)
            if match is not None:
                sheet = match.group(1)
                i = match.end()
    if sheet is not None and i < len(text) and text[i] == "[":
        raise FormulaReferenceError(EXTERNAL_REFUSED)
    if _WHOLE_COLUMN_RE.match(text, i):
        raise FormulaReferenceError(_WHOLE_REFUSED)
    match = _RANGE_RE.match(text, i)
    if match is None or (
        match.end() < len(text) and re.match(r"[A-Za-z0-9_.(\\]", text[match.end()])
    ):
        if sheet is not None:
            raise FormulaReferenceError(
                f"after '{sheet}!' give a cell or a range such as B2 or B2:B20"
            )
        return None, start
    if match.end() < len(text) and text[match.end()] == "#":
        raise FormulaReferenceError(
            "'#' after a reference (spill reference) is not supported; write the range"
        )
    g = match.groups()
    c1, r1 = column_number(g[1]), int(g[3])
    is_range = g[5] is not None
    c2, r2 = (column_number(g[5]), int(g[7])) if is_range else (c1, r1)
    if max(c1, c2) > MAX_COLUMN or max(r1, r2) > MAX_ROW or min(r1, r2) < 1:
        if sheet is not None:
            raise FormulaReferenceError(f"'{match.group(0)}' is outside the sheet grid")
        return None, start
    if c1 > c2:
        c1, c2 = c2, c1
    if r1 > r2:
        r1, r2 = r2, r1
    ref = Ref(
        sheet=sheet,
        c1=c1,
        r1=r1,
        c2=c2,
        r2=r2,
        abs_c1=bool(g[0]),
        abs_r1=bool(g[2]),
        abs_c2=bool(g[4]) if is_range else bool(g[0]),
        abs_r2=bool(g[6]) if is_range else bool(g[2]),
        is_range=is_range,
    )
    return ref, match.end()


# --- Parser --------------------------------------------------------------------

_BINARY_PRECEDENCE = {
    "=": 1,
    "<>": 1,
    "<": 1,
    ">": 1,
    "<=": 1,
    ">=": 1,
    "&": 2,
    "+": 3,
    "-": 3,
    "*": 4,
    "/": 4,
    "^": 5,
}


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    def peek(self) -> _Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> _Token:
        token = self.peek()
        if token is None:
            raise FormulaError("the formula ends too early")
        self.index += 1
        return token

    def expression(self, min_precedence: int = 0) -> Node:
        left = self.unary()
        while True:
            token = self.peek()
            if token is None or token.kind != "OP" or token.value == "%":
                return left
            precedence = _BINARY_PRECEDENCE[str(token.value)]
            if precedence <= min_precedence:
                return left
            self.take()
            right = self.expression(precedence)
            left = Binary(str(token.value), left, right)

    def unary(self) -> Node:
        token = self.peek()
        if token is not None and token.kind == "OP" and token.value in ("+", "-"):
            self.take()
            return Unary(str(token.value), self.unary())
        node = self.primary()
        while (
            (token := self.peek()) is not None
            and token.kind == "OP"
            and (token.value == "%")
        ):
            self.take()
            node = Percent(node)
        return node

    def primary(self) -> Node:
        token = self.take()
        if token.kind == "NUM":
            return Num(float(token.value))  # type: ignore[arg-type]
        if token.kind == "STR":
            return Str(str(token.value))
        if token.kind == "BOOL":
            return Bool(bool(token.value))
        if token.kind == "ERR":
            return Err(str(token.value))
        if token.kind == "REF":
            return token.value  # type: ignore[return-value]
        if token.kind == "LP":
            self._enter()
            inner = self.expression()
            self._expect("RP")
            self.depth -= 1
            return Group(inner)
        if token.kind == "FUNC":
            return self.call(str(token.value))
        raise FormulaError(f"unexpected {token.value!r} in the formula")

    def call(self, raw_name: str) -> Node:
        self._expect("LP")
        self._enter()
        args: list[Node] = []
        if (token := self.peek()) is not None and token.kind == "RP":
            self.take()
        else:
            while True:
                token = self.peek()
                if token is not None and token.kind in ("COMMA", "RP"):
                    args.append(Missing())
                else:
                    args.append(self.expression())
                separator = self.take()
                if separator.kind == "RP":
                    break
                if separator.kind != "COMMA":
                    raise FormulaError(
                        f"expected ',' or ')' in {raw_name}(...), got {separator.value!r}"
                    )
        self.depth -= 1
        name = _PREFIX_RE.sub("", raw_name).upper()
        return Call(name, tuple(args))

    def _enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise FormulaError(
                f"the formula nests more than {MAX_DEPTH} levels; split it over "
                "several columns"
            )

    def _expect(self, kind: str) -> None:
        token = self.take()
        if token.kind != kind:
            raise FormulaError(f"unexpected {token.value!r} in the formula")


def parse(text: str, sheet_names: Sequence[str] | None = None) -> Node:
    """Parse `=...`; `sheet_names` lets unquoted names with spaces resolve."""

    body = text.strip()
    if not body.startswith("="):
        raise FormulaError("a formula starts with '='")
    if len(body) > MAX_FORMULA_CHARS:
        raise FormulaError(
            f"the formula has {len(body)} characters; Excel's limit is {MAX_FORMULA_CHARS}"
        )
    if "|" in _STRING_RE.sub("", body):
        raise FormulaReferenceError(DDE_REFUSED)
    tokens = _tokenize(body[1:], sheet_names)
    if not tokens:
        raise FormulaError("the formula is empty")
    parser = _Parser(tokens)
    node = parser.expression()
    if parser.peek() is not None:
        raise FormulaError(f"unexpected {parser.peek().value!r} in the formula")  # type: ignore[union-attr]
    return node


def walk(node: Node) -> Iterator[Node]:
    yield node
    if isinstance(node, Unary | Percent):
        yield from walk(node.operand)
    elif isinstance(node, Binary):
        yield from walk(node.left)
        yield from walk(node.right)
    elif isinstance(node, Call):
        for arg in node.args:
            yield from walk(arg)
    elif isinstance(node, Group):
        yield from walk(node.inner)


def is_formula_like(text: str) -> bool:
    """A plain string that a spreadsheet would run: a function call or a reference."""

    if not text.lstrip().startswith("="):
        return False
    try:
        node = parse(text)
    except FormulaReferenceError:
        return True
    except FormulaError:
        return False
    return any(isinstance(n, Call | Ref) for n in walk(node))


def map_refs(node: Node, fn: Callable[[Ref], Node]) -> Node:
    """Rebuild `node` with each reference replaced by `fn(ref)`."""

    if isinstance(node, Ref):
        return fn(node)
    if isinstance(node, Unary):
        return Unary(node.op, map_refs(node.operand, fn))
    if isinstance(node, Percent):
        return Percent(map_refs(node.operand, fn))
    if isinstance(node, Binary):
        return Binary(node.op, map_refs(node.left, fn), map_refs(node.right, fn))
    if isinstance(node, Call):
        return Call(node.name, tuple(map_refs(a, fn) for a in node.args))
    if isinstance(node, Group):
        return Group(map_refs(node.inner, fn))
    return node


# --- Checking ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SheetLayout:
    name: str
    columns: int
    data_rows: int
    has_totals: bool

    @property
    def last_data_row(self) -> int:
        return self.data_rows + 1

    @property
    def totals_row(self) -> int | None:
        return self.last_data_row + 1 if self.has_totals and self.data_rows else None

    @property
    def last_row(self) -> int:
        return self.totals_row or self.last_data_row

    def describe(self) -> str:
        rows = (
            f"data rows 2 to {self.last_data_row}" if self.data_rows else "no data rows"
        )
        if self.totals_row:
            rows += f", totals row {self.totals_row}"
        return f"columns A to {column_letters(self.columns)}, {rows}"


def sheet_reference(name: str) -> str:
    """The sheet prefix as Excel writes it: quoted unless a plain ASCII name."""

    if _SIMPLE_SHEET_RE.fullmatch(name) and not _CELL_LIKE_NAME_RE.fullmatch(name):
        if name.upper() not in ("TRUE", "FALSE"):
            return name
    return "'" + name.replace("'", "''") + "'"


def check(
    node: Node,
    layouts: Sequence[SheetLayout],
    here: str,
    *,
    fill_rows: int = 0,
) -> Node:
    """Check functions and references; return the node with canonical sheet names.

    `fill_rows` is how far a column formula is filled down: relative rows are
    checked at the first and the last filled row.
    """

    by_name = {layout.name.casefold(): layout for layout in layouts}
    if fill_rows:
        node = anchor_ranges(node)

    for item in walk(node):
        if isinstance(item, Call):
            _check_call(item)

    def resolve(ref: Ref) -> Node:
        layout = by_name.get((ref.sheet or here).casefold())
        if layout is None:
            names = ", ".join(sheet_reference(x.name) for x in layouts)
            raise FormulaError(
                f"sheet '{ref.sheet}' does not exist in this workbook; its sheets "
                f"are {names}"
            )
        sheet = None if ref.sheet is None or layout.name == here else layout.name
        canonical = replace(ref, sheet=sheet)
        _check_bounds(canonical, layout, here)
        if fill_rows:
            try:
                _check_bounds(shift(canonical, fill_rows), layout, here)
            except FormulaError as exc:
                raise FormulaError(
                    f"{exc} at the last row: this column formula is filled down, so "
                    "a cell every row reads must be written with $ (e.g. $B$2)"
                ) from None
        return canonical

    return map_refs(node, resolve)


def anchor_ranges(node: Node) -> Node:
    """In a filled-down formula, a range written without any `$` is read whole by
    every row (a lookup table, a total): anchor it instead of shifting it."""

    def anchor(ref: Ref) -> Node:
        if not ref.is_range or ref.abs_c1 or ref.abs_r1 or ref.abs_c2 or ref.abs_r2:
            return ref
        return replace(ref, abs_c1=True, abs_r1=True, abs_c2=True, abs_r2=True)

    return map_refs(node, anchor)


def _check_call(call: Call) -> None:
    name = call.name
    if name in DENIED_FUNCTIONS:
        raise FormulaError(f"{name} is not accepted: {DENIED_FUNCTIONS[name]}")
    if name not in FUNCTIONS:
        english = _FRENCH_NAMES.get(name)
        if english:
            raise FormulaError(
                f"use English function names: {english} instead of {name}, with "
                "commas between arguments"
            )
        raise FormulaError(
            f"{name} is not supported. Supported functions: {FUNCTION_FAMILIES}"
        )
    low, high = FUNCTIONS[name]
    count = len(call.args)
    if count < low or (high is not None and count > high):
        expected = (
            f"{low}"
            if low == high
            else f"{low} to {high}"
            if high
            else f"at least {low}"
        )
        raise FormulaError(f"{name} takes {expected} argument(s), got {count}")


def _check_bounds(ref: Ref, layout: SheetLayout, here: str) -> None:
    label = _ref_text(ref, None)
    where = "" if layout.name == here else f"sheet {sheet_reference(layout.name)}: "
    if ref.r1 < 1 or ref.c2 > layout.columns or ref.r2 > layout.last_row:
        raise FormulaError(f"{where}{label} is outside the table ({layout.describe()})")
    totals = layout.totals_row
    if totals and ref.is_range and ref.r1 <= layout.last_data_row < totals <= ref.r2:
        fixed = _ref_text(replace(ref, r2=layout.last_data_row), None)
        raise FormulaError(
            f"{where}{label} would count the totals row {totals} with the data; "
            f"use {fixed}"
        )


def shift(ref: Ref, rows: int) -> Ref:
    if not rows:
        return ref
    return replace(
        ref,
        r1=ref.r1 if ref.abs_r1 else ref.r1 + rows,
        r2=ref.r2 if ref.abs_r2 else ref.r2 + rows,
    )


# --- Emission ------------------------------------------------------------------


def number_text(value: float) -> str:
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value).upper()


def _ref_text(ref: Ref, sheet: str | None) -> str:
    def cell(column: int, row: int, abs_c: bool, abs_r: bool) -> str:
        return (
            f"{'$' if abs_c else ''}{column_letters(column)}{'$' if abs_r else ''}{row}"
        )

    text = cell(ref.c1, ref.r1, ref.abs_c1, ref.abs_r1)
    if ref.is_range:
        text += ":" + cell(ref.c2, ref.r2, ref.abs_c2, ref.abs_r2)
    return (sheet_reference(sheet) + "!" if sheet else "") + text


def _marked_text(ref: Ref) -> str:
    def cell(column: int, row: int, abs_c: bool, abs_r: bool) -> str:
        number = f"{_ROW_MARK}{-row if abs_r else row}{_ROW_MARK}"
        return f"{'$' if abs_c else ''}{column_letters(column)}{'$' if abs_r else ''}{number}"

    text = cell(ref.c1, ref.r1, ref.abs_c1, ref.abs_r1)
    if ref.is_range:
        text += ":" + cell(ref.c2, ref.r2, ref.abs_c2, ref.abs_r2)
    return (sheet_reference(ref.sheet) + "!" if ref.sheet else "") + text


def emit(node: Node, *, stored: bool = False, rows: int = 0) -> str:
    """Formula text with `=`; `stored` adds Excel's prefixes, `rows` fills down."""

    return "=" + _emit(node, stored, rows)


def _emit(node: Node, stored: bool, rows: int) -> str:
    if isinstance(node, Num):
        return number_text(node.value)
    if isinstance(node, Str):
        return '"' + node.value.replace('"', '""') + '"'
    if isinstance(node, Bool):
        return "TRUE" if node.value else "FALSE"
    if isinstance(node, Err):
        return node.code
    if isinstance(node, Missing):
        return ""
    if isinstance(node, Ref):
        return _ref_text(shift(node, rows), node.sheet)
    if isinstance(node, _MarkedRef):
        return _marked_text(node.ref)
    if isinstance(node, Unary):
        return node.op + _emit(node.operand, stored, rows)
    if isinstance(node, Percent):
        return _emit(node.operand, stored, rows) + "%"
    if isinstance(node, Binary):
        return (
            _emit(node.left, stored, rows) + node.op + _emit(node.right, stored, rows)
        )
    if isinstance(node, Group):
        return "(" + _emit(node.inner, stored, rows) + ")"
    prefix = _STORED_PREFIX.get(node.name, "") if stored else ""
    args = ",".join(_emit(arg, stored, rows) for arg in node.args)
    return f"{prefix}{node.name}({args})"


_ROW_MARK = "\x00"


def fill_down(node: Node, *, stored: bool = False) -> Callable[[int], str]:
    """Text of a column formula `rows` below its first data row, emitted once."""

    def mark(ref: Ref) -> Node:
        return cast(Node, _MarkedRef(ref))

    text = "=" + _emit(map_refs(node, mark), stored, 0)
    parts = text.split(_ROW_MARK)
    if len(parts) == 1:
        return lambda rows: text
    pieces = parts[0::2]
    bases = [int(x) for x in parts[1::2]]

    def at(rows: int) -> str:
        out = [pieces[0]]
        for base, piece in zip(bases, pieces[1:], strict=True):
            out.append(str(base + rows) if base > 0 else str(-base))
            out.append(piece)
        return "".join(out)

    return at


@dataclass(frozen=True, slots=True)
class _MarkedRef:
    """A reference whose relative rows are emitted as markers (positive base) and
    absolute rows as negated numbers, so `fill_down` substitutes them as text."""

    ref: Ref


def uses_dynamic_arrays(node: Node) -> bool:
    return any(
        isinstance(n, Call) and n.name in DYNAMIC_ARRAY_FUNCTIONS for n in walk(node)
    )


def row_template(node: Node, placeholder: str) -> str | None:
    """The formula with `placeholder` for its own row, when every relative row is
    the first data row (2); None when it reads other rows relatively."""

    if any(
        isinstance(n, Ref)
        and ((not n.abs_r1 and n.r1 != 2) or (not n.abs_r2 and n.r2 != 2))
        for n in walk(node)
    ):
        return None
    marker = 900_000  # a row number no checked formula can hold
    text = emit(node, rows=marker - 2)
    return text.replace(str(marker), placeholder)
