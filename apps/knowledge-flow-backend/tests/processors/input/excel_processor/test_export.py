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
Niveau 3bis — tests de l'export (sommaire Markdown + extraits + tables.json).

Deux sources :
  • `demo_run` (skippé sans LibreOffice) — export du classeur de démo complet ;
  • `run_export` — conversion hors-ligne de petits classeurs via le point
    d'entrée public `convert_file_to_markdown`.

Contrat cible : les artefacts sont écrits DIRECTEMENT sous `output_dir`
(`output.md`, `<fmt>/<table>.<fmt>`, `tables.json`), sans sous-dossier `<stem>/`.
"""

from __future__ import annotations

import io
import json
import os

import pandas as pd
import pytest

from knowledge_flow_backend.core.processors.input.excel_processor.excel_processor import ExcelProcessor


# ========================================================================== #
# Export du classeur de démo (intégration, via demo_run)
# ========================================================================== #
def test_markdown_summary_written(demo_run):
    md = os.path.join(demo_run.output_dir, "output.md")
    assert os.path.exists(md)
    with open(md, encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("# Extraction summary")
    # chaque feuille apparaît comme section
    for name in ["Synthèse", "Typage", "Brouillon"]:
        assert f"## Sheet: {name}" in content


def test_one_csv_per_non_empty_table(demo_run):
    csv_dir = os.path.join(demo_run.output_dir, "csv")
    files = sorted(os.listdir(csv_dir))
    # 17 tableaux, tous non vides → 17 CSV
    assert len(files) == 17
    assert all(f.endswith(".csv") for f in files)


def test_csv_filenames_are_sanitized(demo_run):
    csv_dir = os.path.join(demo_run.output_dir, "csv")
    files = os.listdir(csv_dir)
    # « Séparateur 80%.t1 » → nom de fichier nettoyé : accents repliés en ASCII,
    # espace et % remplacés (pas d'espace ni de %).
    assert "Separateur_80_.t1.csv" in files


def test_csv_roundtrip_typage(demo_run):
    csv_dir = os.path.join(demo_run.output_dir, "csv")
    df = pd.read_csv(os.path.join(csv_dir, "Typage.t1.csv"), sep=";", dtype=str)
    assert list(df.columns) == [
        "Produit",
        "Prix",
        "Remise",
        "Quantité",
        "Disponible",
        "Date_MAJ",
        "Code_Postal",
        "Téléphone",
    ]
    assert len(df) == 3
    # les zéros de tête de l'identifiant ont survécu à l'aller-retour CSV
    assert df["Code_Postal"].iloc[0] == "01000"


def test_markdown_references_csv_links(demo_run):
    md = os.path.join(demo_run.output_dir, "output.md")
    with open(md, encoding="utf-8") as f:
        content = f.read()
    assert "(csv/Typage.t1.csv)" in content


def test_tables_json_lists_every_non_empty_table(demo_run):
    with open(os.path.join(demo_run.output_dir, "tables.json"), encoding="utf-8") as f:
        entries = json.load(f)
    # une entrée par tableau non vide (= 1 CSV chacun)
    assert len(entries) == 17
    # chaque entrée référence un extrait réellement écrit
    for entry in entries:
        assert set(entry) >= {"table_id", "sheet", "range", "format", "path", "row_count", "columns"}
        assert os.path.isfile(os.path.join(demo_run.output_dir, entry["path"]))
    # le schéma « Typage » est repris dans le sidecar
    typage = next(e for e in entries if e["table_id"] == "Typage.t1")
    assert [c["name"] for c in typage["columns"]] == [
        "Produit",
        "Prix",
        "Remise",
        "Quantité",
        "Disponible",
        "Date_MAJ",
        "Code_Postal",
        "Téléphone",
    ]


# ========================================================================== #
# Conversion hors-ligne de petits classeurs (via run_export)
# ========================================================================== #
def test_convert_writes_output_md(run_export):
    r = run_export(
        [
            {
                "name": "S",
                "cells": {"A1": "h", "B1": "g", "A2": 1, "B2": 2, "A3": 3, "B3": 4},
            }
        ]
    )
    md = r.output_dir / "output.md"
    assert md.is_file()
    assert md.read_text(encoding="utf-8").startswith("# Extraction summary")
    assert r.result["md_file"].endswith("output.md")


def test_tables_json_matches_csv_files(run_export):
    r = run_export(
        [
            {
                "name": "Vide",
                "cells": {"A1": "h1", "B1": "h2", "A2": None, "B2": None, "A3": "garde", "B3": "moi"},
            }
        ],
        extract_format="csv",
    )
    entries = json.loads((r.output_dir / "tables.json").read_text(encoding="utf-8"))
    csv_dir = r.output_dir / "csv"
    written = sorted(p.name for p in csv_dir.iterdir()) if csv_dir.is_dir() else []
    # exactement un CSV par entrée du catalogue : aucun extrait pour une table vide
    assert len(written) == len(entries)
    for entry in entries:
        assert (r.output_dir / entry["path"]).is_file()


def test_tables_json_entry_shape(run_export):
    r = run_export(
        [
            {
                "name": "Data",
                "cells": {"A1": "Produit", "B1": "Prix", "A2": "Pomme", "B2": 10, "A3": "Poire", "B3": 20},
            }
        ],
        extract_format="csv",
    )
    entries = json.loads((r.output_dir / "tables.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    entry = entries[0]
    assert entry["format"] == "csv"
    assert entry["path"] == "csv/Data.t1.csv"
    assert entry["row_count"] == 2
    assert [c["name"] for c in entry["columns"]] == ["Produit", "Prix"]
    # dtype repris du vocabulaire tabulaire plateforme
    assert {c["dtype"] for c in entry["columns"]} <= {"string", "integer", "float", "boolean", "datetime", "unknown"}


# --------------------------------------------------------------------------- #
# Export au format parquet (extract_format="parquet")
# --------------------------------------------------------------------------- #
def _read_stored_parquet(object_key: str) -> pd.DataFrame:
    """Read back a Parquet artifact uploaded to the tabular store by its key."""
    from knowledge_flow_backend.application_context import ApplicationContext

    store = ApplicationContext.get_instance().get_content_store()
    data = store.get_object_stream(object_key).read()
    return pd.read_parquet(io.BytesIO(data))


def test_parquet_export_uploads_and_leaves_no_local_copy(run_export):
    # Mode ingestion + Parquet : l'extrait part dans le tabular store, aucune
    # copie locale ne subsiste sous output_dir (pas de duplication dans le bucket
    # de contenu documentaire lors de save_output).
    r = run_export(
        [
            {
                "name": "Data",
                "cells": {"A1": "Produit", "B1": "Prix", "A2": "Pomme", "B2": 10, "A3": "Poire", "B3": 20},
            }
        ],
        extract_format="parquet",
    )
    # output_dir ne contient plus que le preview + le sidecar
    assert not (r.output_dir / "parquet").exists()
    assert not (r.output_dir / "csv").is_dir()
    assert sorted(p.name for p in r.output_dir.iterdir()) == ["output.md", "tables.json"]

    # le contenu Parquet vit désormais dans le tabular store, sous object_key
    entries = json.loads((r.output_dir / "tables.json").read_text(encoding="utf-8"))
    df = _read_stored_parquet(entries[0]["object_key"])
    assert list(df.columns) == ["Produit", "Prix"]
    assert len(df) == 2


def test_parquet_export_mixed_type_column(run_export):
    # colonne object mêlant nombres et texte (59, 99, "CTRL") : l'écriture parquet
    # ne doit pas planter (cast en `string`), et la valeur survit à l'aller-retour.
    r = run_export(
        [
            {
                "name": "Mix",
                "cells": {"A1": "Code", "B1": "Libellé", "A2": 59, "B2": "a", "A3": 99, "B3": "b", "A4": "CTRL", "B4": "c"},
            }
        ],
        extract_format="parquet",
        coerce_types=False,
    )
    entries = json.loads((r.output_dir / "tables.json").read_text(encoding="utf-8"))
    df = _read_stored_parquet(entries[0]["object_key"])
    assert df["Code"].astype(str).tolist() == ["59", "99", "CTRL"]


def test_parquet_markdown_shows_object_key_not_link(run_export):
    r = run_export(
        [
            {
                "name": "Data",
                "cells": {"A1": "h", "A2": "v1", "A3": "v2", "B1": "g", "B2": 1, "B3": 2},
            }
        ],
        extract_format="parquet",
    )
    content = (r.output_dir / "output.md").read_text(encoding="utf-8")
    entries = json.loads((r.output_dir / "tables.json").read_text(encoding="utf-8"))
    object_key = entries[0]["object_key"]
    # seul le NOM du fichier parquet est présent EN CLAIR (basename)
    assert f'parquet="{os.path.basename(object_key)}"' in content
    # le préfixe de stockage interne (tabular/datasets/<uid>/<rev>/) n'est PAS exposé
    assert "tabular/datasets/" not in content
    assert object_key not in content
    # ce n'est pas non plus un lien markdown de redirection
    assert "[PARQUET]" not in content
    assert "[CSV]" not in content
    assert f"]({object_key})" not in content
    # et l'alias SQL reste exposé
    assert 'query_alias="' in content


def test_invalid_extract_format_raises(run_export):
    with pytest.raises(ValueError):
        run_export([{"name": "S", "cells": {"A1": 1}}], extract_format="json")


def test_check_file_validity_and_metadata(tmp_path):
    # petit bout de contrat processeur : validité + métadonnées légères
    from pathlib import Path

    from openpyxl import Workbook

    path = tmp_path / "book.xlsx"
    wb = Workbook()
    wb.active.title = "S1"
    wb.create_sheet("S2")
    wb.save(str(path))

    proc = ExcelProcessor()
    assert proc.check_file_validity(Path(path)) is True
    assert proc.check_file_validity(tmp_path / "missing.xlsx") is False
    meta = proc.extract_file_metadata(Path(path))
    assert meta["extras"]["excel.sheet_count"] == 2
    assert meta["extras"]["excel.sheet_names"] == ["S1", "S2"]
