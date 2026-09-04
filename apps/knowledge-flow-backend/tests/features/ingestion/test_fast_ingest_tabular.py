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
ATTACH-TAB-01: CSV chat attachments build a real `tabular_v1` dataset
instead of the text-chunk vector preview other attachments get (DESIGN.md,
"Session-Scoped Attachment Datasets"). These tests cover the ingestion
controller's build/delete orchestration; `TabularService`'s ownership-based
authorization fallback is covered in `tests/services/test_tabular_service.py`.
"""

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
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tabular.artifacts import FAST_INGEST_SOURCE_TAG, read_tabular_artifact


def _user(uid: str = "u-1") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=f"{uid}@localhost", roles=["admin"])


def _controller_with_fake_metadata_service(save_document_metadata) -> IngestionController:
    controller = IngestionController.__new__(IngestionController)
    controller.service = SimpleNamespace(metadata_service=SimpleNamespace(save_document_metadata=save_document_metadata))
    controller._tabular_processor = TabularProcessor()
    return controller


@pytest.mark.asyncio
async def test_build_attachment_tabular_dataset_reuses_the_vector_chunk_document_uid(tmp_path: Path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("city,amount\nParis,10\nLyon,20\n", encoding="utf-8")

    saved: list = []

    async def _save_document_metadata(user, metadata):
        del user
        saved.append(metadata)

    controller = _controller_with_fake_metadata_service(_save_document_metadata)

    await controller._build_attachment_tabular_dataset(
        user=_user(),
        document_uid="doc-attachment",
        filename="sales.csv",
        raw_path=csv_path,
    )

    assert len(saved) == 1
    persisted = saved[0]
    assert persisted.document_uid == "doc-attachment"
    assert persisted.identity.uploaded_by == "u-1"
    assert persisted.source_tag == FAST_INGEST_SOURCE_TAG
    # No tags -> `_persist_metadata_and_follow_up` never writes a ReBAC
    # parent link for this document (DESIGN.md, "Session-Scoped Attachment
    # Datasets"); TabularService authorizes it by ownership metadata instead.
    assert persisted.tags.tag_ids == []
    artifact = read_tabular_artifact(persisted)
    assert artifact is not None
    assert artifact.row_count == 2


@pytest.mark.asyncio
async def test_build_attachment_tabular_dataset_raises_on_failure(tmp_path: Path):
    """
    Deliberately not best-effort: a CSV attachment skips vector-chunking
    entirely (DESIGN.md), so a failed tabular build would otherwise leave an
    attachment the agent can neither search nor query. The caller
    (`fast_ingest`) turns this into a 422, same as the empty-file check.
    """
    # A file that doesn't exist makes `TabularProcessor.process` raise before
    # any metadata is saved.
    missing_csv_path = tmp_path / "missing.csv"

    async def _save_document_metadata(*args, **kwargs):
        raise AssertionError("must not be called when tabular processing fails")

    controller = _controller_with_fake_metadata_service(_save_document_metadata)

    with pytest.raises(Exception):
        await controller._build_attachment_tabular_dataset(
            user=_user(),
            document_uid="doc-attachment",
            filename="missing.csv",
            raw_path=missing_csv_path,
        )


@pytest.mark.asyncio
async def test_build_attachment_tabular_dataset_does_not_collide_across_users_with_the_same_filename(tmp_path: Path, metadata_store):
    """
    Regression: an earlier version of this method built metadata via
    `IngestionService.extract_metadata()`, whose versioning step scans the
    whole metadata catalog for a document sharing the uploaded filename's
    canonical name and raises when one already exists — folder/tag semantics
    that make no sense for an untagged, session-scoped attachment. Building
    `DocumentMetadata` directly (no versioning, no corpus `document_sources`
    registry lookup) means two unrelated users attaching a file with the same
    common name (e.g. "sales.csv") never collide.
    """
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    controller = _controller_with_fake_metadata_service(MetadataService().save_document_metadata)

    for uid, uploader in [("doc-user-a", "user-a"), ("doc-user-b", "user-b")]:
        csv_path = tmp_path / uploader / "sales.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("city,amount\nParis,10\n", encoding="utf-8")

        await controller._build_attachment_tabular_dataset(
            user=_user(uploader),
            document_uid=uid,
            filename="sales.csv",
            raw_path=csv_path,
        )

    assert await metadata_store.get_metadata_by_uid("doc-user-a") is not None
    assert await metadata_store.get_metadata_by_uid("doc-user-b") is not None


@pytest.mark.asyncio
async def test_delete_attachment_tabular_dataset_removes_metadata_and_parquet(tmp_path: Path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("city,amount\nParis,10\n", encoding="utf-8")
    metadata = DocumentMetadata(
        identity=Identity(document_name="sales.csv", document_uid="doc-attachment", title="sales.csv", uploaded_by="u-1"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag=FAST_INGEST_SOURCE_TAG),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
        tags=Tagging(tag_ids=[]),
    )
    processed = TabularProcessor().process(str(csv_path), metadata, emit_pointer_chunk=False)
    await MetadataService().save_document_metadata(_user(), processed)
    assert await metadata_store.get_metadata_by_uid("doc-attachment") is not None

    controller = IngestionController.__new__(IngestionController)
    await controller._delete_attachment_tabular_dataset(user=_user(), document_uid="doc-attachment", is_platform_bypass=False)

    assert await metadata_store.get_metadata_by_uid("doc-attachment") is None


@pytest.mark.asyncio
async def test_delete_attachment_tabular_dataset_is_a_noop_for_text_only_attachments(metadata_store):
    # A non-CSV attachment (or a CSV where tabular processing failed) never
    # got a `tabular_v1` artifact — nothing to clean up, and no error.
    controller = IngestionController.__new__(IngestionController)
    await controller._delete_attachment_tabular_dataset(user=_user(), document_uid="doc-never-existed", is_platform_bypass=False)


@pytest.mark.asyncio
async def test_delete_attachment_tabular_dataset_refuses_a_non_owner_without_platform_bypass(tmp_path: Path, metadata_store):
    """
    Regression: `_authorize_fast_ingest_delete`'s "no vector chunks = safe
    retry" rule (`may_delete_session_document`) was designed for an
    idempotent vector-only delete and passes for ANY document with zero
    vector chunks — a CSV attachment always has zero (ATTACH-TAB-01 skips
    vector-chunking for CSV entirely). Without its own ownership check, this
    method would let any authenticated user delete any other user's
    attachment via `DELETE /fast/delete/{their_uid}`.
    """
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("city,amount\nParis,10\n", encoding="utf-8")
    metadata = DocumentMetadata(
        identity=Identity(document_name="sales.csv", document_uid="doc-attachment", title="sales.csv", uploaded_by="alice"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag=FAST_INGEST_SOURCE_TAG),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
        tags=Tagging(tag_ids=[]),
    )
    processed = TabularProcessor().process(str(csv_path), metadata, emit_pointer_chunk=False)
    await MetadataService().save_document_metadata(_user("alice"), processed)
    assert await metadata_store.get_metadata_by_uid("doc-attachment") is not None

    controller = IngestionController.__new__(IngestionController)
    await controller._delete_attachment_tabular_dataset(user=_user("attacker"), document_uid="doc-attachment", is_platform_bypass=False)

    # Alice's attachment must survive completely untouched.
    persisted = await metadata_store.get_metadata_by_uid("doc-attachment")
    assert persisted is not None
    assert read_tabular_artifact(persisted) is not None


@pytest.mark.asyncio
async def test_delete_attachment_tabular_dataset_refuses_a_corpus_document_even_with_platform_bypass(tmp_path: Path, metadata_store):
    """
    `source_tag == "fast_ingest"` stays a hard requirement regardless of
    `is_platform_bypass`: this narrow cleanup must never touch a corpus
    tabular dataset even for a platform caller — that document class has its
    own deletion path (quota release, tag/ReBAC cleanup) this one skips.
    """
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    csv_path = tmp_path / "quarterly.csv"
    csv_path.write_text("city,amount\nParis,10\n", encoding="utf-8")
    metadata = DocumentMetadata(
        identity=Identity(document_name="quarterly.csv", document_uid="doc-corpus", title="quarterly.csv", uploaded_by="owner-user"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred"),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
        tags=Tagging(tag_ids=["team-tag"]),
    )
    processed = TabularProcessor().process(str(csv_path), metadata, emit_pointer_chunk=False)
    await MetadataService().save_document_metadata(_user("owner-user"), processed)
    assert await metadata_store.get_metadata_by_uid("doc-corpus") is not None

    controller = IngestionController.__new__(IngestionController)
    await controller._delete_attachment_tabular_dataset(user=_user("platform-service"), document_uid="doc-corpus", is_platform_bypass=True)

    # The corpus document must survive completely untouched.
    persisted = await metadata_store.get_metadata_by_uid("doc-corpus")
    assert persisted is not None
    assert read_tabular_artifact(persisted) is not None


@pytest.mark.asyncio
async def test_delete_attachment_tabular_dataset_platform_bypass_deletes_another_users_attachment(tmp_path: Path, metadata_store):
    """
    P1 regression (codex review): scheduled conversation erasure (CTRLP-12)
    authenticates as a minted platform service bearer, never as the
    attachment's own uploader — `_authorize_fast_ingest_delete` already
    grants it a bypass, but this method used to re-derive ownership on its
    own with no accommodation for that bypass, so `uploaded_by == user.uid`
    was always false for the service account and cleanup silently no-oped.
    Erasure was then reported HTTP 200 / receipt-ok while the Parquet
    artifact and metadata row were orphaned with nothing left pointing at
    them to make the gap retryable. `is_platform_bypass=True` must actually
    delete the artifact, not skip it.
    """
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("city,amount\nParis,10\n", encoding="utf-8")
    metadata = DocumentMetadata(
        identity=Identity(document_name="sales.csv", document_uid="doc-alice", title="sales.csv", uploaded_by="alice"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag=FAST_INGEST_SOURCE_TAG),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
        tags=Tagging(tag_ids=[]),
    )
    processed = TabularProcessor().process(str(csv_path), metadata, emit_pointer_chunk=False)
    await MetadataService().save_document_metadata(_user("alice"), processed)
    assert await metadata_store.get_metadata_by_uid("doc-alice") is not None

    controller = IngestionController.__new__(IngestionController)
    await controller._delete_attachment_tabular_dataset(user=_user("platform-service"), document_uid="doc-alice", is_platform_bypass=True)

    assert await metadata_store.get_metadata_by_uid("doc-alice") is None
