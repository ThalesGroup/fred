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

"""Unit tests for MetadataService.audit_stores / fix_store_anomalies.

fix_store_anomalies must never delete a document's metadata over a
missing_content/missing_vectors finding — those are recoverable/pending
situations, not orphans. Only orphan_vectors/orphan_content (data with no
metadata row at all) are safe to delete. See service.py's fix_store_anomalies
docstring for the reasoning; this test file is the regression guard for it.
"""

from datetime import datetime, timezone

import pytest
from fred_core.documents.document_structures import (
    AccessInfo,
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.features.metadata.service import MetadataService


def _make_metadata(uid: str, *, raw_done: bool, preview_done: bool, vectorized_done: bool) -> DocumentMetadata:
    processing = Processing()
    if raw_done:
        processing.mark_done(ProcessingStage.RAW_AVAILABLE)
    if preview_done:
        processing.mark_done(ProcessingStage.PREVIEW_READY)
    if vectorized_done:
        processing.mark_done(ProcessingStage.VECTORIZED)
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, modified=datetime.now(timezone.utc)),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads", date_added_to_kb=datetime.now(timezone.utc)),
        file=FileInfo(),
        tags=Tagging(tag_ids=[]),
        processing=processing,
        access=AccessInfo(),
    )


class _FakeRebac:
    async def check_user_permission_or_raise(self, user, permission, resource_id) -> None:
        del user, permission, resource_id


class _FakeMetadataStore:
    def __init__(self, docs: dict[str, DocumentMetadata]):
        self.docs = docs
        self.deleted: list[str] = []
        self.saved: list[str] = []

    async def get_all_metadata(self, filters: dict) -> list[DocumentMetadata]:
        del filters
        return list(self.docs.values())

    async def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata | None:
        return self.docs.get(document_uid)

    async def save_metadata(self, metadata: DocumentMetadata) -> None:
        self.docs[metadata.document_uid] = metadata
        self.saved.append(metadata.document_uid)

    async def delete_metadata(self, document_uid: str) -> None:
        self.docs.pop(document_uid, None)
        self.deleted.append(document_uid)


class _FakeContentStore:
    def __init__(self, uids: set[str]):
        self.uids = set(uids)
        self.deleted: list[str] = []

    def list_document_uids(self) -> set[str]:
        return self.uids

    def delete_content(self, document_uid: str) -> None:
        self.uids.discard(document_uid)
        self.deleted.append(document_uid)


class _FakeVectorStore:
    def __init__(self, uids: set[str], chunk_counts: dict[str, int] | None = None):
        self.uids = set(uids)
        self.chunk_counts = chunk_counts or {}
        self.deleted: list[str] = []

    def list_document_uids(self) -> set[str]:
        return self.uids

    def get_document_chunk_count(self, *, document_uid: str) -> int:
        return self.chunk_counts.get(document_uid, 0)

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        self.uids.discard(document_uid)
        self.deleted.append(document_uid)


def _build_service(*, docs, content_uids, vector_uids) -> MetadataService:
    service = MetadataService.__new__(MetadataService)
    service.metadata_store = _FakeMetadataStore(docs)
    service.content_store = _FakeContentStore(content_uids)
    service.vector_store = _FakeVectorStore(vector_uids)
    service.rebac = _FakeRebac()
    return service


@pytest.mark.asyncio
async def test_missing_vectors_resets_stage_never_deletes_metadata():
    doc = _make_metadata("doc-1", raw_done=True, preview_done=True, vectorized_done=True)
    service = _build_service(
        docs={"doc-1": doc},
        content_uids={"doc-1"},
        vector_uids=set(),  # claimed VECTORIZED=DONE but absent from the vector store
    )

    report = await service.audit_stores(user=object())
    assert report.has_anomalies
    assert report.anomalies[0].issues == ["missing_vectors"]

    fixed = await service.fix_store_anomalies(user=object())

    # The document must still exist — only its stage flag is corrected.
    assert "doc-1" in service.metadata_store.docs
    assert service.metadata_store.deleted == []
    assert fixed.reset_metadata == ["doc-1"]
    surviving = service.metadata_store.docs["doc-1"]
    assert surviving.processing.stages[ProcessingStage.VECTORIZED] == ProcessingStatus.NOT_STARTED
    # Unrelated stages are untouched.
    assert surviving.processing.stages[ProcessingStage.RAW_AVAILABLE] == ProcessingStatus.DONE
    assert surviving.processing.stages[ProcessingStage.PREVIEW_READY] == ProcessingStatus.DONE

    after = await service.audit_stores(user=object())
    assert not after.has_anomalies


@pytest.mark.asyncio
async def test_missing_content_cascades_reset_never_deletes_metadata():
    doc = _make_metadata("doc-2", raw_done=True, preview_done=True, vectorized_done=True)
    service = _build_service(
        docs={"doc-2": doc},
        content_uids=set(),  # claimed RAW_AVAILABLE=DONE but absent from the content store
        vector_uids={"doc-2"},
    )

    fixed = await service.fix_store_anomalies(user=object())

    assert "doc-2" in service.metadata_store.docs
    assert service.metadata_store.deleted == []
    assert fixed.reset_metadata == ["doc-2"]
    surviving = service.metadata_store.docs["doc-2"]
    # Every downstream stage's DONE claim was equally unearned — all reset.
    assert surviving.processing.stages[ProcessingStage.RAW_AVAILABLE] == ProcessingStatus.NOT_STARTED
    assert surviving.processing.stages[ProcessingStage.PREVIEW_READY] == ProcessingStatus.NOT_STARTED
    assert surviving.processing.stages[ProcessingStage.VECTORIZED] == ProcessingStatus.NOT_STARTED


@pytest.mark.asyncio
async def test_orphan_vectors_and_content_are_reported_never_deleted():
    """fix_store_anomalies must leave orphans alone — a platform admin decides
    by hand whether to delete or investigate first. This is a deliberate
    product decision (2026-07-25): the audit only ever reports or repairs a
    lying stage flag, it never deletes data on its own."""
    service = _build_service(
        docs={},
        content_uids={"orphan-content-doc"},
        vector_uids={"orphan-vector-doc"},
    )

    report = await service.audit_stores(user=object())
    issue_by_uid = {f.document_uid: set(f.issues) for f in report.anomalies}
    assert issue_by_uid["orphan-content-doc"] == {"orphan_content"}
    assert issue_by_uid["orphan-vector-doc"] == {"orphan_vectors"}

    fixed = await service.fix_store_anomalies(user=object())

    assert fixed.reset_metadata == []
    # Nothing was touched — the orphans are exactly as before.
    assert service.content_store.uids == {"orphan-content-doc"}
    assert service.vector_store.uids == {"orphan-vector-doc"}
    assert service.content_store.deleted == []
    assert service.vector_store.deleted == []

    after = await service.audit_stores(user=object())
    assert after.has_anomalies
    assert len(after.anomalies) == 2


@pytest.mark.asyncio
async def test_fix_response_has_no_deletion_fields():
    """Regression guard: deleted_metadata/deleted_vectors/deleted_content were
    removed, not merely left empty — fix_store_anomalies must never be able
    to report deleting anything again."""
    from knowledge_flow_backend.features.metadata.service import StoreAuditFixResponse

    assert "deleted_metadata" not in StoreAuditFixResponse.model_fields
    assert "deleted_vectors" not in StoreAuditFixResponse.model_fields
    assert "deleted_content" not in StoreAuditFixResponse.model_fields
    assert "reset_metadata" in StoreAuditFixResponse.model_fields
