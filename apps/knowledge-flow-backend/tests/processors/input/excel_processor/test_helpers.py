# Copyright Thales 2025
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

"""
Niveau 1 — tests unitaires des fonctions pures (helpers de `excel_extractor`).

Chaque helper est testé en isolation, sans I/O ni classeur.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from knowledge_flow_backend.core.processors.input.excel_processor import excel_extractor as ee
from knowledge_flow_backend.core.processors.input.excel_processor.excel_processor import ExcelProcessor


# --------------------------------------------------------------------------- #
# _nonempty
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, expected",
    [
        (None, False),
        (float("nan"), False),
        ("", False),
        ("   ", False),
        ("\t", False),
        (0, True),  # 0 EST une valeur (pas vide)
        (False, True),
        ("x", True),
        (3.14, True),
        ("  a  ", True),
    ],
)
def test_nonempty(value, expected):
    assert ee._nonempty(value) is expected


# --------------------------------------------------------------------------- #
# _is_number / _is_data_like
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, expected",
    [
        (1, True),
        (1.5, True),
        (-3, True),
        (0, True),
        (True, False),  # un booléen n'est pas un nombre
        (False, False),
        (float("nan"), False),  # NaN exclu
        ("1", False),
        (None, False),
        (dt.date(2024, 1, 1), False),
    ],
)
def test_is_number(value, expected):
    assert ee._is_number(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (10, True),
        (1.5, True),
        (dt.date(2024, 1, 1), True),
        (dt.datetime(2024, 1, 1, 12), True),
        ("texte", False),
        (None, False),
        (True, False),
    ],
)
def test_is_data_like(value, expected):
    assert ee._is_data_like(value) is expected


# --------------------------------------------------------------------------- #
# _format_hides_value — masquage par format de nombre Excel
# --------------------------------------------------------------------------- #
def test_format_hides_zero_with_empty_section():
    # format '0;\-0;;' : section "zéro" vide → 0 masqué
    assert ee._format_hides_value(0, "0;\\-0;;") is True


def test_format_does_not_hide_positive():
    assert ee._format_hides_value(5, "0;\\-0;;") is False


def test_format_does_not_hide_negative():
    # négatif : section 2 (« \-0 »), non vide → visible
    assert ee._format_hides_value(-5, "0;\\-0;;") is False


def test_format_two_sections_zero_follows_positive():
    # 2 sections : le 0 suit la section positive (idx 0)
    assert ee._format_hides_value(0, ";0") is True  # section positive vide
    assert ee._format_hides_value(5, ";0") is True
    assert ee._format_hides_value(-5, ";0") is False


def test_format_single_section_general():
    assert ee._format_hides_value(0, "General") is False


def test_format_ignored_for_non_numbers():
    assert ee._format_hides_value("texte", "0;\\-0;;") is False
    assert ee._format_hides_value(None, "0;\\-0;;") is False


def test_format_none_returns_false():
    assert ee._format_hides_value(5, None) is False


# --------------------------------------------------------------------------- #
# _a1 — coords 0-indexées → notation Excel
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "coords, expected",
    [
        ((0, 0, 0, 0), "A1:A1"),
        ((0, 0, 4, 4), "A1:E5"),
        ((5, 1, 9, 3), "B6:D10"),
        ((0, 26, 0, 26), "AA1:AA1"),
    ],
)
def test_a1(coords, expected):
    assert ee._a1(*coords) == expected


# --------------------------------------------------------------------------- #
# _despace_thousands — retire UNIQUEMENT les espaces de groupement des milliers
# (monnaie, %, virgule décimale conservés)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token, expected",
    [
        ("1 200", "1200"),  # séparateur de milliers (espace)
        ("1 200", "1200"),  # espace insécable
        ("1 234 567", "1234567"),  # plusieurs groupes
        ("1 234,56 €", "1234,56 €"),  # milliers retirés, € + virgule gardés
        ("15 %", "15 %"),  # espace avant % (pas entre chiffres) gardé
        ("1,50 €", "1,50 €"),  # rien à retirer
        ("abc", "abc"),  # texte inchangé
    ],
)
def test_despace_thousands(token, expected):
    assert ee._despace_thousands(token) == expected


# --------------------------------------------------------------------------- #
# _looks_numeric — reconnaissance d'un token numérique (monnaie/%/locale tolérés)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token, expected",
    [
        ("1,50 €", True),  # monnaie + virgule décimale FR
        ("1 200", True),  # séparateur de milliers
        ("15%", True),  # pourcentage
        ("-42", True),
        ("3.14", True),
        ("01000", True),  # zéros de tête : numérique au sens reconnaissance
        ("£1,000.5", False),  # point ET virgule → ambigu
        ("01/03/2024", False),  # date, pas un nombre
        ("abc", False),
    ],
)
def test_looks_numeric(token, expected):
    assert ee._looks_numeric(token) is expected


@pytest.mark.parametrize("token", ["", "-", "–", "N/A", "NA", "n/a", "TBD"])
def test_looks_numeric_sentinels(token):
    assert ee._looks_numeric(token) is False


# --------------------------------------------------------------------------- #
# _residual_value — déroulé des valeurs d'un résidu (helper du processeur)
# --------------------------------------------------------------------------- #
def test_residual_value_none():
    assert ExcelProcessor._residual_value(None) == ""


def test_residual_value_single():
    assert ExcelProcessor._residual_value("OK") == '  value="OK"'


def test_residual_value_single_from_grid():
    assert ExcelProcessor._residual_value([["OK"]]) == '  value="OK"'


def test_residual_value_multiple_unrolled():
    out = ExcelProcessor._residual_value([["Sous-total", 240]])
    assert "Sous-total" in out and "240" in out
    assert out.startswith('  value="\n')


def test_residual_value_splits_internal_newlines():
    out = ExcelProcessor._residual_value("ligne1\nligne2")
    assert "ligne1" in out and "ligne2" in out


# --------------------------------------------------------------------------- #
# _safe_filename — id de tableau -> nom de fichier
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, expected",
    [
        ("Synthèse.t1", "Synthese.t1"),  # accents repliés en ASCII
        ("Séparateur 80%.t1", "Separateur_80_.t1"),
        ("a/b\\c", "a_b_c"),
        ("___", "table"),  # rien d'utilisable → fallback
        ("日本語", "table"),  # tout non-ASCII → repli vide → fallback
    ],
)
def test_safe_filename(name, expected):
    assert ExcelProcessor._safe_filename(name) == expected


# --------------------------------------------------------------------------- #
# _normalize_newlines — uniformisation des sauts de ligne intra-cellule
# --------------------------------------------------------------------------- #
def test_normalize_newlines():
    df = pd.DataFrame({"a": ["x\r\ny", "p\rq", "k\nm"], "b": [1, 2, 3]})
    out = ExcelProcessor._normalize_newlines(df)
    assert list(out["a"]) == ["x\ny", "p\nq", "k\nm"]
    # les non-chaînes sont inchangées
    assert list(out["b"]) == [1, 2, 3]
