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

"""What a person may not do to a folder a machine fills, and what stays open.

Two properties are worth more than the refusals themselves. The guard runs after
the caller's right is checked, so being refused never reveals which folders a
machine fills to someone who could not touch them anyway. And deleting the folder
is deliberately still allowed: a base is removed by deleting its folder, and a
guard there would make the base itself undeletable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fred_core import AuthorizationError, Resource
from fred_core.security.structure import SERVICE_AGENT_ROLE, KeycloakUser

import knowledge_flow_backend.features.tag.tag_service as tag_service_module
from knowledge_flow_backend.features.tag.structure import Tag, TagCreate, TagType, TagUpdate
from knowledge_flow_backend.features.tag.synchronized import FolderIsSynchronized

TagService = tag_service_module.TagService

TEAM = "team-1"
LIBRARY = "Mirror"
MACHINE = "knowledge_base:ab12"


def _tag(tag_id: str, name: str, path: str | None, synchronized_by: str | None = None) -> Tag:
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
        synchronized_by=synchronized_by,
    )


class _FakeRebac:
    def __init__(self, *, updatable: set[str], team_right: bool = True) -> None:
        self._updatable = updatable
        self._team_right = team_right
        self.relations: list[object] = []

    async def has_user_permission(self, user, permission, resource_id) -> bool:
        return resource_id in self._updatable

    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        if resource_id not in self._updatable:
            raise AuthorizationError(user.uid, str(permission), Resource.TAGS)

    async def check_user_team_permission_or_raise(self, *, user, permission, team_id):
        if not self._team_right:
            raise AuthorizationError(user.uid, str(permission), Resource.TEAM)

    async def add_relation(self, relation, actor_uid=None):
        self.relations.append(relation)

    async def add_user_relation(self, user, relation, *, resource_type, resource_id):
        self.relations.append(relation)


class _FakeItemService:
    """The documents a folder holds, and what deleting it does to them."""

    def __init__(self, item_ids: list[str]) -> None:
        self._item_ids = item_ids
        self.removed: list[tuple[str, str]] = []

    async def retrieve_items_ids_for_tag(self, user, tag_id: str) -> list[str]:
        return list(self._item_ids)

    async def remove_tag_id_from_item(self, user, item_id: str, tag_id_to_remove: str) -> None:
        self.removed.append((item_id, tag_id_to_remove))


class _FakeTagStore:
    def __init__(self, existing: list[Tag]) -> None:
        self.tags = {t.id: t for t in existing}
        self.created: Tag | None = None
        self.updated: Tag | None = None
        self.deleted: list[str] = []

    async def delete_tag_by_id(self, tag_id: str, session=None) -> None:
        self.deleted.append(tag_id)

    async def get_tag_by_id(self, tag_id: str, session=None) -> Tag:
        return self.tags[tag_id]

    async def get_by_owner_type_full_path(self, owner_id, tag_type, full_path, session=None):
        for tag in self.tags.values():
            if tag.owner_id == owner_id and tag.type == tag_type and tag.full_path == full_path:
                return tag
        return None

    async def create_tag(self, tag: Tag) -> Tag:
        self.created = tag
        return tag

    async def update_tag_by_id(self, tag_id: str, tag: Tag, session=None) -> Tag:
        self.updated = tag
        return tag


def _service(rebac: _FakeRebac, store: _FakeTagStore) -> TagService:
    service = TagService.__new__(TagService)
    service.rebac = rebac
    service._tag_store = store
    return service


def person() -> KeycloakUser:
    return KeycloakUser(uid="alice", username="alice", roles=["user"], email=None)


def machine() -> KeycloakUser:
    return KeycloakUser(uid="kb-pod", username="kb-pod", roles=[SERVICE_AGENT_ROLE], email=None)


def _library_tree() -> list[Tag]:
    return [
        _tag("lib", LIBRARY, None, MACHINE),
        _tag("sub", "specs", LIBRARY),
        _tag("plain", "Notes", None),
    ]


# --------------------------------------------------------------------------
# Creating a folder inside one a machine fills
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_person_cannot_create_a_folder_inside_a_library():
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"lib"}), store)

    with pytest.raises(FolderIsSynchronized) as refused:
        await service.create_tag_for_user(
            TagCreate(name="notes", path=LIBRARY, type=TagType.DOCUMENT, team_id=TEAM),
            person(),
        )

    assert refused.value.machine == MACHINE
    assert store.created is None


@pytest.mark.asyncio
async def test_the_refusal_reaches_a_folder_nested_deeper():
    """The mark lives on the library alone, so this proves the derivation."""
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"sub"}), store)

    with pytest.raises(FolderIsSynchronized):
        await service.create_tag_for_user(
            TagCreate(name="api", path=f"{LIBRARY}/specs", type=TagType.DOCUMENT, team_id=TEAM),
            person(),
        )

    assert store.created is None


@pytest.mark.asyncio
async def test_the_machine_still_creates_the_folders_its_source_needs():
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"lib"}), store)

    await service.create_tag_for_user(
        TagCreate(name="specs2", path=LIBRARY, type=TagType.DOCUMENT, team_id=TEAM),
        machine(),
    )

    assert store.created is not None and store.created.full_path == f"{LIBRARY}/specs2"


@pytest.mark.asyncio
async def test_a_folder_people_made_is_untouched_by_the_guard():
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"plain"}), store)

    await service.create_tag_for_user(
        TagCreate(name="drafts", path="Notes", type=TagType.DOCUMENT, team_id=TEAM),
        person(),
    )

    assert store.created is not None and store.created.full_path == "Notes/drafts"


# --------------------------------------------------------------------------
# Changing what a library holds, or what it is called
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_person_cannot_rename_a_library():
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"lib"}), store)

    with pytest.raises(FolderIsSynchronized):
        await service.update_tag_for_user(
            "lib",
            TagUpdate(name="Renamed", path=None, description=None, type=TagType.DOCUMENT, item_ids=[]),
            person(),
        )

    assert store.updated is None
    assert store.tags["lib"].name == LIBRARY


@pytest.mark.asyncio
async def test_a_person_cannot_change_what_a_nested_folder_holds():
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"sub"}), store)

    with pytest.raises(FolderIsSynchronized):
        await service.update_tag_for_user(
            "sub",
            TagUpdate(name="specs", path=LIBRARY, description=None, type=TagType.DOCUMENT, item_ids=["doc-1"]),
            person(),
        )

    assert store.updated is None


# --------------------------------------------------------------------------
# The two properties that matter more than the refusals
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_holding_no_right_is_reported_as_holding_no_right():
    """Refusing for the wrong reason would tell a stranger which folders are filled."""
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable=set(), team_right=False), store)

    with pytest.raises(AuthorizationError):
        await service.update_tag_for_user(
            "lib",
            TagUpdate(name="Renamed", path=None, description=None, type=TagType.DOCUMENT, item_ids=[]),
            person(),
        )


@pytest.mark.asyncio
async def test_creating_a_folder_refuses_on_the_right_before_the_machine():
    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable=set(), team_right=False), store)

    with pytest.raises(AuthorizationError):
        await service.create_tag_for_user(
            TagCreate(name="notes", path=LIBRARY, type=TagType.DOCUMENT, team_id=TEAM),
            person(),
        )

    assert store.created is None


@pytest.mark.asyncio
async def test_a_person_deletes_a_library_and_its_documents_are_released(monkeypatch):
    """Deleting the folder is how a base is removed, so a guard here would strand it.

    The instance's own deletion removes the library under the person's token, and
    that is where the right to delete anything at all is checked. Refusing here
    would leave a base nobody can take away.
    """
    item_service = _FakeItemService(["doc-1", "doc-2"])
    monkeypatch.setattr(tag_service_module, "get_specific_tag_item_service", lambda tag_type: item_service)

    store = _FakeTagStore(_library_tree())
    service = _service(_FakeRebac(updatable={"lib", "sub"}), store)
    library, nested = store.tags["lib"], store.tags["sub"]

    async def _subtree(user, tag_type, path_prefix=None, limit=None):
        return [library, nested]

    service.list_all_tags_for_user = _subtree

    await service.delete_tag_for_user("lib", person())

    assert store.deleted == ["lib", "sub"]
    assert ("doc-1", "lib") in item_service.removed
