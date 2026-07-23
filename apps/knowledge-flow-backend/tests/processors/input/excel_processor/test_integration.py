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
Niveau 3 — tests d'intégration : extraction COMPLÈTE sur le classeur de démo.

Le classeur est construit par `build_test_excel.build_demo_workbook` puis traité
une seule fois (fixture `demo_run`, scope session). Chaque test vérifie le
résultat attendu d'une feuille, tel que documenté dans build_test_excel.py.

Config canonique : include_hidden_cells=False, coerce_types=True, recalc=True.
Les tests appuyés sur `demo_run` sont skippés si LibreOffice est absent
(recalc). Les tests d'options n'utilisant pas recalc tournent hors-ligne.
"""

from __future__ import annotations

import pandas as pd
import pytest

from knowledge_flow_backend.core.processors.input.excel_processor.excel_processor import ExcelProcessor

# --------------------------------------------------------------------------- #
# Vue d'ensemble
# --------------------------------------------------------------------------- #
EXPECTED_SHEETS = [
    "Synthèse",
    "Empilés",
    "Séparateur 80%",
    "Colonnes-étiquettes",
    "Transposée",
    "Croisée",
    "Typage",
    "Entêtes",
    "Formules",
    "Résidus",
    "Découpe",
    "Compaction",
    "Brouillon",
]


def test_all_sheets_present(demo_run):
    assert [s.name for s in demo_run.summaries] == EXPECTED_SHEETS


def test_total_table_count(demo_run):
    total = sum(len(s.tables) for s in demo_run.summaries)
    # 2+2+2+2+1+1+1+1+1+1+1+1+1
    assert total == 17


# --------------------------------------------------------------------------- #
# Synthèse — interaction colonnes masquées (C et F cachées sur toute la feuille)
# --------------------------------------------------------------------------- #
def test_synthese_hidden_columns_segment_tables(demo_run):
    s = demo_run.by_name["Synthèse"]
    assert len(s.tables) == 2
    t1, t2 = s.tables
    # Tableau 1 (A1:G4) : C et F masquées coupent en runs [A,B] [D,E] [G] ;
    # égalité de largeur → le run le plus à DROITE (D,E) est retenu.
    assert t1.plage == "A1:G4"
    assert t1.plage_donnees == "D1:E4"
    assert list(t1.df.columns) == ["Ventes_2024", "Croissance"]
    # Tableau 2 (A6:D10) : colonne C masquée → runs [A,B] [D] → [A,B] retenu.
    assert t2.plage_donnees == "A6:B10"
    assert list(t2.df.columns) == ["Région", "Ville"]
    assert s.coverage == 1.0


# --------------------------------------------------------------------------- #
# Empilés — découpe par ligne-titre fusionnée pleine largeur
# --------------------------------------------------------------------------- #
def test_empiles_two_tables_with_title_and_context(demo_run):
    s = demo_run.by_name["Empilés"]
    assert len(s.tables) == 2
    t1, t2 = s.tables
    assert t1.title == "Tableau A — ventes trimestrielles"
    assert t1.context == []
    assert list(t1.df.columns) == ["Produit", "Q1", "Q2", "Q3"]
    assert t2.title == "Tableau B — stocks"
    assert t2.context == ["au 31/12/2024, tous entrepôts"]
    assert list(t2.df.columns) == ["Produit", "Entrepôt", "Quantité", "Seuil"]


# --------------------------------------------------------------------------- #
# Séparateur 80% — fusion-titre non pleine largeur (A:D sur 5 colonnes)
# --------------------------------------------------------------------------- #
def test_separateur_80pct_splits_keeping_total_column(demo_run):
    s = demo_run.by_name["Séparateur 80%"]
    assert len(s.tables) == 2
    for t in s.tables:
        # la colonne « Total » (hors fusion-séparateur) reste une vraie colonne
        assert "Total" in t.df.columns
        assert list(t.df.columns)[0] == "Produit"


# --------------------------------------------------------------------------- #
# Colonnes-étiquettes — A5 retire les colonnes-étiquettes fusionnées en tête
# --------------------------------------------------------------------------- #
def test_colonnes_etiquettes_stripped_to_context(demo_run):
    s = demo_run.by_name["Colonnes-étiquettes"]
    assert len(s.tables) == 2
    t1, t2 = s.tables
    # Tableau 1 : 1 colonne-étiquette « Papeterie »
    assert t1.context == ["Papeterie"]
    assert t1.plage_donnees == "B2:E6"
    assert list(t1.df.columns) == ["Produit", "Prix", "Stock", "Statut"]
    # Tableau 2 : 2 colonnes-étiquettes « Nord », « Lille »
    assert t2.context == ["Nord", "Lille"]
    assert t2.plage_donnees == "C8:E12"
    assert list(t2.df.columns) == ["Produit", "Quantité", "Seuil"]


# --------------------------------------------------------------------------- #
# Transposée / Croisée — détection d'orientation (B1)
# --------------------------------------------------------------------------- #
def test_transposee_detected_and_remounted(demo_run):
    s = demo_run.by_name["Transposée"]
    assert len(s.tables) == 1
    t = s.tables[0]
    assert t.orientation == "transposed"
    # après df.T : les indicateurs deviennent des colonnes
    assert list(t.df.columns) == ["Indicateur", "Chiffre d'affaires", "Charges", "Résultat"]


def test_croisee_detected(demo_run):
    s = demo_run.by_name["Croisée"]
    assert len(s.tables) == 1
    t = s.tables[0]
    assert t.orientation == "cross-tab"
    assert list(t.df.columns) == ["Mois", "2022", "2023"]


# --------------------------------------------------------------------------- #
# Typage — coercition complète (B4)
# --------------------------------------------------------------------------- #
def test_typage_all_branches(demo_run):
    s = demo_run.by_name["Typage"]
    t = s.tables[0]
    df = t.df
    # numérique reconnu mais non converti : monnaie/%/virgule conservés,
    # seuls les espaces de milliers sont retirés (valeurs = chaînes)
    assert list(df["Prix"]) == ["1,50 €", "2,00 €", "0,80 €"]
    assert list(df["Remise"]) == ["15%", "5%", "0%"]
    assert list(df["Quantité"]) == ["1200", "12000", "8500"]
    assert list(df["Disponible"]) == ["oui", "non", "oui"]  # texte (plus de booléen)
    assert df["Date_MAJ"].iloc[0] == pd.Timestamp("2024-03-01")
    # zéros de tête préservés naturellement (aucune conversion en nombre)
    assert list(df["Code_Postal"]) == ["01000", "75001", "06000"]
    assert list(df["Téléphone"]) == ["0612345678", "0698765432", "0700000000"]


# --------------------------------------------------------------------------- #
# Entêtes — déduplication + nommage des colonnes vides (B2)
# --------------------------------------------------------------------------- #
def test_entetes_dedup_and_empty(demo_run):
    s = demo_run.by_name["Entêtes"]
    t = s.tables[0]
    assert list(t.df.columns) == ["Montant", "Montant.1", "col_2", "Montant.2"]


# --------------------------------------------------------------------------- #
# Formules — détection des formules (A1) et des erreurs (A2)
# --------------------------------------------------------------------------- #
def test_formules_flagged(demo_run):
    s = demo_run.by_name["Formules"]
    assert s.has_formulas is True
    assert len(s.tables) == 1
    assert list(s.tables[0].df.columns) == ["Produit", "Quantité", "Prix", "Total"]


# --------------------------------------------------------------------------- #
# Résidus — un tableau + deux résidus (A3)
# --------------------------------------------------------------------------- #
def test_residus_classified(demo_run):
    s = demo_run.by_name["Résidus"]
    assert len(s.tables) == 1
    types = sorted(r.type for r in s.residuals)
    assert types == ["isolated_cell", "non_tabular_block"]
    assert s.coverage == 0.8


# --------------------------------------------------------------------------- #
# Découpe — résidus de découpe non conservés par défaut
# --------------------------------------------------------------------------- #
def test_decoupe_default_drops_split_residuals(demo_run):
    s = demo_run.by_name["Découpe"]
    assert len(s.tables) == 1  # seul le vrai tableau survit
    assert s.residuals == []  # keep_split_residuals=False par défaut
    assert s.coverage == pytest.approx(0.67, abs=0.01)


# --------------------------------------------------------------------------- #
# Compaction — ligne à 1re colonne seule conservée en mode drop par défaut
# --------------------------------------------------------------------------- #
def test_compaction_keeps_partial_row(demo_run):
    s = demo_run.by_name["Compaction"]
    t = s.tables[0]
    # « Libellé orphelin » occupe la 1re colonne : la ligne n'est pas entièrement
    # vide, elle est donc conservée.
    assert "Libellé orphelin" in list(t.df["Catégorie"])


# --------------------------------------------------------------------------- #
# Brouillon — feuille masquée incluse par défaut
# --------------------------------------------------------------------------- #
def test_brouillon_hidden_sheet_included(demo_run):
    s = demo_run.by_name["Brouillon"]
    assert s.visible is False
    assert len(s.tables) == 1
    assert list(s.tables[0].df.columns) == ["clé", "valeur"]


# --------------------------------------------------------------------------- #
# Options : exclusion des feuilles masquées (sans recalc → hors-ligne)
# --------------------------------------------------------------------------- #
def test_exclude_hidden_sheets(demo_path):
    proc = ExcelProcessor()
    proc.include_hidden_sheets = False
    summaries = proc._build_extractor(demo_path).extract()
    # « Brouillon » est masquée → aucune table issue d'elle
    brouillon = next(s for s in summaries if s.name == "Brouillon")
    assert brouillon.tables == []


# --------------------------------------------------------------------------- #
# Options : sélection d'une seule feuille (sans recalc → hors-ligne)
# --------------------------------------------------------------------------- #
def test_sheets_filter_single(demo_path):
    proc = ExcelProcessor()
    proc.sheets = "Typage"
    summaries = proc._build_extractor(demo_path).extract()
    assert [s.name for s in summaries] == ["Typage"]


# --------------------------------------------------------------------------- #
# Options : keep_single_column_tables=False écarte les tableaux réduits à 1 col.
# --------------------------------------------------------------------------- #
def test_keep_single_column_false_drops_single_column(make_extractor):
    # colonne « Note » entièrement vide → supprimée en B3 → tableau réduit à 1 col.
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "Produit",
                    "B1": "Note",
                    "A2": "Stylo",
                    "A3": "Cahier",
                    "A4": "Gomme",
                },
            }
        ],
        keep_single_column_tables=False,
        drop_empty_cols=True,
    )
    summaries = ext.extract()
    s = summaries[0]
    assert s.tables == []  # écarté après réduction à une colonne
    assert any(r.type == "single_column_table" for r in s.residuals)


def test_keep_single_column_true_keeps_it(make_extractor):
    ext = make_extractor(
        [
            {
                "name": "F1",
                "cells": {
                    "A1": "Produit",
                    "B1": "Note",
                    "A2": "Stylo",
                    "A3": "Cahier",
                    "A4": "Gomme",
                },
            }
        ],
        keep_single_column_tables=True,
        drop_empty_cols=True,
    )
    summaries = ext.extract()
    s = summaries[0]
    assert len(s.tables) == 1
    assert list(s.tables[0].df.columns) == ["Produit"]
