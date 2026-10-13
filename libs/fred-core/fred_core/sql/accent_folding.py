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


def fold_text(value: str) -> str:
    """Fold a search string exactly as `fold_accents` folds a column."""
    # Composed first so a letter typed as base + combining mark folds like the stored one.
    return unicodedata.normalize("NFC", value).translate(_PYTHON_TABLE).lower()


class fold_accents(FunctionElement[str]):
    """Lower-cased column text with the letters of `FOLDED_LETTERS` unaccented."""

    type = String()
    inherit_cache = True
    name = "fold_accents"


@compiles(fold_accents)
def _fold_with_replace(element: fold_accents, compiler: Any, **kw: Any) -> str:
    # No translate() outside PostgreSQL: one replace per letter, as text (nested constructs
    # overflow the compiler). SQLite's lower() is ASCII-only, so other scripts stay case-sensitive there.
    (value,) = element.clauses
    folded = compiler.process(func.lower(value), **kw)
    for accented, plain in FOLDED_LETTERS.items():
        folded = f"replace({folded}, '{accented}', '{plain}')"
    return folded


@compiles(fold_accents, "postgresql")
def _fold_with_translate(element: fold_accents, compiler: Any, **kw: Any) -> str:
    (value,) = element.clauses
    return compiler.process(func.translate(func.lower(value), _ACCENTED, _PLAIN), **kw)
