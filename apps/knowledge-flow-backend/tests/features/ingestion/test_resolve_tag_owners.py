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

"""`_resolve_tag_owners` is the shared tag->owner resolution used by both quota
enforcement and, since this fix, task `team_id` tagging in
`_stream_upload_process`. Before this fix, uploaded-document ingestion tasks were
always created with `team_id=NULL`, so a team-scoped Activity view (`WHERE
team_id = :team_id`) never matched them — only a platform admin (no team filter)
could see them. These tests pin down the resolution itself, independent of where
it is consumed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser, RebacDisabledResult

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


class _FakeTagStore:
    def __init__(self, tags: dict[str, SimpleNamespace]) -> None:
        self._tags = tags

    async def get_tag_by_id(self, tag_id: str):
        return self._tags.get(tag_id)


class _FakeRebac:
    def __init__(self, subjects_by_tag: dict[str, list[str]] | None = None, disabled: bool = False) -> None:
        self._subjects_by_tag = subjects_by_tag or {}
        self._disabled = disabled

    async def lookup_subjects(self, reference, relation, resource):
        if self._disabled:
            return RebacDisabledResult()
        return [SimpleNamespace(id=sid) for sid in self._subjects_by_tag.get(reference.id, [])]


class _FakeTeamMetadataStore:
    def __init__(self, known_team_ids: set[str]) -> None:
        self._known = known_team_ids

    async def get_by_team_id(self, team_id):
        return SimpleNamespace(team_id=str(team_id)) if str(team_id) in self._known else None


class _FakeAppContext:
    def __init__(self, tag_store: _FakeTagStore, rebac: _FakeRebac) -> None:
        self._tag_store = tag_store
        self._rebac = rebac

    def get_tag_store(self):
        return self._tag_store

    def get_rebac_engine(self):
        return self._rebac

    def get_pg_async_engine(self):
        return object()  # opaque; only the patched TeamMetadataStore(...) consumes it


def _patch_app_context(monkeypatch, tag_store: _FakeTagStore, rebac: _FakeRebac) -> None:
    fake = _FakeAppContext(tag_store, rebac)
    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(lambda cls: fake))


def _patch_team_metadata_store(monkeypatch, known_team_ids: set[str]) -> None:
    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_controller.TeamMetadataStore",
        lambda engine: _FakeTeamMetadataStore(known_team_ids),
    )


def _controller() -> IngestionController:
    return IngestionController.__new__(IngestionController)


def _user(uid: str = "bob") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=None, roles=[])


@pytest.mark.asyncio
async def test_resolves_team_via_rebac(monkeypatch):
    tag_store = _FakeTagStore({"tag-1": SimpleNamespace(id="tag-1", owner_id="team-fredlab")})
    rebac = _FakeRebac(subjects_by_tag={"tag-1": ["team-fredlab"]})
    _patch_app_context(monkeypatch, tag_store, rebac)

    team_ids, user_ids = await _controller()._resolve_tag_owners(["tag-1"], _user())

    assert team_ids == {"team-fredlab"}
    assert user_ids == set()


@pytest.mark.asyncio
async def test_falls_back_to_team_metadata_lookup_when_rebac_disabled(monkeypatch):
    # This is the exact path AUTHZ-05 exercises with `rebac=None` — ReBAC
    # disabled must not silently drop team ownership.
    tag_store = _FakeTagStore({"tag-1": SimpleNamespace(id="tag-1", owner_id="team-fredlab")})
    rebac = _FakeRebac(disabled=True)
    _patch_app_context(monkeypatch, tag_store, rebac)
    _patch_team_metadata_store(monkeypatch, known_team_ids={"team-fredlab"})

    team_ids, user_ids = await _controller()._resolve_tag_owners(["tag-1"], _user())

    assert team_ids == {"team-fredlab"}
    assert user_ids == set()


@pytest.mark.asyncio
async def test_falls_back_to_user_id_when_team_metadata_lookup_also_fails(monkeypatch):
    tag_store = _FakeTagStore({"tag-1": SimpleNamespace(id="tag-1", owner_id="not-a-real-team")})
    rebac = _FakeRebac(disabled=True)
    _patch_app_context(monkeypatch, tag_store, rebac)
    _patch_team_metadata_store(monkeypatch, known_team_ids=set())

    team_ids, user_ids = await _controller()._resolve_tag_owners(["tag-1"], _user("bob"))

    assert team_ids == set()
    assert user_ids == {"not-a-real-team"}


@pytest.mark.asyncio
async def test_personal_space_tag_resolves_to_the_owning_user(monkeypatch):
    tag_store = _FakeTagStore({"tag-1": SimpleNamespace(id="tag-1", owner_id="personal-bob")})
    rebac = _FakeRebac(disabled=True)
    _patch_app_context(monkeypatch, tag_store, rebac)
    _patch_team_metadata_store(monkeypatch, known_team_ids=set())

    team_ids, user_ids = await _controller()._resolve_tag_owners(["tag-1"], _user("bob"))

    assert team_ids == set()
    assert user_ids == {"bob"}


@pytest.mark.asyncio
async def test_tag_with_no_owner_id_falls_back_to_the_caller(monkeypatch):
    tag_store = _FakeTagStore({"tag-1": SimpleNamespace(id="tag-1", owner_id="personal")})
    rebac = _FakeRebac(disabled=True)
    _patch_app_context(monkeypatch, tag_store, rebac)
    _patch_team_metadata_store(monkeypatch, known_team_ids=set())

    team_ids, user_ids = await _controller()._resolve_tag_owners(["tag-1"], _user("bob"))

    assert team_ids == set()
    assert user_ids == {"bob"}


@pytest.mark.asyncio
async def test_unknown_tag_id_is_skipped(monkeypatch):
    tag_store = _FakeTagStore({})
    rebac = _FakeRebac()
    _patch_app_context(monkeypatch, tag_store, rebac)

    team_ids, user_ids = await _controller()._resolve_tag_owners(["missing-tag"], _user())

    assert team_ids == set()
    assert user_ids == set()


@pytest.mark.asyncio
async def test_multiple_tags_can_resolve_to_multiple_teams(monkeypatch):
    tag_store = _FakeTagStore(
        {
            "tag-a": SimpleNamespace(id="tag-a", owner_id="team-1"),
            "tag-b": SimpleNamespace(id="tag-b", owner_id="team-2"),
        }
    )
    rebac = _FakeRebac(subjects_by_tag={"tag-a": ["team-1"], "tag-b": ["team-2"]})
    _patch_app_context(monkeypatch, tag_store, rebac)

    team_ids, user_ids = await _controller()._resolve_tag_owners(["tag-a", "tag-b"], _user())

    assert team_ids == {"team-1", "team-2"}
    assert user_ids == set()
