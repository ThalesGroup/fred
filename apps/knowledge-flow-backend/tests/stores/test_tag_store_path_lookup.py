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
import pytest_asyncio
from fred_core.models.base import Base
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
from knowledge_flow_backend.features.tag.structure import Tag, TagType

OWNER = "team-1"


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tags.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
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


@pytest.mark.asyncio
async def test_a_top_level_folder_is_found_by_its_own_name(store):
    await store.create_tag(_tag("lib", "Mirror", None))

    found = await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror")

    assert found is not None and found.id == "lib"


@pytest.mark.asyncio
async def test_a_nested_folder_is_found_by_its_whole_path(store):
    await store.create_tag(_tag("lib", "Mirror", None))
    await store.create_tag(_tag("sub", "specs", "Mirror"))
    await store.create_tag(_tag("deep", "api", "Mirror/specs"))

    assert (await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/specs")).id == "sub"
    assert (await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/specs/api")).id == "deep"


@pytest.mark.asyncio
async def test_the_same_path_under_another_owner_is_not_this_owner_s(store):
    await store.create_tag(_tag("their-root", "Mirror", None, owner_id="team-2"))
    await store.create_tag(_tag("theirs", "specs", "Mirror", owner_id="team-2"))

    assert await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/specs") is None


@pytest.mark.asyncio
async def test_a_path_nothing_holds_is_absent_rather_than_wrong(store):
    await store.create_tag(_tag("lib", "Mirror", None))

    assert await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Mirror/absent") is None
    assert await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "Elsewhere") is None


@pytest.mark.asyncio
async def test_a_name_carrying_a_slash_is_still_found(store):
    """Names are single segments now, but rows written before that are not rewritten.

    Splitting `A/B` into a parent and a leaf lands on halves this tag does not
    have, so only the fallback can find it — and it must, or a uniqueness check
    would stop seeing a folder that exists and would let a duplicate be created.
    """
    await store.create_tag(_tag("legacy", "A/B", None))

    found = await store.get_by_owner_type_full_path(OWNER, TagType.DOCUMENT, "A/B")

    assert found is not None and found.id == "legacy"


@pytest.mark.asyncio
async def test_owner_and_subtree_are_scoped_before_paging(store):
    for tag in [
        _tag("foreign-root", "Sales", None, owner_id="another-team"),
        _tag("sibling-root", "Salesforce", None),
        _tag("foreign", "A", "Sales", owner_id="another-team"),
        _tag("sibling", "A", "Salesforce"),
        _tag("root", "Sales", None),
        _tag("child", "B", "Sales"),
        _tag("child-2", "C", "Sales"),
        _tag("wildcard", "Sales_%", None),
        _tag("wildcard-child", "D", "Sales_%"),
    ]:
        await store.create_tag(tag)
    assert [tag.id for tag in await store.list_by_owner(OWNER, path_prefix="Sales", limit=2, offset=1)] == ["child", "child-2"]
    assert [tag.id for tag in await store.list_by_owner(OWNER, path_prefix="Sales_%")] == ["wildcard", "wildcard-child"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [None, ""])
async def test_database_rejects_duplicate_root_paths_including_empty_path(store, path):
    await store.create_tag(_tag("first", "Root", None))
    with pytest.raises(IntegrityError):
        await store.create_tag(_tag("duplicate", "Root", path))
    await store.create_tag(_tag("another-owner", "Root", path, owner_id="team-2"))


@pytest.mark.asyncio
async def test_database_rejects_rename_to_existing_folder(store):
    await store.create_tag(_tag("first", "First", None))
    await store.create_tag(_tag("second", "Second", None))
    with pytest.raises(IntegrityError):
        await store.update_tag_by_id("second", _tag("second", "First", None))
    assert (await store.get_tag_by_id("second")).name == "Second"


@pytest.mark.asyncio
async def test_legacy_flat_name_cannot_alias_a_nested_path(store):
    await store.create_tag(_tag("legacy", "A/B", None))
    await store.create_tag(_tag("real-parent", "A", None))
    with pytest.raises(IntegrityError):
        await store.create_tag(_tag("nested", "B", "A"))


@pytest.mark.asyncio
async def test_atomic_rename_preserves_ids_and_rewrites_only_descendants(store):
    for tag in [
        _tag("root", "A_%", None),
        _tag("child", "Child", "A_%"),
        _tag("deep", "Deep", "A_%/Child"),
        _tag("prefix", "A_%other", None),
        _tag("foreign", "A_%", None, owner_id="team-2"),
    ]:
        await store.create_tag(tag)
    renamed = await store.rename_tag("root", name="Renamed", description="new description")
    assert renamed.name == "Renamed" and renamed.description == "new description"
    assert (await store.get_tag_by_id("child")).full_path == "Renamed/Child"
    assert (await store.get_tag_by_id("deep")).full_path == "Renamed/Child/Deep"
    assert (await store.get_tag_by_id("prefix")).full_path == "A_%other"
    assert (await store.get_tag_by_id("foreign")).full_path == "A_%"
    await store.rename_tag("child", name="Nested", description=None)
    assert (await store.get_tag_by_id("deep")).full_path == "Renamed/Nested/Deep"


@pytest.mark.asyncio
async def test_conflicting_rename_rolls_back_entire_subtree(store):
    from knowledge_flow_backend.core.stores.tags.base_tag_store import TagAlreadyExistsError

    await store.create_tag(_tag("root", "Before", None))
    await store.create_tag(_tag("child", "Child", "Before"))
    await store.create_tag(_tag("taken", "Taken", None))
    with pytest.raises(TagAlreadyExistsError):
        await store.rename_tag("root", name="Taken", description="must roll back")
    assert (await store.get_tag_by_id("root")).full_path == "Before"
    assert (await store.get_tag_by_id("root")).description is None
    assert (await store.get_tag_by_id("child")).full_path == "Before/Child"


@pytest.mark.asyncio
async def test_timestamp_touch_preserves_current_name_and_source_cursor(store):
    tag = _tag("root", "Before", None)
    tag.source_version = "cursor"
    await store.create_tag(tag)
    await store.rename_tag("root", name="After", description="renamed")
    await store.touch_tag("root")
    after = await store.get_tag_by_id("root")
    assert (after.name, after.description, after.source_version) == ("After", "renamed", "cursor")


@pytest.mark.asyncio
async def test_rename_refuses_subtree_with_claimed_descendant(store):
    from fred_core.documents.tag_models import TagRow
    from sqlalchemy import update

    from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy

    await store.create_tag(_tag("root", "Root", None))
    await store.create_tag(_tag("child", "Child", "Root"))
    async with store._sessions.begin() as session:
        await session.execute(update(TagRow).where(TagRow.tag_id == "child").values(deletion_task_id="delete"))
    with pytest.raises(CorpusBusy):
        await store.rename_tag("root", name="After", description=None)
    assert (await store.get_tag_by_id("root")).name == "Root"
