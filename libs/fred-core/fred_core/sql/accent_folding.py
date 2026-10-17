# SPDX-License-Identifier: Apache-2.0
"""Accent- and case-insensitive text matching that needs no database extension."""

import unicodedata
from typing import Any

from sqlalchemy import String, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement


def _folding_table() -> dict[str, str]:
    """Latin-1 and Latin Extended-A letters that are an ASCII letter plus marks."""
    table: dict[str, str] = {}
    for code in range(0x00C0, 0x0180):
        base, *marks = unicodedata.normalize("NFD", chr(code))
        if marks and base.isascii() and all(map(unicodedata.combining, marks)):
            table[chr(code)] = base.lower()
    return table


FOLDED_LETTERS = _folding_table()
_ACCENTED = "".join(FOLDED_LETTERS)
_PLAIN = "".join(FOLDED_LETTERS.values())
_PYTHON_TABLE = str.maketrans(FOLDED_LETTERS)
# What an ASCII-only lower() changes (SQLite, PostgreSQL under a C/POSIX LC_CTYPE).
_ASCII_LOWER = str.maketrans({chr(code): chr(code + 32) for code in range(65, 91)})


def fold_text(value: str) -> str:
    """Fold text as `fold_accents` does where the database lower() knows Unicode."""
    # Composed first so a letter typed as base + combining mark folds like the stored one.
    return unicodedata.normalize("NFC", value).translate(_PYTHON_TABLE).lower()


def search_spellings(value: str) -> tuple[str, ...]:
    """Spellings of a search text for the database to fold through `fold_accents`.

    Composed (NFC) only. A capital an ASCII-only lower() would keep also goes in
    lower case, so text stored in lower case is still found.
    """
    typed = unicodedata.normalize("NFC", value)
    ascii_folded = typed.translate(_PYTHON_TABLE).translate(_ASCII_LOWER)
    kept_capital = ascii_folded != fold_text(typed)
    return (typed, typed.lower()) if kept_capital else (typed,)


class fold_accents(FunctionElement[str]):
    """Lower-cased column text with the letters of `FOLDED_LETTERS` unaccented."""

    type = String()
    inherit_cache = True
    name = "fold_accents"


@compiles(fold_accents)
def _fold_with_replace(element: fold_accents, compiler: Any, **kw: Any) -> str:
    # No translate() outside PostgreSQL: one replace per letter, as text (nested constructs
    # overflow the compiler). Letters outside the table take the case folding of the database lower().
    (value,) = element.clauses
    folded = compiler.process(func.lower(value), **kw)
    for accented, plain in FOLDED_LETTERS.items():
        folded = f"replace({folded}, '{accented}', '{plain}')"
    return folded


@compiles(fold_accents, "postgresql")
def _fold_with_translate(element: fold_accents, compiler: Any, **kw: Any) -> str:
    (value,) = element.clauses
    return compiler.process(func.translate(func.lower(value), _ACCENTED, _PLAIN), **kw)


@compiles(fold_accents, "sqlite")
def _fold_sqlite(element: fold_accents, compiler: Any, **kw: Any) -> str:
    # Older SQLite builds have a fixed parser stack: 161 nested replace() calls
    # overflow it. Sibling CTEs keep each parsed expression shallow, without a
    # connection-specific SQL function or a change to SQLite's case semantics.
    (value,) = element.clauses
    initial = compiler.process(func.lower(value), **kw)
    stages = [f"_fred_fold_0(v) AS (SELECT {initial})"]
    letters = list(FOLDED_LETTERS.items())
    for stage, start in enumerate(range(0, len(letters), 16), 1):
        folded = "v"
        for accented, plain in letters[start : start + 16]:
            folded = f"replace({folded}, '{accented}', '{plain}')"
        # Only integer stage IDs and the fixed folding table form this SQL.
        stages.append(
            f"_fred_fold_{stage}(v) AS (SELECT {folded} FROM _fred_fold_{stage - 1})"  # nosec B608
        )
    # The input expression is compiled by SQLAlchemy; user search text stays
    # bound separately. Only compiler-generated stages are joined here.
    return f"(WITH {', '.join(stages)} SELECT v FROM _fred_fold_{len(stages) - 1})"  # nosec B608
