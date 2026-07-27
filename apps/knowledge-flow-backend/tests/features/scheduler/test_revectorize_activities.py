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

"""Unit tests for the MIGR-07 corpus re-vectorization activities.

Covers `list_documents_in_scope`, `get_chunk_count`, `delete_vectors`, and
`prepare_revectorize_file` — thin activities over the existing ingestion/vector-store
building blocks (RFC docs/swift/rfc/CORPUS-REVECTORIZE-RFC.md §2-3). Mirrors
`test_emit_ingestion_task_event.py`'s pattern: call the `@activity.defn` function
directly (it's just a plain async function) and patch `ApplicationContext.get_instance`.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)
from temporalio import exceptions

from knowledge_flow_backend.features.scheduler.activities import (
    RevectorizePreparedFile,
    delete_vectors,
    get_chunk_count,
    list_documents_in_scope,
    mark_document_vectorized,
    prepare_revectorize_file,
)


def _run(coro):
    return asyncio.run(coro)


def _make_metadata(document_uid: str, document_name: str = "report.pdf", source_tag: str = "uploads") -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=document_name, document_uid=document_uid, title="sample"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag=source_tag),
        file=FileInfo(mime_type="application/pdf"),
        processing=Processing(),
    )


_PATCH_CTX = "knowledge_flow_backend.application_context.ApplicationContext.get_instance"


# ── list_documents_in_scope ────────────────────────────────────────────────────


def test_list_documents_in_scope_returns_document_uids_directly_without_querying_metadata_store():
    app_ctx = MagicMock()
    app_ctx.get_metadata_store.side_effect = AssertionError("must not query the metadata store when document_uids is given")

    with patch(_PATCH_CTX, return_value=app_ctx):
        result = _run(list_documents_in_scope({"document_uids": ["doc-1", "doc-2", "doc-1"]}))

    assert result == ["doc-1", "doc-2"]  # de-duplicated, order preserved


def test_list_documents_in_scope_resolves_via_tag_ids_filter():
    metadata_store = MagicMock()
    metadata_store.get_all_metadata = AsyncMock(return_value=[_make_metadata("doc-a"), _make_metadata("doc-b")])
    app_ctx = MagicMock()
    app_ctx.get_metadata_store.return_value = metadata_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        result = _run(list_documents_in_scope({"tag_ids": ["tag-1"]}))

    assert result == ["doc-a", "doc-b"]
    metadata_store.get_all_metadata.assert_awaited_once_with({"tag_ids": ["tag-1"]})


def test_list_documents_in_scope_resolves_via_source_tag_filter():
    metadata_store = MagicMock()
    metadata_store.get_all_metadata = AsyncMock(return_value=[_make_metadata("doc-a", source_tag="kea-import")])
    app_ctx = MagicMock()
    app_ctx.get_metadata_store.return_value = metadata_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        result = _run(list_documents_in_scope({"source_tag": "kea-import"}))

    assert result == ["doc-a"]
    metadata_store.get_all_metadata.assert_awaited_once_with({"source_tag": "kea-import"})


def test_list_documents_in_scope_combines_tag_ids_and_source_tag_filters():
    metadata_store = MagicMock()
    metadata_store.get_all_metadata = AsyncMock(return_value=[])
    app_ctx = MagicMock()
    app_ctx.get_metadata_store.return_value = metadata_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(list_documents_in_scope({"tag_ids": ["tag-1"], "source_tag": "kea-import"}))

    metadata_store.get_all_metadata.assert_awaited_once_with({"tag_ids": ["tag-1"], "source_tag": "kea-import"})


def test_list_documents_in_scope_raises_when_scope_has_no_usable_field():
    with pytest.raises(ValueError):
        _run(list_documents_in_scope({"library_id": "lib-1"}))


# ── get_chunk_count ─────────────────────────────────────────────────────────────


def test_get_chunk_count_returns_store_value():
    vector_store = MagicMock()
    vector_store.get_document_chunk_count.return_value = 7
    app_ctx = MagicMock()
    app_ctx.get_create_vector_store.return_value = vector_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        result = _run(get_chunk_count("doc-1"))

    assert result == 7
    vector_store.get_document_chunk_count.assert_called_once_with(document_uid="doc-1")


def test_get_chunk_count_returns_zero_when_store_lacks_the_method():
    vector_store = MagicMock(spec=[])  # no get_document_chunk_count attribute
    app_ctx = MagicMock()
    app_ctx.get_create_vector_store.return_value = vector_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        result = _run(get_chunk_count("doc-1"))

    assert result == 0


def test_get_chunk_count_returns_zero_when_store_raises():
    vector_store = MagicMock()
    vector_store.get_document_chunk_count.side_effect = RuntimeError("boom")
    app_ctx = MagicMock()
    app_ctx.get_create_vector_store.return_value = vector_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        result = _run(get_chunk_count("doc-1"))

    assert result == 0


# ── delete_vectors ──────────────────────────────────────────────────────────────


def test_delete_vectors_calls_vector_store_delete():
    vector_store = MagicMock()
    app_ctx = MagicMock()
    app_ctx.get_create_vector_store.return_value = vector_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(delete_vectors("doc-1"))

    vector_store.delete_vectors_for_document.assert_called_once_with(document_uid="doc-1")


# ── prepare_revectorize_file ────────────────────────────────────────────────────

_PATCH_GET_INGESTION_SERVICE = "knowledge_flow_backend.features.ingestion.ingestion_service.get_ingestion_service"

_USER = KeycloakUser(uid="alice", username="alice", email=None, roles=[]).model_dump()


def test_prepare_revectorize_file_builds_file_and_metadata_bundle():
    metadata = _make_metadata("doc-1", document_name="report.pdf", source_tag="kea-import")
    ingestion_service = MagicMock()
    ingestion_service.get_metadata = AsyncMock(return_value=metadata)

    with patch(_PATCH_GET_INGESTION_SERVICE, return_value=ingestion_service):
        result = _run(prepare_revectorize_file("doc-1", _USER))

    assert isinstance(result, RevectorizePreparedFile)
    assert result.metadata.document_uid == "doc-1"
    assert result.file.document_uid == "doc-1"
    assert result.file.source_tag == "kea-import"
    assert result.file.display_name == "report.pdf"
    assert result.file.processed_by.uid == "alice"


def test_prepare_revectorize_file_raises_non_retryable_when_document_missing():
    ingestion_service = MagicMock()
    ingestion_service.get_metadata = AsyncMock(return_value=None)

    with patch(_PATCH_GET_INGESTION_SERVICE, return_value=ingestion_service):
        with pytest.raises(exceptions.ApplicationError) as exc_info:
            _run(prepare_revectorize_file("missing-doc", _USER))

    assert exc_info.value.non_retryable is True


def test_prepare_revectorize_file_raises_non_retryable_when_source_tag_missing():
    metadata = _make_metadata("doc-1", source_tag="uploads")
    metadata.source.source_tag = None  # SourceInfo.source_tag is Optional[str] in practice
    ingestion_service = MagicMock()
    ingestion_service.get_metadata = AsyncMock(return_value=metadata)

    with patch(_PATCH_GET_INGESTION_SERVICE, return_value=ingestion_service):
        with pytest.raises(exceptions.ApplicationError) as exc_info:
            _run(prepare_revectorize_file("doc-1", _USER))

    assert exc_info.value.non_retryable is True


# ── mark_document_vectorized (MIGR-07.04) ───────────────────────────────────────


def test_mark_document_vectorized_marks_stage_done_and_saves():
    metadata = _make_metadata("doc-1")
    metadata.set_stage_status(ProcessingStage.VECTORIZED, ProcessingStatus.NOT_STARTED)
    metadata_store = MagicMock()
    metadata_store.get_metadata_by_uid = AsyncMock(return_value=metadata)
    metadata_store.save_metadata = AsyncMock()
    app_ctx = MagicMock()
    app_ctx.get_metadata_store.return_value = metadata_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(mark_document_vectorized("doc-1"))

    assert metadata.processing.stages[ProcessingStage.VECTORIZED] == ProcessingStatus.DONE
    metadata_store.get_metadata_by_uid.assert_awaited_once_with("doc-1")
    metadata_store.save_metadata.assert_awaited_once_with(metadata)


def test_mark_document_vectorized_is_a_noop_when_document_missing():
    metadata_store = MagicMock()
    metadata_store.get_metadata_by_uid = AsyncMock(return_value=None)
    metadata_store.save_metadata = AsyncMock()
    app_ctx = MagicMock()
    app_ctx.get_metadata_store.return_value = metadata_store

    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(mark_document_vectorized("missing-doc"))  # must not raise

    metadata_store.save_metadata.assert_not_awaited()
