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
`PostgresDocumentMetadataStore.update_metadata` — the conditional UPDATE that
makes a deleted document impossible to resurrect (#2315).

An ingestion activity runs its work in a thread Python cannot kill, so it keeps
going after a cancellation deleted the document and then persists what it
computed. Through `save_metadata` (an upsert) that write re-creates the row,
stuck `in_progress` forever. `update_metadata` reports "no such document"
instead of creating one — the same atomic-decision rule `delete_metadata`
already carries (#2149).

Runs against SQLite, like the store's other tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_sqlite_engine(tmp_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'update.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(uid: str, title: str = "original") -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=title),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag="uploads", pull_location=None
        ),
    )


@pytest.mark.asyncio
async def test_update_metadata_writes_and_reports_true_for_a_live_document(tmp_path):
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("doc-1"))

    updated = _doc("doc-1", title="renamed")
    updated.processing.stages[ProcessingStage.PREVIEW_READY] = ProcessingStatus.DONE

    assert await store.update_metadata(updated) is True
    stored = await store.get_metadata_by_uid("doc-1")
    assert stored is not None
    assert stored.identity.title == "renamed"
    assert (
        stored.processing.stages[ProcessingStage.PREVIEW_READY] == ProcessingStatus.DONE
    )


@pytest.mark.asyncio
async def test_update_metadata_never_resurrects_a_deleted_document(tmp_path):
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("doc-1"))
    assert await store.delete_metadata("doc-1") is True

    # This is the zombie write: an unkillable activity thread finishing its work
    # long after the cancellation deleted the document.
    late = _doc("doc-1")
    late.processing.stages[ProcessingStage.PREVIEW_READY] = ProcessingStatus.IN_PROGRESS

    assert await store.update_metadata(late) is False
    assert await store.get_metadata_by_uid("doc-1") is None


@pytest.mark.asyncio
async def test_save_metadata_still_creates(tmp_path):
    # The registration path must keep its create semantics — `update_metadata`
    # narrows only the in-flight writers.
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))

    await store.save_metadata(_doc("doc-new"))

    assert await store.get_metadata_by_uid("doc-new") is not None
