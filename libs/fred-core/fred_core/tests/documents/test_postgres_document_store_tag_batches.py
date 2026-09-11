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
`document_uids_by_tags` / `metadata_in_tags` — the batched reads that let a
folder listing resolve N libraries in one query instead of N.

Runs against SQLite, which takes the Python-fallback branch (no array `&&`
operator), like every other array-based method in this store. What is pinned
here is therefore the contract both branches must satisfy, not the SQL.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_store(tmp_path: Path) -> PostgresDocumentMetadataStore:
    engine: AsyncEngine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'batches.db'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return PostgresDocumentMetadataStore(engine=engine)


def _doc(uid: str, tag_ids: list[str]) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag="uploads", pull_location=None
        ),
        tags=Tagging(tag_ids=tag_ids),
    )


async def _seed(store: PostgresDocumentMetadataStore) -> None:
    await store.save_metadata(_doc("d1", ["t1"]))
    await store.save_metadata(_doc("d2", ["t1", "t2"]))
    await store.save_metadata(_doc("d3", ["t3"]))


@pytest.mark.asyncio
async def test_uids_by_tags_groups_each_requested_tag(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    await _seed(store)

    result = await store.document_uids_by_tags(["t1", "t2"])

    assert sorted(result["t1"]) == ["d1", "d2"]
    assert result["t2"] == ["d2"]
    # A tag that was not asked for contributes nothing, even though d3 exists.
    assert "t3" not in result


@pytest.mark.asyncio
async def test_uids_by_tags_reports_empty_tags_and_ignores_duplicates(
    tmp_path: Path,
) -> None:
    store = await _make_store(tmp_path)
    await _seed(store)

    # An empty library must still get a key: the caller builds one folder row
    # per requested tag and would otherwise have to guess the missing ones.
    result = await store.document_uids_by_tags(["t1", "t1", "empty"])

    assert result["empty"] == []
    assert sorted(result["t1"]) == ["d1", "d2"]
    assert await store.document_uids_by_tags([]) == {}


@pytest.mark.asyncio
async def test_metadata_in_tags_returns_the_union_once_each(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    await _seed(store)

    # d2 carries both requested tags — a corpus aggregate must not count it twice.
    docs = await store.metadata_in_tags(["t1", "t2"])

    assert sorted(d.identity.document_uid for d in docs) == ["d1", "d2"]
    assert await store.metadata_in_tags([]) == []
