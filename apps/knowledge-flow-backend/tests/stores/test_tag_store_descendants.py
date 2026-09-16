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

"""Every folder under one path, which is how a library's documents are found.

A document carries the folder it sits in and never the library above it, so
listing what a library holds starts here. The failure that matters is not
missing a folder — it is claiming one that belongs to a sibling, because a
prefix match over a path column is one careless character away from doing that.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
from knowledge_flow_backend.features.tag.structure import Tag, TagType

OWNER = "team-1"


@asynccontextmanager
async def _store(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tags.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield PostgresTagStore(engine)
    finally:
        await engine.dispose()


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


async def _descendants(store: PostgresTagStore, full_path: str) -> set[str]:
    found = await store.list_descendants(OWNER, TagType.DOCUMENT, full_path)
    return {tag.id for tag in found}


@pytest.mark.asyncio
async def test_every_depth_below_the_folder_is_returned(tmp_path):
    async with _store(tmp_path) as store:
        await store.create_tag(_tag("lib", "Mirror", None))
        await store.create_tag(_tag("sub", "specs", "Mirror"))
        await store.create_tag(_tag("deep", "api", "Mirror/specs"))
        await store.create_tag(_tag("deeper", "v2", "Mirror/specs/api"))

        assert await _descendants(store, "Mirror") == {"sub", "deep", "deeper"}


@pytest.mark.asyncio
async def test_the_folder_itself_is_not_one_of_its_descendants(tmp_path):
    """Its caller already holds it; returning it twice would double a count."""
    async with _store(tmp_path) as store:
        await store.create_tag(_tag("lib", "Mirror", None))

        assert await _descendants(store, "Mirror") == set()


@pytest.mark.asyncio
async def test_a_sibling_sharing_the_start_of_the_name_is_not_claimed(tmp_path):
    """`Mirror2` is not inside `Mirror`, however much its path looks like it."""
    async with _store(tmp_path) as store:
        await store.create_tag(_tag("lib", "Mirror", None))
        await store.create_tag(_tag("sub", "specs", "Mirror"))
        await store.create_tag(_tag("other", "Mirror2", None))
        await store.create_tag(_tag("other-sub", "specs", "Mirror2"))

        assert await _descendants(store, "Mirror") == {"sub"}


@pytest.mark.asyncio
async def test_a_wildcard_in_a_folder_name_matches_only_itself(tmp_path):
    """A name may contain what the query language reads as a wildcard."""
    async with _store(tmp_path) as store:
        await store.create_tag(_tag("pattern", "Q%", None))
        await store.create_tag(_tag("under-pattern", "notes", "Q%"))
        await store.create_tag(_tag("decoy", "QA", None))
        await store.create_tag(_tag("under-decoy", "notes", "QA"))

        assert await _descendants(store, "Q%") == {"under-pattern"}


@pytest.mark.asyncio
async def test_another_owner_s_identical_tree_is_not_returned(tmp_path):
    async with _store(tmp_path) as store:
        await store.create_tag(_tag("lib", "Mirror", None))
        await store.create_tag(_tag("sub", "specs", "Mirror"))
        await store.create_tag(_tag("theirs", "specs", "Mirror", owner_id="team-2"))

        assert await _descendants(store, "Mirror") == {"sub"}


@pytest.mark.asyncio
async def test_another_kind_of_folder_is_not_returned(tmp_path):
    async with _store(tmp_path) as store:
        await store.create_tag(_tag("lib", "Mirror", None))
        await store.create_tag(_tag("sub", "specs", "Mirror"))
        prompts = _tag("prompt-sub", "specs", "Mirror")
        prompts.id = "prompt-sub"
        prompts.type = TagType.PROMPT
        await store.create_tag(prompts)

        assert await _descendants(store, "Mirror") == {"sub"}
