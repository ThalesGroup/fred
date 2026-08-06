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

"""Unit tests for the vector-metadata repair activities (#2234, 3a).

Mirrors `test_revectorize_activities.py`'s pattern: call the `@activity.defn`
function directly (it's a plain async function) and patch
`ApplicationContext.get_instance`.

The most important tests in this file are the structural safety-guarantee
ones (`TestNeverTouchesTheEmbedderOrVectorStoreAdapter`): the whole point of
`list_strict_vector_document_uids` is that it can list real vector
document_uids WITHOUT ever calling `get_embedder()`/`get_create_vector_store()`
or constructing an `OpenSearchVectorStoreAdapter` (whose `__init__` calls
`ensure_ready()`, which calls the embedder and can create/update the index,
its mapping, or the hybrid-search pipeline -- every one of those is forbidden
for a metadata-only repair).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
)

from knowledge_flow_backend.common.structures import ChromaVectorStorageConfig, OpenSearchVectorIndexConfig
from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from knowledge_flow_backend.features.scheduler.repair_vector_metadata_activities import (
    bulk_repair_vector_metadata,
    emit_repair_vector_metadata_task_event,
    list_repair_candidates_for_source_tag,
    list_strict_content_document_uids,
    list_strict_vector_document_uids,
)

_PATCH_CTX = "knowledge_flow_backend.application_context.ApplicationContext.get_instance"


def _run(coro):
    return asyncio.run(coro)


def _make_metadata(
    document_uid: str,
    *,
    file_type: FileType = FileType.PDF,
    vector_done: bool = False,
    source_tag: str = "fred",
    stage_status: tuple[ProcessingStage, ProcessingStatus] | None = None,
) -> DocumentMetadata:
    md = DocumentMetadata(
        identity=Identity(document_name=f"{document_uid}.pdf", document_uid=document_uid, title=document_uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag=source_tag),
        file=FileInfo(file_type=file_type),
    )
    if vector_done:
        md.processing.mark_done(ProcessingStage.VECTORIZED)
    if stage_status is not None:
        stage, status = stage_status
        md.processing.set_status(stage, status)
    return md


def _fake_search_client(pages: list[dict]) -> MagicMock:
    """A bare mock standing in for `ApplicationContext.get_opensearch_client()`'s
    return value -- only `.search()` is ever expected to be called; `.indices`/
    `.ingest` are left as ordinary auto-created mocks so a test can assert they
    were never *called* (see `TestNeverTouchesTheEmbedderOrVectorStoreAdapter`)."""
    client = MagicMock()
    client.search = MagicMock(side_effect=pages)
    return client


def _one_empty_page() -> dict:
    return {"aggregations": {"by_doc": {"buckets": []}}}


class TestListRepairCandidatesForSourceTag:
    def test_resolves_via_list_by_source_tag_and_flags_tabular_and_vector_done(self):
        docs = [
            _make_metadata("doc-1"),
            _make_metadata("doc-2", vector_done=True),
            _make_metadata("doc-3", file_type=FileType.CSV),
            _make_metadata("doc-4", file_type=FileType.XLSX),
        ]
        metadata_store = MagicMock()
        metadata_store.list_by_source_tag = AsyncMock(return_value=docs)
        app_ctx = MagicMock()
        app_ctx.get_metadata_store.return_value = metadata_store

        with patch(_PATCH_CTX, return_value=app_ctx):
            result = _run(list_repair_candidates_for_source_tag("fred"))

        metadata_store.list_by_source_tag.assert_awaited_once_with("fred")
        assert result == [
            {"document_uid": "doc-1", "is_tabular": False, "vector_done": False, "failed_or_running": False},
            {"document_uid": "doc-2", "is_tabular": False, "vector_done": True, "failed_or_running": False},
            {"document_uid": "doc-3", "is_tabular": True, "vector_done": False, "failed_or_running": False},
            {"document_uid": "doc-4", "is_tabular": True, "vector_done": False, "failed_or_running": False},
        ]

    def test_flags_failed_or_running_when_any_stage_is_failed_or_in_progress(self):
        """Real Kea-corpus shape (#2234 hardening): a document whose `vector`
        never started but whose `preview` stage reads `failed`, and one whose
        `vector` stage itself reads `failed` -- both must be flagged, not
        silently treated the same as a clean `not_started` document."""
        docs = [
            _make_metadata("doc-failed-preview", stage_status=(ProcessingStage.PREVIEW_READY, ProcessingStatus.FAILED)),
            _make_metadata("doc-failed-vector", stage_status=(ProcessingStage.VECTORIZED, ProcessingStatus.FAILED)),
            _make_metadata("doc-in-progress", stage_status=(ProcessingStage.PREVIEW_READY, ProcessingStatus.IN_PROGRESS)),
            _make_metadata("doc-clean"),
        ]
        metadata_store = MagicMock()
        metadata_store.list_by_source_tag = AsyncMock(return_value=docs)
        app_ctx = MagicMock()
        app_ctx.get_metadata_store.return_value = metadata_store

        with patch(_PATCH_CTX, return_value=app_ctx):
            result = _run(list_repair_candidates_for_source_tag("fred"))

        by_uid = {r["document_uid"]: r["failed_or_running"] for r in result}
        assert by_uid == {
            "doc-failed-preview": True,
            "doc-failed-vector": True,
            "doc-in-progress": True,
            "doc-clean": False,
        }


class TestNeverTouchesTheEmbedderOrVectorStoreAdapter:
    """The structural safety guarantee for `list_strict_vector_document_uids`."""

    def test_never_calls_get_embedder_or_get_create_vector_store(self, monkeypatch):
        app_ctx = MagicMock()
        app_ctx.get_config.return_value.storage.vector_store = OpenSearchVectorIndexConfig(type="opensearch", index="fred-vectors")
        app_ctx.get_opensearch_client.return_value = _fake_search_client([_one_empty_page()])

        with patch(_PATCH_CTX, return_value=app_ctx):
            result = _run(list_strict_vector_document_uids())

        assert result == []
        app_ctx.get_embedder.assert_not_called()
        app_ctx.get_create_vector_store.assert_not_called()

    def test_never_constructs_an_opensearch_vector_store_adapter(self, monkeypatch):
        def _forbidden_init(self, *args, **kwargs):
            raise AssertionError("OpenSearchVectorStoreAdapter must never be constructed by the 3a repair path")

        monkeypatch.setattr(OpenSearchVectorStoreAdapter, "__init__", _forbidden_init)

        app_ctx = MagicMock()
        app_ctx.get_config.return_value.storage.vector_store = OpenSearchVectorIndexConfig(type="opensearch", index="fred-vectors")
        app_ctx.get_opensearch_client.return_value = _fake_search_client([_one_empty_page()])

        with patch(_PATCH_CTX, return_value=app_ctx):
            # Would raise AssertionError above if the forbidden constructor ran.
            result = _run(list_strict_vector_document_uids())

        assert result == []

    def test_never_touches_indices_or_ingest_pipeline_management(self):
        """No `indices.create`/`indices.put_mapping`/pipeline `put` call -- the
        only client method this activity may call is `search`."""
        app_ctx = MagicMock()
        app_ctx.get_config.return_value.storage.vector_store = OpenSearchVectorIndexConfig(type="opensearch", index="fred-vectors")
        client = _fake_search_client([_one_empty_page()])
        app_ctx.get_opensearch_client.return_value = client

        with patch(_PATCH_CTX, return_value=app_ctx):
            _run(list_strict_vector_document_uids())

        client.indices.create.assert_not_called()
        client.indices.put_mapping.assert_not_called()
        client.indices.exists.assert_not_called()
        client.ingest.put_pipeline.assert_not_called()

    def test_uses_the_configured_index_name_and_the_raw_opensearch_client(self):
        app_ctx = MagicMock()
        app_ctx.get_config.return_value.storage.vector_store = OpenSearchVectorIndexConfig(type="opensearch", index="fred-vectors-prod")
        client = _fake_search_client([_one_empty_page()])
        app_ctx.get_opensearch_client.return_value = client

        with patch(_PATCH_CTX, return_value=app_ctx):
            _run(list_strict_vector_document_uids())

        app_ctx.get_opensearch_client.assert_called_once()
        called_kwargs = client.search.call_args.kwargs
        assert called_kwargs["index"] == "fred-vectors-prod"

    def test_raises_a_clear_error_when_the_configured_backend_is_not_opensearch(self):
        app_ctx = MagicMock()
        app_ctx.get_config.return_value.storage.vector_store = ChromaVectorStorageConfig(type="chroma", local_path="/tmp/chroma", collection_name="c")

        with patch(_PATCH_CTX, return_value=app_ctx):
            with pytest.raises(RuntimeError, match="OpenSearch"):
                _run(list_strict_vector_document_uids())

        app_ctx.get_embedder.assert_not_called()
        app_ctx.get_create_vector_store.assert_not_called()
        app_ctx.get_opensearch_client.assert_not_called()

    def test_strict_scan_failure_propagates_instead_of_returning_an_incomplete_list(self):
        app_ctx = MagicMock()
        app_ctx.get_config.return_value.storage.vector_store = OpenSearchVectorIndexConfig(type="opensearch", index="fred-vectors")
        client = MagicMock()
        client.search = MagicMock(side_effect=RuntimeError("opensearch timeout"))
        app_ctx.get_opensearch_client.return_value = client

        with patch(_PATCH_CTX, return_value=app_ctx):
            with pytest.raises(RuntimeError, match="opensearch timeout"):
                _run(list_strict_vector_document_uids())


class TestListStrictContentDocumentUids:
    def test_calls_content_store_list_document_uids_strict(self):
        content_store = MagicMock()
        content_store.list_document_uids = MagicMock(return_value=["doc-1", "doc-2"])
        app_ctx = MagicMock()
        app_ctx.get_content_store.return_value = content_store

        with patch(_PATCH_CTX, return_value=app_ctx):
            result = _run(list_strict_content_document_uids())

        assert result == ["doc-1", "doc-2"]
        content_store.list_document_uids.assert_called_once_with(strict=True)

    def test_a_content_store_failure_propagates(self):
        content_store = MagicMock()
        content_store.list_document_uids = MagicMock(side_effect=RuntimeError("minio unreachable"))
        app_ctx = MagicMock()
        app_ctx.get_content_store.return_value = content_store

        with patch(_PATCH_CTX, return_value=app_ctx):
            with pytest.raises(RuntimeError, match="minio unreachable"):
                _run(list_strict_content_document_uids())


class TestBulkRepairVectorMetadata:
    def test_passes_source_tag_and_document_uids_through_to_the_store(self):
        metadata_store = MagicMock()
        metadata_store.bulk_mark_vector_done = AsyncMock(return_value=["doc-1", "doc-2"])
        app_ctx = MagicMock()
        app_ctx.get_metadata_store.return_value = metadata_store

        with patch(_PATCH_CTX, return_value=app_ctx):
            result = _run(bulk_repair_vector_metadata("fred", ["doc-1", "doc-2"]))

        assert result == ["doc-1", "doc-2"]
        metadata_store.bulk_mark_vector_done.assert_awaited_once_with("fred", ["doc-1", "doc-2"])

    def test_raises_clearly_when_the_metadata_store_lacks_bulk_mark_vector_done(self):
        app_ctx = MagicMock(spec=["get_metadata_store"])
        metadata_store = MagicMock(spec=[])  # no bulk_mark_vector_done attribute at all
        app_ctx.get_metadata_store.return_value = metadata_store

        with patch(_PATCH_CTX, return_value=app_ctx):
            with pytest.raises(RuntimeError, match="bulk_mark_vector_done"):
                _run(bulk_repair_vector_metadata("fred", ["doc-1"]))


class TestEmitRepairVectorMetadataTaskEvent:
    def test_succeeded_event_carries_the_structured_report(self):
        task_service = MagicMock()
        task_service.record = AsyncMock()
        app_ctx = MagicMock()
        app_ctx.get_task_service.return_value = task_service
        report = {
            "source_tag": "fred",
            "metadata_documents": 10,
            "already_done": 1,
            "eligible_with_vectors_and_content": 8,
            "repaired": 8,
            "missing_vectors": 1,
            "missing_content": 0,
            "tabular_excluded": 0,
            "errors": 0,
        }

        with patch(_PATCH_CTX, return_value=app_ctx):
            _run(emit_repair_vector_metadata_task_event("task-1", "succeeded", None, report))

        task_service.record.assert_awaited_once()
        (event,) = task_service.record.await_args.args
        assert event.state.value == "succeeded"
        assert event.detail.result.source_tag == "fred"
        assert event.detail.result.repaired == 8
        assert event.detail.processed == 8

    def test_failed_event_carries_the_error_and_no_result(self):
        task_service = MagicMock()
        task_service.record = AsyncMock()
        app_ctx = MagicMock()
        app_ctx.get_task_service.return_value = task_service

        with patch(_PATCH_CTX, return_value=app_ctx):
            _run(emit_repair_vector_metadata_task_event("task-1", "failed", "OpenSearch scan failed", None))

        (event,) = task_service.record.await_args.args
        assert event.state.value == "failed"
        assert event.error == "OpenSearch scan failed"
        assert event.detail.result is None
