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
`PostgresDocumentMetadataStore.count_by_team` — a document's team is indirect
(via a tag's `owner_id`, not a column on `metadata`), so this exercises the
`tag` <-> `metadata` join the `documents_total` KPI preset now relies on to be
`team_scopable` (NOTES-OBSERV-02-FOLLOWUPS.md #1). Runs against SQLite, which
takes the Python-fallback branch (no array `&&` operator) — the same branch
every other array-based method in this store already falls back to.
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
from fred_core.documents.tag_models import TagRow
from fred_core.models.base import Base
from fred_core.sql.async_session import make_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(uid: str, tag_ids: list[str]) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag="uploads", pull_location=None
        ),
        tags=Tagging(tag_ids=tag_ids),
    )


async def _add_tag(sessions: async_sessionmaker, tag_id: str, owner_id: str) -> None:
    # `PostgresDocumentMetadataStore` doesn't own tag writes — insert TagRow
    # directly, same as knowledge-flow's own PostgresTagStore would.
    async with sessions() as s:
        async with s.begin():
            s.add(TagRow(tag_id=tag_id, owner_id=owner_id))


@pytest.mark.asyncio
async def test_count_by_team_counts_documents_via_tag_ownership(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "count_by_team.sqlite3")
    sessions = make_session_factory(engine)
    store = PostgresDocumentMetadataStore(engine)
    await _add_tag(sessions, "tag-a", "team-1")
    await _add_tag(sessions, "tag-b", "team-2")

    await store.save_metadata(_doc("doc-1", ["tag-a"]))
    await store.save_metadata(_doc("doc-2", ["tag-a"]))
    await store.save_metadata(_doc("doc-3", ["tag-b"]))

    assert await store.count_by_team("team-1") == 2
    assert await store.count_by_team("team-2") == 1


@pytest.mark.asyncio
async def test_count_by_team_counts_a_document_once_even_with_multiple_team_tags(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "count_by_team_multi.sqlite3")
    sessions = make_session_factory(engine)
    store = PostgresDocumentMetadataStore(engine)
    await _add_tag(sessions, "tag-a", "team-1")
    await _add_tag(sessions, "tag-b", "team-1")

    await store.save_metadata(_doc("doc-1", ["tag-a", "tag-b"]))

    assert await store.count_by_team("team-1") == 1


@pytest.mark.asyncio
async def test_count_by_team_returns_zero_for_team_with_no_tags(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "count_by_team_empty.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1", ["tag-a"]))

    assert await store.count_by_team("no-such-team") == 0


@pytest.mark.asyncio
async def test_count_by_team_treats_personal_space_ids_like_any_other_owner(
    tmp_path: Path,
) -> None:
    """Personal-space tags carry `owner_id="personal-<uid>"` verbatim — same
    convention the `document.created_total`/`document.deleted_total` KPI
    events already use (`features/metadata/service.py`). No special-casing
    here keeps the store consistent with that existing dims.team_id value."""
    engine = await _make_sqlite_engine(tmp_path, "count_by_team_personal.sqlite3")
    sessions = make_session_factory(engine)
    store = PostgresDocumentMetadataStore(engine)
    await _add_tag(sessions, "tag-personal", "personal-u1")

    await store.save_metadata(_doc("doc-1", ["tag-personal"]))

    assert await store.count_by_team("personal-u1") == 1
