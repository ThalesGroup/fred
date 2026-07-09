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

"""
Niveau 3ter — tests de l'enregistrement tabulaire (mode ingestion).

Quand `convert_file_to_markdown` reçoit un `document_uid` et que les extraits
sont Parquet, chaque table est uploadée dans le content store sous la clé
canonique `tabular/datasets/<uid>/<rev>/…` et son entrée `tables.json` gagne
`object_key` / `query_alias` / `source_revision`. L'alias imprimé dans
`output.md` doit être identique à celui du sidecar (contrat catalogue SQL).
"""

from __future__ import annotations

import json

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tabular.artifacts import build_table_query_alias


def _read_sidecar(output_dir):
    return json.loads((output_dir / "tables.json").read_text(encoding="utf-8"))


def test_parquet_export_registers_tables_in_content_store(run_export):
    # le content store de test persiste sur disque : on repart d'un état vide
    ApplicationContext.get_instance().get_content_store().clear()
    r = run_export(
        [
            {
                "name": "Data",
                "cells": {"A1": "Produit", "B1": "Prix", "A2": "Pomme", "B2": 10, "A3": "Poire", "B3": 20},
            }
        ],
        extract_format="parquet",
    )
    entries = _read_sidecar(r.output_dir)
    assert len(entries) == 1
    entry = entries[0]

    document_uid = r.document_uid
    expected_alias = build_table_query_alias(document_uid, "Data", 1)
    assert entry["query_alias"] == expected_alias
    assert entry["dataset_uid"] == document_uid
    assert entry["table_index"] == 1
    assert entry["source_revision"]
    assert entry["generated_at"]
    assert entry["file_size_bytes"] > 0
    assert entry["object_key"] == f"tabular/datasets/{document_uid}/{entry['source_revision']}/Data.t1.parquet"

    # l'artefact est réellement présent dans le content store partagé
    content_store = ApplicationContext.get_instance().get_content_store()
    stored = content_store.list_objects(f"tabular/datasets/{document_uid}/")
    assert [s.key for s in stored] == [entry["object_key"]]

    # le catalogue Markdown expose exactement le même alias
    md = (r.output_dir / "output.md").read_text(encoding="utf-8")
    assert f'query_alias="{expected_alias}"' in md


def test_csv_export_is_not_registered(run_export):
    r = run_export(
        [
            {
                "name": "Data",
                "cells": {"A1": "Produit", "B1": "Prix", "A2": "Pomme", "B2": 10, "A3": "Poire", "B3": 20},
            }
        ],
        extract_format="csv",
    )
    entries = _read_sidecar(r.output_dir)
    assert len(entries) == 1
    assert "object_key" not in entries[0]
    assert "query_alias" not in entries[0]
    assert 'query_alias="' not in (r.output_dir / "output.md").read_text(encoding="utf-8")


def test_colliding_sheet_aliases_are_deduplicated(run_export):
    # « Data 1 » et « Data_1 » se sanitizent tous deux en « data_1 » : les deux
    # feuilles portent une table t1 → même alias de base, dédupliqué en « _2 ».
    r = run_export(
        [
            {"name": "Data 1", "cells": {"A1": "h1", "B1": "h2", "A2": 1, "B2": 2, "A3": 3, "B3": 4}},
            {"name": "Data_1", "cells": {"A1": "h1", "B1": "h2", "A2": 5, "B2": 6, "A3": 7, "B3": 8}},
        ],
        extract_format="parquet",
    )
    entries = _read_sidecar(r.output_dir)
    aliases = [entry["query_alias"] for entry in entries]
    assert len(aliases) == 2
    assert len(set(aliases)) == 2
    assert aliases[1] == f"{aliases[0]}_2"


def test_registration_survives_missing_application_context(run_export, monkeypatch):
    # Run standalone (pas de contexte) : export local intact, aucune clé objet.
    monkeypatch.setattr(ApplicationContext, "_instance", None)
    r = run_export(
        [
            {
                "name": "Data",
                "cells": {"A1": "Produit", "B1": "Prix", "A2": "Pomme", "B2": 10, "A3": "Poire", "B3": 20},
            }
        ],
        extract_format="parquet",
    )
    entries = _read_sidecar(r.output_dir)
    assert len(entries) == 1
    assert "object_key" not in entries[0]
    assert (r.output_dir / entries[0]["path"]).is_file()
