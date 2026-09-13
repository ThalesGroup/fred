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

"""Finding one folder by its path, without reading every folder its owner has.

This lookup is asked once per folder of every document a synchronizing caller
writes, so a scan of the whole table per path segment is not affordable. It is
answered from the indexed name and path columns, and still finds what the scan
found — including a tag stored before names were validated, whose own name
carries a "/" and whose path therefore cannot be split.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
from knowledge_flow_backend.features.tag.structure import Tag, TagType

OWNER = "team-1"


async def _store(tmp_path: Path) -> PostgresTagStore:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tags.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return PostgresTagStore(engine)


def _tag(tag_id: str, name: str, path: str | None, owner_id: str = OWNER) -> Tag:
    now = datetime.now(timezone.utc)
    return Tag(
        id=tag_id,
        created_at=now,
        updated_at=now,
        owner_id=owner_id,
        name=name,
        path=path,
        description=None,
        type=TagType.DOCUMENT,
    )


@pytest.mark.asyncio
async def test_a_top_level_folder_is_found_by_its_own_name(tmp_path):
    store = await _store(tmp_path)
    await store.create_tag(_tag("lib", "Mirror", None))

    found = await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror")

    assert found is not None and found.id == "lib"


@pytest.mark.asyncio
async def test_a_nested_folder_is_found_by_its_whole_path(tmp_path):
    store = await _store(tmp_path)
    await store.create_tag(_tag("lib", "Mirror", None))
    await store.create_tag(_tag("sub", "specs", "Mirror"))
    await store.create_tag(_tag("deep", "api", "Mirror/specs"))

    assert (await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/specs")).id == "sub"
    assert (await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/specs/api")).id == "deep"


@pytest.mark.asyncio
async def test_the_same_path_under_another_owner_is_not_this_owner_s(tmp_path):
    store = await _store(tmp_path)
    await store.create_tag(_tag("theirs", "specs", "Mirror", owner_id="team-2"))

    assert await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/specs") is None


@pytest.mark.asyncio
async def test_a_path_nothing_holds_is_absent_rather_than_wrong(tmp_path):
    store = await _store(tmp_path)
    await store.create_tag(_tag("lib", "Mirror", None))

    assert await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/absent") is None
    assert await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Elsewhere") is None


@pytest.mark.asyncio
async def test_a_name_carrying_a_slash_is_still_found(tmp_path):
    """Names are single segments now, but rows written before that are not rewritten.

    Splitting `A/B` into a parent and a leaf lands on halves this tag does not
    have, so only the fallback can find it — and it must, or a uniqueness check
    would stop seeing a folder that exists and would let a duplicate be created.
    """
    store = await _store(tmp_path)
    await store.create_tag(_tag("legacy", "A/B", None))

    found = await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "A/B")

    assert found is not None and found.id == "legacy"
