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

import json
import logging
from pathlib import Path

from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage

from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor, TabularProcessingError
from knowledge_flow_backend.features.tabular.artifacts import (
    TabularMultiArtifactV1,
    TabularTableArtifactV1,
    write_tabular_multi_artifact,
)

logger = logging.getLogger(__name__)


class ExcelTableRegistrationProcessor(BaseOutputProcessor):
    """
    Spreadsheet output stage: promote the input-stage sidecar into metadata.

    Why this exists:
    - The Excel input processor already wrote `output.md` and uploaded one
      Parquet artifact per detected table under the canonical
      `tabular/datasets/<uid>/<rev>/` prefix, but the input stage cannot write
      `metadata.extensions`. Those tables only become visible to the tabular
      runtime once their descriptors land in `extensions["tabular_multi_v1"]`.
    - No vectorization ever happens for spreadsheets: this processor is the
      whole output stage.

    How to use:
    - Registered for `.xlsx` / `.xls` / `.xlsm` through the "spreadsheet"
      category default. `process(...)` receives the path of `output.md` (the
      pipeline resolves the preview file) and reads `tables.json` next to it.
    """

    description = "Promotes the Excel input sidecar (tables.json) into the tabular_multi_v1 extension and marks SQL_INDEXED."

    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        output_dir = Path(file_path).parent  # file_path = .../output/output.md
        entries = self._read_sidecar(output_dir / "tables.json", document_uid=metadata.document_uid)

        registered_entries = [entry for entry in entries if entry.get("object_key")]
        unregistered = len(entries) - len(registered_entries)
        if unregistered:
            logger.warning(
                "[PROCESSOR][EXCEL] %d table(s) of document %s have no object_key and will not be SQL-exposed",
                unregistered,
                metadata.document_uid,
            )

        try:
            tables = [TabularTableArtifactV1.model_validate(entry) for entry in registered_entries]
        except Exception as exc:  # noqa: BLE001
            raise TabularProcessingError(f"Invalid tables.json entry for document {metadata.document_uid}") from exc

        if tables:
            write_tabular_multi_artifact(metadata, TabularMultiArtifactV1(tables=tables))
            metadata.file.row_count = sum(table.row_count for table in tables)
            logger.info(
                "[PROCESSOR][EXCEL] Registered %d table(s) for document %s: %s",
                len(tables),
                metadata.document_uid,
                [table.query_alias for table in tables],
            )
        else:
            logger.info("[PROCESSOR][EXCEL] No registered table for document %s; marking SQL_INDEXED with no dataset", metadata.document_uid)

        metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
        return metadata

    @staticmethod
    def _read_sidecar(sidecar_path: Path, *, document_uid: str) -> list[dict]:
        """Return the catalog entries from `tables.json`, or an empty list when
        the sidecar is missing (e.g. a workbook with no extractable table that
        predates the sidecar). A malformed sidecar raises: better a visible
        error stage than silently losing every table."""
        if not sidecar_path.is_file():
            logger.warning("[PROCESSOR][EXCEL] No tables.json sidecar for document %s at %s", document_uid, sidecar_path)
            return []
        try:
            entries = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise TabularProcessingError(f"Unreadable tables.json sidecar for document {document_uid}") from exc
        if not isinstance(entries, list):
            raise TabularProcessingError(f"tables.json for document {document_uid} must contain a JSON array")
        return entries
