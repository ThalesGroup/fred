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
Tests for the tabular value-locator tool (`search_tabular_values`,
EXCEL-EXTRACTION-PIPELINE-RFC §12 / INGEST-04).

These exercise the service method directly: normalized substring matching
(case/accent/whitespace insensitive, decimal comma treated as point) over every
column cast to text, the row/table caps and their truncation signals, and that
ReBAC scoping matches `query_read`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.processors.output.tabular_processor.tabular_processor import TabularProcessor
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import TabularSearchRequest


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="tester", email="tester@example.com", roles=["admin"])


async def _ingest_csv(*, tmp_path: Path, document_uid: str, file_name: str, content: str) -> DocumentMetadata:
    """Run the real CSV tabular pipeline (Parquet artifact in the local store)."""
    csv_path = tmp_path / file_name
    csv_path.write_text(content, encoding="utf-8")
    metadata = DocumentMetadata(
        identity=Identity(document_name=file_name, document_uid=document_uid, title=file_name),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
        tags=Tagging(tag_ids=[], tag_names=[]),
    )
    processed = TabularProcessor().process(str(csv_path), metadata)
    await MetadataService().save_document_metadata(_user(), processed)
    return processed


class _FakeRebac:
    def __init__(self, readable_document_uids: set[str]):
        self.readable_document_uids = readable_document_uids

    async def lookup_user_resources(self, user, permission):
        del user, permission
        return [SimpleNamespace(id=uid) for uid in sorted(self.readable_document_uids)]

    async def has_user_permission(self, user, permission, resource_id):
        del user, permission
        return resource_id in self.readable_document_uids


@pytest.mark.asyncio
async def test_search_locates_value_case_accent_and_space_insensitive(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        document_uid="doc-catalogue",
        file_name="catalogue.csv",
        content="reference,fournisseur,quantite\nABC-123,Café de Paris,42\nXYZ-999,Boulangerie,7\n",
    )

    service = TabularService()

    # Accent + case insensitive: search "CAFE" finds "Café de Paris".
    accent = await service.search_values(_user(), request=TabularSearchRequest(keyword="CAFE"))
    assert [match.document_uid for match in accent.matches] == ["doc-catalogue"]
    assert accent.matches[0].matched_columns == ["fournisseur"]
    assert accent.matches[0].rows == [{"reference": "ABC-123", "fournisseur": "Café de Paris", "quantite": 42}]
    assert accent.tables_truncated is False
    assert accent.matches[0].row_truncated is False

    # Space insensitive: "cafede" matches across the removed spaces.
    spaced = await service.search_values(_user(), request=TabularSearchRequest(keyword="cafede"))
    assert spaced.matches and spaced.matches[0].matched_columns == ["fournisseur"]

    # A genuinely numeric (integer) column is searchable via the text cast.
    numeric = await service.search_values(_user(), request=TabularSearchRequest(keyword="42"))
    assert numeric.matches and numeric.matches[0].matched_columns == ["quantite"]


@pytest.mark.asyncio
async def test_search_matches_numeric_format_with_thousands_space_and_decimal_comma(tmp_path, metadata_store):
    """A French-formatted amount stored as text ("1 234,56") is found by "1234.56":
    whitespace is removed and the decimal comma is normalized to a point."""
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        document_uid="doc-montants",
        file_name="montants.csv",
        content='produit,montant\nVis,"1 234,56"\nEcrou,"99,90"\n',
    )

    service = TabularService()
    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="1234.56"))
    assert [match.document_uid for match in response.matches] == ["doc-montants"]
    assert response.matches[0].matched_columns == ["montant"]
    assert response.matches[0].rows == [{"produit": "Vis", "montant": "1 234,56"}]


@pytest.mark.asyncio
async def test_search_caps_rows_per_table_and_flags_truncation(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    rows = "\n".join(f"{index},ERROR" for index in range(8))
    await _ingest_csv(
        tmp_path=tmp_path,
        document_uid="doc-logs",
        file_name="logs.csv",
        content=f"id,status\n{rows}\n",
    )

    service = TabularService()
    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="error", max_rows_per_table=2))
    assert len(response.matches) == 1
    match = response.matches[0]
    assert match.matched_columns == ["status"]
    assert len(match.rows) == 2
    assert match.row_truncated is True


@pytest.mark.asyncio
async def test_search_caps_matching_tables_and_flags_truncation(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    for index in range(3):
        await _ingest_csv(
            tmp_path=tmp_path,
            document_uid=f"doc-widget-{index}",
            file_name=f"widget-{index}.csv",
            content="label\nwidget\n",
        )

    service = TabularService()
    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="widget", max_matching_tables=2))
    assert len(response.matches) == 2
    assert response.tables_truncated is True
    # All three documents were in scope even though the scan stopped at two matches.
    assert len(response.searched_dataset_uids) == 3


@pytest.mark.asyncio
async def test_search_returns_no_match_when_value_absent(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        document_uid="doc-catalogue",
        file_name="catalogue.csv",
        content="reference,fournisseur\nABC-123,Café de Paris\n",
    )

    service = TabularService()
    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="introuvable-xyz"))
    assert response.matches == []
    assert response.tables_truncated is False


@pytest.mark.asyncio
async def test_search_only_scans_rebac_authorized_documents(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(tmp_path=tmp_path, document_uid="doc-visible", file_name="visible.csv", content="note\nsecret\n")
    await _ingest_csv(tmp_path=tmp_path, document_uid="doc-hidden", file_name="hidden.csv", content="note\nsecret\n")

    service = TabularService()
    service.rebac = _FakeRebac({"doc-visible"})

    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="secret"))
    assert [match.document_uid for match in response.matches] == ["doc-visible"]

    with pytest.raises(PermissionError, match="doc-hidden"):
        await service.search_values(_user(), request=TabularSearchRequest(keyword="secret", dataset_uids=["doc-hidden"]))


@pytest.mark.asyncio
async def test_search_rejects_too_short_keyword(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(tmp_path=tmp_path, document_uid="doc-catalogue", file_name="catalogue.csv", content="note\nhello\n")

    service = TabularService()
    with pytest.raises(ValueError, match="at least 2 characters"):
        await service.search_values(_user(), request=TabularSearchRequest(keyword="a"))


@pytest.mark.asyncio
async def test_search_caps_datasets_examined_even_when_nothing_matches(tmp_path, metadata_store):
    """
    Verify the scan is bounded by tables *examined*, not only by tables matched.

    Why this exists:
    - `max_matching_tables` only breaks the loop once matches accumulate, so a
      keyword that matches nothing used to scan every selected dataset twice
      (an aggregate pass plus a sampled pass). That is issue #2182 finding C:
      the zero-match case was the unbounded one.
    """
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    for index in range(4):
        await _ingest_csv(
            tmp_path=tmp_path,
            document_uid=f"doc-quiet-{index}",
            file_name=f"quiet-{index}.csv",
            content="label\nsomethingelse\n",
        )

    service = TabularService()
    service.tabular_config = service.tabular_config.model_copy(update={"query": service.tabular_config.query.model_copy(update={"max_selected_datasets": 2})})

    examined: list[str] = []
    original_search = service._search_one_table

    def _record(*, connection, dataset, normalized_keyword, max_rows_per_table):
        examined.append(dataset.query_alias)
        return original_search(
            connection=connection,
            dataset=dataset,
            normalized_keyword=normalized_keyword,
            max_rows_per_table=max_rows_per_table,
        )

    service._search_one_table = _record

    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="absent-value"))

    assert response.matches == []
    assert len(examined) == 2, "a zero-match search must still stop at the dataset cap"
    assert response.tables_truncated is True
    assert len(response.searched_dataset_uids) == 2


@pytest.mark.asyncio
async def test_search_does_not_claim_to_have_searched_a_partially_scanned_document(tmp_path, metadata_store):
    """
    Verify a workbook cut in half by the dataset cap is not reported as searched.

    Why this exists:
    - A spreadsheet expands to one dataset per table, so the cap can slice
      through the middle of one document. Listing its uid in
      `searched_dataset_uids` would tell the caller "the value is not in this
      document" when tables of it were never opened — a wrong answer, not a
      partial one. `tables_truncated` alone does not say which document is
      incomplete.
    """
    # Reuse the workbook fixture rather than duplicating the two-sheet build.
    from tests.services.test_tabular_service import _ingest_excel_workbook

    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_excel_workbook(tmp_path=tmp_path, document_uid="doc-book")
    await _ingest_csv(
        tmp_path=tmp_path,
        document_uid="doc-plain",
        file_name="plain.csv",
        content="label\nwidget\n",
    )

    service = TabularService()
    all_datasets = await service._resolve_authorized_datasets(_user())
    workbook_tables = [dataset for dataset in all_datasets if dataset.metadata.document_uid == "doc-book"]
    assert len(workbook_tables) > 1, "fixture must produce a multi-table workbook"

    # Cap below the workbook's table count so the document is sliced in half.
    service.tabular_config = service.tabular_config.model_copy(update={"query": service.tabular_config.query.model_copy(update={"max_selected_datasets": 1})})

    response = await service.search_values(_user(), request=TabularSearchRequest(keyword="Paris"))

    assert response.tables_truncated is True
    assert "doc-book" not in response.searched_dataset_uids, "a half-scanned workbook must not be reported as searched"
