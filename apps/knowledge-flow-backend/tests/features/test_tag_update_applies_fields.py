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

"""`update_tag_for_user` must persist name/path/description changes.

Regression: the service loaded the stored tag, diffed only its item_ids, and
saved it back unchanged — so every rename (folder or tag) was silently dropped
and appeared to do nothing in the UI.
"""

from datetime import datetime, timezone

import pytest
from fred_core.security.structure import KeycloakUser

import knowledge_flow_backend.features.tag.tag_service as tag_service_module
from knowledge_flow_backend.features.tag.structure import Tag, TagType, TagUpdate

TagService = tag_service_module.TagService


class _FakeRebac:
    async def check_user_permission_or_raise(self, user, permission, tag_id):
        return None


class _FakeTagStore:
    def __init__(self, tag: Tag) -> None:
        self._tag = tag
        self.saved: Tag | None = None

    async def get_tag_by_id(self, tag_id: str) -> Tag:
        return self._tag

    async def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        self.saved = tag
        return tag


class _FakeItemService:
    async def retrieve_items_ids_for_tag(self, user, tag_id):
        return []

    async def add_tag_id_to_item(self, user, item_id, tag_id):
        return None

    async def remove_tag_id_from_item(self, user, item_id, tag_id):
        return None


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=[], email=None)


@pytest.mark.asyncio
async def test_update_applies_name_and_path(monkeypatch):
    now = datetime.now(timezone.utc)
    existing = Tag(
        id="t1",
        created_at=now,
        updated_at=now,
        owner_id="u",
        name="Reports",
        path=None,
        description="old",
        type=TagType.DOCUMENT,
    )
    store = _FakeTagStore(existing)
    monkeypatch.setattr(tag_service_module, "get_specific_tag_item_service", lambda _type: _FakeItemService())

    svc = TagService.__new__(TagService)
    svc.rebac = _FakeRebac()
    svc._tag_store = store

    await svc.update_tag_for_user(
        "t1",
        TagUpdate(name="Rapports", path="Archive", description="new", type=TagType.DOCUMENT, item_ids=[]),
        _user(),
    )

    assert store.saved is not None
    assert store.saved.name == "Rapports"
    assert store.saved.path == "Archive"
    assert store.saved.description == "new"
    assert store.saved.full_path == "Archive/Rapports"
