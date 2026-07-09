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
Output stage des classeurs Excel : promotion du sidecar `tables.json` en
extension `tabular_multi_v1` + marquage SQL_INDEXED (jamais de vectorisation).
"""

from __future__ import annotations

import json

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.core.processors.output.base_output_processor import TabularProcessingError
from knowledge_flow_backend.core.processors.output.excel_processor.excel_table_registration_processor import ExcelTableRegistrationProcessor
from knowledge_flow_backend.features.tabular.artifacts import read_tabular_multi_artifact


def _metadata(document_uid: str = "doc-xlsx") -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name="book.xlsx", document_uid=document_uid, title="book"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.XLSX),
        tags=Tagging(tag_ids=[], tag_names=[]),
    )


def _registered_entry(*, table_id: str = "Ventes.t1", sheet: str = "Ventes", alias: str = "d_doc_xlsx_ventes_t1", row_count: int = 2) -> dict:
    return {
        "table_id": table_id,
        "table_index": 1,
        "sheet": sheet,
        "title": "Ventes 2026",
        "range": "A1:B3",
        "data_range": "A1:B3",
        "format": "parquet",
        "path": f"parquet/{table_id}.parquet",
        "row_count": row_count,
        "columns": [{"name": "city", "dtype": "string"}, {"name": "amount", "dtype": "string"}],
        "dataset_uid": "doc-xlsx",
        "object_key": f"tabular/datasets/doc-xlsx/rev-1/{table_id}.parquet",
        "query_alias": alias,
        "source_revision": "rev-1",
        "generated_at": "2026-07-03T12:00:00+00:00",
        "file_size_bytes": 1024,
    }


def _write_sidecar(output_dir, entries) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tables.json").write_text(json.dumps(entries), encoding="utf-8")
    md_path = output_dir / "output.md"
    md_path.write_text("# Extraction summary\n", encoding="utf-8")
    return str(md_path)


def test_promotes_sidecar_into_tabular_multi_extension(tmp_path):
    entries = [
        _registered_entry(),
        _registered_entry(table_id="Cibles.t1", sheet="Cibles", alias="d_doc_xlsx_cibles_t1", row_count=3),
    ]
    md_path = _write_sidecar(tmp_path / "output", entries)

    metadata = ExcelTableRegistrationProcessor().process(md_path, _metadata())

    multi = read_tabular_multi_artifact(metadata)
    assert multi is not None
    assert [table.query_alias for table in multi.tables] == ["d_doc_xlsx_ventes_t1", "d_doc_xlsx_cibles_t1"]
    assert [table.sheet for table in multi.tables] == ["Ventes", "Cibles"]
    assert multi.tables[0].object_key == "tabular/datasets/doc-xlsx/rev-1/Ventes.t1.parquet"
    assert multi.tables[0].range == "A1:B3"
    assert metadata.file.row_count == 5
    assert metadata.processing.stages[ProcessingStage.SQL_INDEXED] == ProcessingStatus.DONE
    assert metadata.processing.stages.get(ProcessingStage.VECTORIZED, ProcessingStatus.NOT_STARTED) == ProcessingStatus.NOT_STARTED


def test_unregistered_entries_are_skipped(tmp_path):
    unregistered = {key: value for key, value in _registered_entry().items() if key not in {"object_key", "query_alias", "source_revision", "generated_at", "dataset_uid", "file_size_bytes"}}
    md_path = _write_sidecar(tmp_path / "output", [unregistered])

    metadata = ExcelTableRegistrationProcessor().process(md_path, _metadata())

    assert read_tabular_multi_artifact(metadata) is None
    assert metadata.processing.stages[ProcessingStage.SQL_INDEXED] == ProcessingStatus.DONE


def test_missing_sidecar_still_marks_sql_indexed(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    md_path = output_dir / "output.md"
    md_path.write_text("# Extraction summary\n", encoding="utf-8")

    metadata = ExcelTableRegistrationProcessor().process(str(md_path), _metadata())

    assert read_tabular_multi_artifact(metadata) is None
    assert metadata.processing.stages[ProcessingStage.SQL_INDEXED] == ProcessingStatus.DONE


def test_malformed_sidecar_raises(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "tables.json").write_text("{not json", encoding="utf-8")
    md_path = output_dir / "output.md"
    md_path.write_text("# Extraction summary\n", encoding="utf-8")

    with pytest.raises(TabularProcessingError, match="Unreadable tables.json"):
        ExcelTableRegistrationProcessor().process(str(md_path), _metadata())


def test_invalid_registered_entry_raises(tmp_path):
    broken = _registered_entry()
    broken.pop("query_alias")
    broken["object_key"] = "tabular/datasets/doc-xlsx/rev-1/broken.parquet"
    md_path = _write_sidecar(tmp_path / "output", [broken])

    with pytest.raises(TabularProcessingError, match="Invalid tables.json entry"):
        ExcelTableRegistrationProcessor().process(md_path, _metadata())
