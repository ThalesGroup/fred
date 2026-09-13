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

"""Creating a folder inside another is authorized by the right to write in it.

Every other permission on a tag inherits downward through `parent`; folder
creation alone asked for a team-level right, so a subject able to fill one
folder could not create a folder in it. That asymmetry applies to people, and to
any workload granted one library — a Knowledge Base pod holds `editor` over its
own library and must never hold anything over the team.

Creating a top-level folder still takes the team right, so being able to fill
one folder never becomes being able to add folders to a team.
"""

from datetime import datetime, timezone

import pytest
from fred_core import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser

import knowledge_flow_backend.features.tag.tag_service as tag_service_module
from knowledge_flow_backend.features.tag.structure import Tag, TagCreate, TagType

TagService = tag_service_module.TagService

TEAM = "team-1"
PARENT_PATH = "Library"


def _tag(tag_id: str, name: str, path: str | None) -> Tag:
    now = datetime.now(timezone.utc)
    return Tag(
        id=tag_id,
        created_at=now,
        updated_at=now,
        owner_id=TEAM,
        name=name,
        path=path,
        description=None,
        type=TagType.DOCUMENT,
    )


class _FakeRebac:
    """Grants `update` on the tags named, and the team right only if told to."""

    def __init__(self, *, updatable: set[str], team_right: bool) -> None:
        self._updatable = updatable
        self._team_right = team_right
        self.team_checked = False
        self.relations: list[object] = []

    async def has_user_permission(self, user, permission, resource_id) -> bool:
        return resource_id in self._updatable

    async def check_user_team_permission_or_raise(self, *, user, permission, team_id):
        self.team_checked = True
        if not self._team_right:
            raise AuthorizationError(user.uid, str(permission), Resource.TEAM)

    async def add_relation(self, relation, actor_uid=None):
        self.relations.append(relation)

    async def add_user_relation(self, user, relation, *, resource_type, resource_id):
        self.relations.append(relation)


class _FakeTagStore:
    def __init__(self, existing: list[Tag]) -> None:
        self._existing = {t.full_path: t for t in existing}
        self.created: Tag | None = None

    async def get_by_owner_type_full_path(self, owner_id, tag_type, full_path, session=None):
        return self._existing.get(full_path)

    async def create_tag(self, tag: Tag) -> Tag:
        self.created = tag
        return tag


def _service(rebac: _FakeRebac, store: _FakeTagStore) -> TagService:
    service = TagService.__new__(TagService)
    service.rebac = rebac
    service._tag_store = store
    return service


def _user() -> KeycloakUser:
    return KeycloakUser(uid="pod", username="pod", roles=[], email=None)


@pytest.mark.asyncio
async def test_writing_in_a_folder_is_enough_to_create_one_inside_it():
    parent = _tag("parent", PARENT_PATH, None)
    rebac = _FakeRebac(updatable={"parent"}, team_right=False)
    store = _FakeTagStore([parent])

    await _service(rebac, store).create_tag_for_user(
        TagCreate(name="sub", path=PARENT_PATH, type=TagType.DOCUMENT, team_id=TEAM),
        _user(),
    )

    assert store.created is not None
    assert store.created.full_path == f"{PARENT_PATH}/sub"
    # The team right was never needed, so it was never asked for.
    assert rebac.team_checked is False


@pytest.mark.asyncio
async def test_writing_in_a_folder_does_not_confer_creating_a_top_level_one():
    rebac = _FakeRebac(updatable={"parent"}, team_right=False)
    store = _FakeTagStore([_tag("parent", PARENT_PATH, None)])

    with pytest.raises(AuthorizationError):
        await _service(rebac, store).create_tag_for_user(
            TagCreate(name="Elsewhere", type=TagType.DOCUMENT, team_id=TEAM),
            _user(),
        )

    assert store.created is None


@pytest.mark.asyncio
async def test_the_team_right_still_creates_a_top_level_folder():
    rebac = _FakeRebac(updatable=set(), team_right=True)
    store = _FakeTagStore([])

    await _service(rebac, store).create_tag_for_user(
        TagCreate(name="Reports", type=TagType.DOCUMENT, team_id=TEAM),
        _user(),
    )

    assert store.created is not None
    assert store.created.full_path == "Reports"
    assert rebac.team_checked is True


@pytest.mark.asyncio
async def test_the_team_right_still_creates_a_nested_folder_without_the_parent_right():
    """The previous path keeps working: nothing that was permitted becomes refused."""
    rebac = _FakeRebac(updatable=set(), team_right=True)
    store = _FakeTagStore([_tag("parent", PARENT_PATH, None)])

    await _service(rebac, store).create_tag_for_user(
        TagCreate(name="sub", path=PARENT_PATH, type=TagType.DOCUMENT, team_id=TEAM),
        _user(),
    )

    assert store.created is not None
    assert rebac.team_checked is True


@pytest.mark.asyncio
async def test_neither_right_creates_nothing():
    rebac = _FakeRebac(updatable=set(), team_right=False)
    store = _FakeTagStore([_tag("parent", PARENT_PATH, None)])

    with pytest.raises(AuthorizationError):
        await _service(rebac, store).create_tag_for_user(
            TagCreate(name="sub", path=PARENT_PATH, type=TagType.DOCUMENT, team_id=TEAM),
            _user(),
        )

    assert store.created is None


@pytest.mark.asyncio
async def test_a_missing_parent_falls_back_to_the_team_right():
    """An orphan nest was permitted before and stays permitted, on the team right.

    Refusing it here would be a second behaviour change riding along with this
    one, and the parent that is missing cannot authorize anything.
    """
    rebac = _FakeRebac(updatable=set(), team_right=True)
    store = _FakeTagStore([])

    await _service(rebac, store).create_tag_for_user(
        TagCreate(name="sub", path="Nowhere", type=TagType.DOCUMENT, team_id=TEAM),
        _user(),
    )

    assert store.created is not None
    assert rebac.team_checked is True
