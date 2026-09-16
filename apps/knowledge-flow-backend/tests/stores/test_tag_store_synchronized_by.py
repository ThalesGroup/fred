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

"""Which machine fills a folder survives storage, and the projections that expose it.

A folder is stored as a JSON document beside a few indexed columns, so this field
needed no schema change — which is only true as long as a folder written before
it existed still reads back, with the field absent rather than failing to parse.
The projections matter for the same reason: they rebuild a folder field by field,
and a reader that never receives the mark cannot withhold the actions it governs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.documents.tag_models import TagRow
from fred_core.models.base import Base
from fred_core.sql.async_session import make_session_factory
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
from knowledge_flow_backend.features.tag.structure import (
    Tag,
    TagType,
    TagWithItemsId,
    TagWithPermissions,
)

OWNER = "team-1"
MACHINE = "knowledge_base:ab12"


@asynccontextmanager
async def _engine(tmp_path: Path):
    """Disposed on the way out: an undisposed pool leaves a worker thread to be
    collected after the loop closes, which surfaces as teardown noise."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tags.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


def _tag(tag_id: str, name: str, synchronized_by: str | None) -> Tag:
    now = datetime.now(timezone.utc)
    return Tag(
        id=tag_id,
        created_at=now,
        updated_at=now,
        owner_id=OWNER,
        name=name,
        path=None,
        description=None,
        type=TagType.DOCUMENT,
        synchronized_by=synchronized_by,
    )


@pytest.mark.asyncio
async def test_a_marked_folder_reads_back_with_its_machine(tmp_path):
    async with _engine(tmp_path) as engine:
        store = PostgresTagStore(engine)
        await store.create_tag(_tag("lib", "Mirror", MACHINE))

        found = await store.get_tag_by_id("lib")

        assert found.synchronized_by == MACHINE
        assert found.is_synchronized


@pytest.mark.asyncio
async def test_an_unmarked_folder_is_written_by_people(tmp_path):
    async with _engine(tmp_path) as engine:
        store = PostgresTagStore(engine)
        await store.create_tag(_tag("plain", "Notes", None))

        found = await store.get_tag_by_id("plain")

        assert found.synchronized_by is None
        assert not found.is_synchronized


@pytest.mark.asyncio
async def test_a_folder_stored_before_the_field_existed_still_reads(tmp_path):
    """The row this writes is what every folder in an existing deployment looks like."""
    async with _engine(tmp_path) as engine:
        store = PostgresTagStore(engine)
        stored = _tag("old", "Legacy", None).model_dump(mode="json")
        del stored["synchronized_by"]

        sessions = make_session_factory(engine)
        async with sessions() as session:
            session.add(
                TagRow(
                    tag_id="old",
                    created_at=None,
                    updated_at=None,
                    owner_id=OWNER,
                    name="Legacy",
                    path=None,
                    description=None,
                    type=TagType.DOCUMENT.value,
                    doc=stored,
                )
            )
            await session.commit()

        found = await store.get_tag_by_id("old")

        assert found.synchronized_by is None
        assert not found.is_synchronized


@pytest.mark.asyncio
async def test_updating_a_folder_keeps_its_machine(tmp_path):
    """Renaming happens through a full rewrite of the document, so the mark rides along."""
    async with _engine(tmp_path) as engine:
        store = PostgresTagStore(engine)
        await store.create_tag(_tag("lib", "Mirror", MACHINE))

        renamed = await store.get_tag_by_id("lib")
        renamed.description = "Synchronized by WebDAV share"
        await store.update_tag_by_id("lib", renamed)

        assert (await store.get_tag_by_id("lib")).synchronized_by == MACHINE


def test_the_projections_a_reader_receives_carry_the_machine():
    """These rebuild a folder field by field, which is where a new field gets dropped."""
    marked = _tag("lib", "Mirror", MACHINE)

    with_items = TagWithItemsId.from_tag(marked, item_ids=[])
    with_permissions = TagWithPermissions.from_tag_with_items(with_items, permissions=[])

    assert with_items.synchronized_by == MACHINE
    assert with_permissions.synchronized_by == MACHINE


def test_an_unmarked_folder_is_omitted_rather_than_sent_as_null():
    """The tag routes serialize excluding none, so a reader sees the key or nothing."""
    plain = TagWithItemsId.from_tag(_tag("plain", "Notes", None), item_ids=[])

    assert "synchronized_by" not in plain.model_dump(exclude_none=True)
