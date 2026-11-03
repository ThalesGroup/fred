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

"""`MetadataService.update_document_retrievable`: the toggle reaches the vector
index or the request fails with the stored metadata unchanged. Real SQLite-backed
metadata store; the vector store is a recording fake."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fred_core.documents.document_structures import DocumentMetadata, Identity, ProcessingStage, SourceInfo, SourceType, Tagging
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.metadata.service import MetadataService, MetadataUpdateError


class _AllowAll:
    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        return None


class _VectorStore:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, bool]] = []

    def set_document_retrievable(self, *, document_uid: str, value: bool) -> None:
        self.calls.append((document_uid, value))
        if self.error:
            raise self.error


async def _service(tmp_path: Path, vector_store: _VectorStore, *, vectorized: bool = True) -> MetadataService:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retrievable.sqlite3'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    service = MetadataService.__new__(MetadataService)
    service.metadata_store = PostgresDocumentMetadataStore(engine)  # type: ignore[assignment]
    service.rebac = _AllowAll()  # type: ignore[assignment]
    service.vector_store = vector_store  # type: ignore[assignment]
    doc = DocumentMetadata(
        identity=Identity(document_name="doc-1.pdf", document_uid="doc-1", title="doc-1", modified=datetime.now(timezone.utc)),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred", retrievable=True),
        tags=Tagging(tag_ids=["lib-1"]),
    )
    if vectorized:
        doc.processing.mark_done(ProcessingStage.VECTORIZED)
    await service.metadata_store.save_metadata(doc)
    return service


def _user() -> SimpleNamespace:
    return SimpleNamespace(uid="u-1", username="u-1", email="u-1@localhost", roles=["admin"])


async def _stored_retrievable(service: MetadataService) -> bool:
    metadata = await service.metadata_store.get_metadata_by_uid("doc-1")
    assert metadata is not None
    return metadata.source.retrievable


@pytest.mark.asyncio
async def test_toggle_updates_the_vector_index_and_the_metadata(tmp_path) -> None:
    vectors = _VectorStore()
    service = await _service(tmp_path, vectors)

    await service.update_document_retrievable(_user(), "doc-1", False, "u-1")

    assert vectors.calls == [("doc-1", False)]
    assert await _stored_retrievable(service) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [NotImplementedError("no toggle support"), RuntimeError("index unavailable")])
async def test_toggle_fails_and_keeps_metadata_when_the_vector_index_cannot_apply_it(tmp_path, error: Exception) -> None:
    service = await _service(tmp_path, _VectorStore(error))

    with pytest.raises(MetadataUpdateError):
        await service.update_document_retrievable(_user(), "doc-1", False, "u-1")

    assert await _stored_retrievable(service) is True


@pytest.mark.asyncio
async def test_toggle_of_a_document_without_vectors_skips_the_vector_index(tmp_path) -> None:
    vectors = _VectorStore(RuntimeError("must not be called"))
    service = await _service(tmp_path, vectors, vectorized=False)

    await service.update_document_retrievable(_user(), "doc-1", False, "u-1")

    assert vectors.calls == []
    assert await _stored_retrievable(service) is False
