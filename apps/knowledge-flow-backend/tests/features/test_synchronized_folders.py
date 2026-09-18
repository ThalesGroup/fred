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

"""Resolving which machine fills a folder, from anywhere in a library's tree.

Only the folder a library starts at carries the mark, so every answer about a
nested folder is derived. Getting that derivation wrong in the safe-looking
direction — reporting no machine — silently reopens every folder this guards.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fred_core import KeycloakUser
from fred_core.security.structure import SERVICE_AGENT_ROLE

from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
from knowledge_flow_backend.features.tag.structure import Tag, TagType
from knowledge_flow_backend.features.tag.synchronized import (
    FolderIsSynchronized,
    refuse_if_synchronized_by_id,
    synchronizing_machine,
)

OWNER = "team-1"
MACHINE = "knowledge_base:ab12"


class FakeTagStore:
    def __init__(self) -> None:
        self.tags: dict[str, Tag] = {}
        self.reads = 0

    def add(self, tag_id: str, name: str, path: str | None, synchronized_by: str | None = None) -> Tag:
        now = datetime.now(timezone.utc)
        tag = Tag(
            id=tag_id,
            created_at=now,
            updated_at=now,
            owner_id=OWNER,
            name=name,
            path=path,
            description=None,
            type=TagType.DOCUMENT,
            synchronized_by=synchronized_by,
        )
        self.tags[tag_id] = tag
        return tag

    async def get_tag_by_id(self, tag_id: str, session=None) -> Tag:
        self.reads += 1
        if tag_id not in self.tags:
            raise TagNotFoundError(tag_id)
        return self.tags[tag_id]

    async def get_by_owner_type_full_path(self, owner_id, tag_type, full_path, session=None):
        self.reads += 1
        for tag in self.tags.values():
            if tag.owner_id == owner_id and tag.type == tag_type and tag.full_path == full_path:
                return tag
        return None


def person(uid: str = "alice") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=["user"], email=None)


def machine_identity() -> KeycloakUser:
    return KeycloakUser(uid="kb-pod", username="kb-pod", roles=[SERVICE_AGENT_ROLE], email=None)


@pytest.fixture
def store() -> FakeTagStore:
    tags = FakeTagStore()
    tags.add("lib", "Mirror", None, MACHINE)
    tags.add("sub", "specs", "Mirror")
    tags.add("deep", "api", "Mirror/specs")
    tags.add("plain", "Notes", None)
    tags.add("plain-sub", "drafts", "Notes")
    return tags


@pytest.mark.asyncio
async def test_the_library_itself_answers_for_itself(store):
    assert await synchronizing_machine(store, store.tags["lib"]) == MACHINE


@pytest.mark.asyncio
@pytest.mark.parametrize("tag_id", ["sub", "deep"])
async def test_a_folder_at_any_depth_answers_with_its_library_s_machine(store, tag_id):
    assert await synchronizing_machine(store, store.tags[tag_id]) == MACHINE


@pytest.mark.asyncio
@pytest.mark.parametrize("tag_id", ["plain", "plain-sub"])
async def test_a_folder_people_made_reports_no_machine(store, tag_id):
    assert await synchronizing_machine(store, store.tags[tag_id]) is None


@pytest.mark.asyncio
async def test_a_top_level_folder_costs_no_second_read(store):
    """The root is its own answer, so nothing is looked up to find it."""
    store.reads = 0

    await synchronizing_machine(store, store.tags["lib"])

    assert store.reads == 0


@pytest.mark.asyncio
async def test_a_person_is_refused_inside_a_library(store):
    with pytest.raises(FolderIsSynchronized) as refused:
        await refuse_if_synchronized_by_id(store, "deep", person())

    assert refused.value.machine == MACHINE


@pytest.mark.asyncio
@pytest.mark.parametrize("tag_id", ["lib", "sub", "deep"])
async def test_the_machine_itself_is_never_refused(store, tag_id):
    await refuse_if_synchronized_by_id(store, tag_id, machine_identity())


@pytest.mark.asyncio
@pytest.mark.parametrize("tag_id", ["plain", "plain-sub"])
async def test_a_person_is_not_refused_in_a_folder_people_made(store, tag_id):
    await refuse_if_synchronized_by_id(store, tag_id, person())


@pytest.mark.asyncio
async def test_a_folder_that_does_not_exist_is_left_to_its_caller(store):
    """This guard has nothing to protect, and its caller reports absence better."""
    await refuse_if_synchronized_by_id(store, "absent", person())
