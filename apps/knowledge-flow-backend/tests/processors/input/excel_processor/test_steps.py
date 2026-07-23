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
Niveau 2 — tests unitaires des étapes du pipeline prises isolément.

Les étapes A (document/feuille) sont exercées via de petits classeurs ciblés
(fixture `make_extractor`, qui câble l'extracteur comme le fait le processeur).
Les étapes B (par tableau) sont exercées sur des `DetectedTable` construits à la
main (fixture `make_table`), sans I/O.
"""

from __future__ import annotations

import pandas as pd
import pytest

from knowledge_flow_backend.core.processors.input.excel_processor import excel_extractor as ee


# ========================================================================== #
# A1 — inventaire
# ========================================================================== #
def test_a1_inventory_basic(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "x", "B1": 1, "A2": "y", "B2": 2},
            }
        ]
    )
    summaries = ext.a1_inventory()
    assert len(summaries) == 1
    s = summaries[0]
    assert s.name == "F1"
    assert s.visible is True
    assert s.has_formulas is False
    assert s.n_merges == 0


def test_a1_detects_formulas_and_merges(make_extractor):
    # une vraie fusion + une formule
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "titre", "A2": "v", "B2": 1, "C2": "=B2*2"},
                "merges": ["A1:C1"],
            }
        ]
    )
    s = ext.a1_inventory()[0]
    assert s.has_formulas is True
    assert s.n_merges == 1


def test_a1_hidden_sheet_flagged(make_extractor):
    ext = make_extractor(
        [
            {"name": "Visible", "cells": {"A1": 1}},
            {"name": "Cachee", "cells": {"A1": 1}, "state": "hidden"},
        ]
    )
    summaries = ext.a1_inventory()
    by = {s.name: s for s in summaries}
    assert by["Visible"].visible is True
    assert by["Cachee"].visible is False


def test_a1_sheets_filter_unknown_raises(make_extractor):
    ext = make_extractor([{"name": "F1", "cells": {"A1": 1}}], sheets=["Inexistante"])
    with pytest.raises(ValueError, match="not found"):
        ext.a1_inventory()


def test_a1_sheets_filter_selects_subset(make_extractor):
    ext = make_extractor(
        [
            {"name": "Garde", "cells": {"A1": 1}},
            {"name": "Ignore", "cells": {"A1": 1}},
        ],
        sheets=["Garde"],
    )
    summaries = ext.a1_inventory()
    assert [s.name for s in summaries] == ["Garde"]


# ========================================================================== #
# A2 — chargement & capture
# ========================================================================== #
def test_a2_reads_grid_and_merges(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "titre", "A2": "h", "B2": "i", "A3": 1, "B3": 2},
                "merges": ["A1:B1"],
            }
        ]
    )
    ext.a1_inventory()
    grid, structure = ext.a2_load_and_capture("F1")
    assert grid.shape == (3, 2)
    assert grid[0, 0] == "titre"
    assert (0, 0, 0, 1) in structure["merges"]


def test_a2_format_masking_hides_zero(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "x", "B1": 0, "A2": "y", "B2": 5},
                "number_formats": {"B1": "0;\\-0;;"},
            }
        ],
        apply_format_masking=True,
    )
    ext.a1_inventory()
    grid, _ = ext.a2_load_and_capture("F1")
    assert grid[0, 1] is None  # 0 masqué par le format → traité comme vide
    assert grid[1, 1] == 5


def test_a2_format_masking_disabled_keeps_zero(make_extractor):
    # B2=5 ancre la colonne B (un 0 isolé serait rogné par _real_extent, qui
    # ignore les lignes/colonnes de zéros en fin de feuille). Ici on vérifie que,
    # masquage désactivé, le 0 de B1 est conservé BRUT (et non masqué en None
    # comme le ferait le format « 0;\-0;; » sur le chemin de masquage).
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "x", "B1": 0, "A2": "y", "B2": 5},
                "number_formats": {"B1": "0;\\-0;;"},
            }
        ],
        apply_format_masking=False,
    )
    ext.a1_inventory()
    grid, _ = ext.a2_load_and_capture("F1")
    assert grid[0, 1] == 0  # chemin rapide : valeur brute conservée
    assert grid[1, 1] == 5


def test_a2_show_zeros_false_hides_all_zeros(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "x", "B1": 0, "C1": 7},
                "show_zeros": False,
            }
        ],
        apply_format_masking=True,
    )
    ext.a1_inventory()
    grid, _ = ext.a2_load_and_capture("F1")
    assert grid[0, 1] is None  # réglage feuille « afficher un zéro » décoché
    assert grid[0, 2] == 7


def test_a2_captures_error_cells(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": "x", "B1": "#DIV/0!", "C1": "#REF!", "D1": "ok"},
            }
        ]
    )
    ext.a1_inventory()
    _, structure = ext.a2_load_and_capture("F1")
    assert (0, 1) in structure["errors"]
    assert (0, 2) in structure["errors"]
    assert (0, 3) not in structure["errors"]


def test_a2_hidden_cells_detected_when_excluded(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {"A1": 1, "B1": 2, "C1": 3},
                "hidden_cols": ["B"],
                "hidden_rows": [1],
            }
        ],
        include_hidden_cells=False,
    )
    ext.a1_inventory()
    _, structure = ext.a2_load_and_capture("F1")
    assert 1 in structure["hidden_cols"]  # colonne B (index 1)
    assert 0 in structure["hidden_rows"]  # ligne 1 (index 0)


# ========================================================================== #
# A3 — détection des tableaux (composantes connexes)
# ========================================================================== #
def _detect(ext, sheet):
    ext.a1_inventory()
    grid, structure = ext.a2_load_and_capture(sheet)
    return ext.a3_detect_tables(sheet, grid, structure)


def test_a3_two_blocks_separated_by_empty_row(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "h1",
                    "B1": "h2",
                    "A2": 1,
                    "B2": 2,
                    # ligne 3 vide
                    "A4": "g1",
                    "B4": "g2",
                    "A5": 3,
                    "B5": 4,
                },
            }
        ]
    )
    candidates, residuals = _detect(ext, "F1")
    assert len(candidates) == 2


def test_a3_isolated_cell_is_residual(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "h1",
                    "B1": "h2",
                    "A2": 1,
                    "B2": 2,
                    "E10": "note isolée",
                },
            }
        ]
    )
    candidates, residuals = _detect(ext, "F1")
    assert len(candidates) == 1
    assert any(r.type == "isolated_cell" for r in residuals)


def test_a3_small_block_is_non_tabular_residual(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "h1",
                    "B1": "h2",
                    "A2": 1,
                    "B2": 2,
                    "A5": "sous-total",
                    "B5": 240,  # 1 ligne, 2 cellules → < 4 cellules
                },
            }
        ]
    )
    candidates, residuals = _detect(ext, "F1")
    assert any(r.type == "non_tabular_block" for r in residuals)


def test_a3_hidden_middle_column_segments_block(make_extractor):
    # Colonne B masquée AU MILIEU : A | C,D → le run le plus large (C,D) est gardé.
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "x",
                    "B1": "cache",
                    "C1": "h1",
                    "D1": "h2",
                    "A2": "y",
                    "B2": "cache",
                    "C2": 1,
                    "D2": 2,
                    "A3": "z",
                    "B3": "cache",
                    "C3": 3,
                    "D3": 4,
                },
                "hidden_cols": ["B"],
            }
        ],
        include_hidden_cells=False,
        split_on_hidden_columns=True,
    )
    candidates, _ = _detect(ext, "F1")
    assert len(candidates) == 1
    cb = candidates[0]
    # colonnes feuille retenues = C, D (indices 2, 3)
    assert cb.col_abs == [2, 3]


# ========================================================================== #
# A4 — découpe des tableaux empilés
# ========================================================================== #
def test_a4_splits_stacked_tables_with_title(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "Tableau A",
                    "A2": "Produit",
                    "B2": "Q1",
                    "C2": "Q2",
                    "D2": "Q3",
                    "A3": "Stylo",
                    "B3": 1,
                    "C3": 2,
                    "D3": 3,
                    "A4": "Cahier",
                    "B4": 4,
                    "C4": 5,
                    "D4": 6,
                    "A5": "Tableau B",
                    "A6": "Produit",
                    "B6": "X",
                    "C6": "Y",
                    "D6": "Z",
                    "A7": "Gomme",
                    "B7": 7,
                    "C7": 8,
                    "D7": 9,
                    "A8": "Règle",
                    "B8": 1,
                    "C8": 2,
                    "D8": 3,
                },
                "merges": ["A1:D1", "A5:D5"],
            }
        ]
    )
    ext.a1_inventory()
    grid, structure = ext.a2_load_and_capture("F1")
    candidates, _ = ext.a3_detect_tables("F1", grid, structure)
    tables, _ = ext.a4_split_stacked_tables(candidates)
    assert len(tables) == 2
    assert tables[0].title == "Tableau A"
    assert tables[1].title == "Tableau B"
    # ids contigus par feuille
    assert tables[0].id == "F1.t1"
    assert tables[1].id == "F1.t2"


def test_a4_context_lines_attached(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "Titre",
                    "A2": "Contexte sous-titre",
                    "A3": "Produit",
                    "B3": "Q1",
                    "C3": "Q2",
                    "D3": "Q3",
                    "A4": "Stylo",
                    "B4": 1,
                    "C4": 2,
                    "D4": 3,
                    "A5": "Cahier",
                    "B5": 4,
                    "C5": 5,
                    "D5": 6,
                },
                "merges": ["A1:D1", "A2:D2"],
            }
        ]
    )
    ext.a1_inventory()
    grid, structure = ext.a2_load_and_capture("F1")
    candidates, _ = ext.a3_detect_tables("F1", grid, structure)
    tables, _ = ext.a4_split_stacked_tables(candidates)
    assert len(tables) == 1
    assert tables[0].title == "Titre"
    assert tables[0].context == ["Contexte sous-titre"]


def test_a4_orphan_title_residual_when_kept(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "Produit",
                    "B1": "Q1",
                    "C1": "Q2",
                    "D1": "Q3",
                    "A2": "Stylo",
                    "B2": 1,
                    "C2": 2,
                    "D2": 3,
                    "A3": "Cahier",
                    "B3": 4,
                    "C3": 5,
                    "D3": 6,
                    "A4": "Note de bas — titre orphelin",
                },
                "merges": ["A4:D4"],
            }
        ],
        keep_split_residuals=True,
    )
    ext.a1_inventory()
    grid, structure = ext.a2_load_and_capture("F1")
    candidates, _ = ext.a3_detect_tables("F1", grid, structure)
    tables, residuals = ext.a4_split_stacked_tables(candidates)
    assert len(tables) == 1
    assert any(r.type == "free_title" for r in residuals)


# ========================================================================== #
# A5 — retrait des colonnes-étiquettes
# ========================================================================== #
def test_a5_strips_one_label_column(make_extractor, make_table):
    ext = make_extractor([{"name": "F1", "cells": {"A1": 1}}])  # extracteur minimal
    # corps 5 lignes ; colonne 0 = une fusion verticale couvrant tout (étiquette)
    grid = [
        ["Papeterie", "Produit", "Prix"],
        [None, "Stylo", 1.5],
        [None, "Cahier", 2.0],
        [None, "Gomme", 0.8],
        [None, "Règle", 1.2],
    ]
    t = make_table(grid, merges=[(0, 0, 4, 0)], data_bbox=(0, 0, 4, 2))
    ext.a5_strip_leading_label_columns([t])
    assert t.grid.shape == (5, 2)
    assert t.context == ["Papeterie"]
    # bord gauche des données décalé d'une colonne
    assert t.data_bbox[1] == 1


def test_a5_strips_two_label_columns(make_extractor, make_table):
    ext = make_extractor([{"name": "F1", "cells": {"A1": 1}}])
    grid = [
        ["Nord", "Lille", "Produit", "Quantité"],
        [None, None, "Stylo", 500],
        [None, None, "Cahier", 300],
        [None, None, "Gomme", 120],
        [None, None, "Règle", 90],
    ]
    t = make_table(grid, merges=[(0, 0, 4, 0), (0, 1, 4, 1)], data_bbox=(0, 0, 4, 3))
    ext.a5_strip_leading_label_columns([t])
    assert t.grid.shape == (5, 2)
    assert t.context == ["Nord", "Lille"]


def test_a5_no_label_column_unchanged(make_extractor, make_table):
    ext = make_extractor([{"name": "F1", "cells": {"A1": 1}}])
    grid = [
        ["Produit", "Prix"],
        ["Stylo", 1.5],
        ["Cahier", 2.0],
    ]
    t = make_table(grid, merges=[], data_bbox=(0, 0, 2, 1))
    ext.a5_strip_leading_label_columns([t])
    assert t.grid.shape == (3, 2)
    assert t.context == []


# ========================================================================== #
# B1 — orientation
# ========================================================================== #
def test_b1_normal_orientation(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    t = make_table(
        [
            ["Produit", "Ventes"],
            ["Stylo", 100],
            ["Cahier", 90],
        ]
    )
    p.b1_detect_orientation(t)
    assert t.orientation == "normal"


def test_b1_transposed_orientation(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    # en-tête numérique (années) + 1re colonne texte, plus large que haut
    t = make_table(
        [
            ["Indicateur", 2021, 2022, 2023, 2024],
            ["CA", 100, 120, 150, 170],
            ["Charges", 80, 90, 100, 110],
            ["Résultat", 20, 30, 50, 60],
        ]
    )
    p.b1_detect_orientation(t)
    assert t.orientation == "transposed"
    # straightened: the grid has been transposed
    assert t.grid.shape == (5, 4)


def test_b1_crossed_orientation(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    # en-tête numérique + 1re colonne texte MAIS trop haut (lignes > colonnes+1)
    rows = [["Mois", 2022, 2023]]
    for m, a, b in [("Jan", 1, 2), ("Fév", 3, 4), ("Mar", 5, 6), ("Avr", 7, 8), ("Mai", 9, 10), ("Jun", 11, 12)]:
        rows.append([m, a, b])
    t = make_table(rows)
    p.b1_detect_orientation(t)
    assert t.orientation == "cross-tab"


# ========================================================================== #
# B2 — conversion en DataFrame
# ========================================================================== #
def test_b2_autofill_and_dataframe(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    p.keep_headerless_columns = True
    t = make_table(
        [
            ["Région", "Ville", "Ventes"],
            ["Nord", "Lille", 1250],
            [None, "Lens", 1180],  # « Nord » à auto-remplir depuis la fusion
        ],
        merges=[(1, 0, 2, 0)],
    )
    p.b2_to_dataframe(t)
    assert list(t.df.columns) == ["Région", "Ville", "Ventes"]
    assert t.df.shape == (2, 3)
    assert t.df.iloc[1]["Région"] == "Nord"  # cellule fusionnée remplie
    assert t.has_column_names is True


def test_b2_dedup_and_empty_header_names(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    p.keep_headerless_columns = True
    t = make_table(
        [
            ["Montant", "Montant", None, "Montant"],
            [10, 20, 30, 40],
            [11, 21, 31, 41],
        ]
    )
    p.b2_to_dataframe(t)
    assert list(t.df.columns) == ["Montant", "Montant.1", "col_2", "Montant.2"]


def test_b2_headerless_table_flagged(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    p.keep_headerless_columns = True
    # 1re ligne entièrement VIDE → aucun libellé → en-tête auto-généré « col_… »
    # (un nombre est une valeur « non vide » et compte donc comme un nom de colonne)
    t = make_table(
        [
            [None, None, None],
            [4, 5, 6],
        ]
    )
    p.b2_to_dataframe(t)
    assert t.has_column_names is False
    assert all(c.startswith("col_") for c in t.df.columns)


def test_b2_single_row_raises(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    t = make_table([["a", "b"]])
    with pytest.raises(ValueError):
        p.b2_to_dataframe(t)


# ========================================================================== #
# B3 — lignes/colonnes vides + état
# ========================================================================== #
def _pipeline_for_b(**kwargs):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    p.drop_empty_rows = kwargs.get("drop_empty_rows", True)
    p.drop_empty_cols = kwargs.get("drop_empty_cols", True)
    p.coerce_types = kwargs.get("coerce_types", True)
    return p


def test_b3_drops_empty_rows_and_cols(make_table):
    p = _pipeline_for_b()
    t = make_table([["h1", "h2"]])
    t.df = pd.DataFrame({"a": [1, None, 3], "b": [None, None, None]})
    p.b3_check_empty(t)
    assert "b" not in t.df.columns  # colonne entièrement vide supprimée
    assert len(t.df) == 2  # ligne entièrement vide supprimée
    assert t.etat == "non-empty"


def test_b3_empty_dataframe_marked_empty(make_table):
    p = _pipeline_for_b()
    t = make_table([["h1", "h2"]])
    t.df = pd.DataFrame({"a": [None, None], "b": [None, None]})
    p.b3_check_empty(t)
    assert t.etat == "empty"


def test_b3_keep_rows_when_disabled(make_table):
    p = _pipeline_for_b(drop_empty_rows=False, drop_empty_cols=False)
    t = make_table([["h"]])
    t.df = pd.DataFrame({"a": [1, None, 3]})
    p.b3_check_empty(t)
    assert len(t.df) == 3


# ========================================================================== #
# B4 — coercition des types
# ========================================================================== #
def test_b4_numeric_keeps_currency_percent_strips_thousands(make_table):
    p = _pipeline_for_b()
    t = make_table([["h"]])
    t.df = pd.DataFrame(
        {
            "Prix": ["1,50 €", "2,00 €", "0,80 €"],
            "Remise": ["15%", "5%", "0%"],
            "Quantité": ["1 200", "12 000", "8 500"],
        }
    )
    p.b4_clean_and_coerce(t)
    # monnaie, %, virgule décimale conservés ; valeurs restent des chaînes
    assert list(t.df["Prix"]) == ["1,50 €", "2,00 €", "0,80 €"]
    assert list(t.df["Remise"]) == ["15%", "5%", "0%"]
    # seuls les espaces de groupement des milliers sont retirés
    assert list(t.df["Quantité"]) == ["1200", "12000", "8500"]


def test_b4_boolean_column_not_coerced(make_table):
    # La branche booléenne a été supprimée : oui/non reste du texte.
    p = _pipeline_for_b()
    t = make_table([["h"]])
    t.df = pd.DataFrame({"Dispo": ["oui", "non", "oui"]})
    p.b4_clean_and_coerce(t)
    assert list(t.df["Dispo"]) == ["oui", "non", "oui"]


def test_b4_date_text_column(make_table):
    p = _pipeline_for_b()
    t = make_table([["h"]])
    t.df = pd.DataFrame({"Date_MAJ": ["01/03/2024", "15/06/2024", "31/12/2023"]})
    p.b4_clean_and_coerce(t)
    assert t.df["Date_MAJ"].iloc[0] == pd.Timestamp("2024-03-01")


def test_b4_leading_zeros_preserved_as_string(make_table):
    # Plus de branche « identifiant », mais comme on ne convertit plus en
    # nombre, les zéros de tête sont naturellement préservés (valeur = chaîne).
    p = _pipeline_for_b()
    t = make_table([["h"]])
    t.df = pd.DataFrame({"Code_Postal": ["01000", "75001", "06000"]})
    p.b4_clean_and_coerce(t)
    assert list(t.df["Code_Postal"]) == ["01000", "75001", "06000"]


def test_b4_unconvertible_value_preserved(make_table):
    p = _pipeline_for_b()
    t = make_table([["h"]])
    # ≥70 % numérique (3/4) → colonne reconnue numérique ; la valeur texte non
    # numérique est conservée telle quelle au lieu d'être détruite.
    t.df = pd.DataFrame({"Val": ["10", "20", "30", "indéterminé"]})
    p.b4_clean_and_coerce(t)
    assert t.df["Val"].iloc[0] == "10"  # chaîne, pas de conversion
    assert t.df["Val"].iloc[3] == "indéterminé"  # jamais détruite


def test_b4_disabled_keeps_raw(make_table):
    p = _pipeline_for_b(coerce_types=False)
    t = make_table([["h"]])
    t.df = pd.DataFrame({"Prix": ["1,50 €", "2,00 €"]})
    p.b4_clean_and_coerce(t)
    assert list(t.df["Prix"]) == ["1,50 €", "2,00 €"]  # aucune conversion


# ========================================================================== #
# B5 — provenance
# ========================================================================== #
def test_b5_attaches_provenance(make_table):
    p = ee.ExcelExtractor.__new__(ee.ExcelExtractor)
    p.path = "/chemin/source.xlsx"
    t = make_table([["h1", "h2"], [1, 2]], sheet="MaFeuille")
    t.df = pd.DataFrame({"h1": [1], "h2": [2]})
    t.title = "Titre"
    p.b5_validate_and_tag(t)
    prov = t.provenance
    assert prov["file"] == "/chemin/source.xlsx"
    assert prov["sheet"] == "MaFeuille"
    assert prov["title"] == "Titre"
    assert set(prov) >= {"file", "sheet", "range", "orientation", "state"}
    # provenance also attached to the DataFrame
    assert t.df.attrs["provenance"] == prov
