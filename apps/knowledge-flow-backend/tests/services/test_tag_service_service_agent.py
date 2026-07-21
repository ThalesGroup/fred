# Copyright Thales 2025
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

"""service_agent recognition in the knowledge-flow tag authorization (RFC EVAL-AUTH).

The evaluation worker (service_agent) must read the TEAM's corpus tags, scoped to
team_id, even though it holds no per-user tag relations.
"""

from datetime import datetime, timezone

import pytest
from fred_core import AuthorizationError, RebacReference, Resource, TagPermission
from fred_core.common import OwnerFilter
from fred_core.security.structure import KeycloakUser

import knowledge_flow_backend.features.tag.tag_service as tag_service_module
from knowledge_flow_backend.features.tag.structure import Tag, TagType

TagService = tag_service_module.TagService


class _FakeRebac:
    """Team owns `team_tags`; the user has no per-user READ relations (like a service)."""

    def __init__(self, team_tags: set[str], user_readable: set[str] | None = None) -> None:
        self._team_tags = team_tags
        self._user_readable = user_readable or set()

    async def lookup_user_resources(self, user, permission):
        return [RebacReference(type=Resource.TAGS, id=t) for t in self._user_readable]

    async def lookup_resources(self, subject_ref, permission, resource_type):
        if permission == TagPermission.OWNER:
            return [RebacReference(type=Resource.TAGS, id=t) for t in self._team_tags]
        return []


def _svc(rebac: _FakeRebac) -> TagService:
    svc = TagService.__new__(TagService)  # bypass ApplicationContext wiring
    svc.rebac = rebac
    return svc


def _user(roles: list[str]) -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=roles, email=None)


def _tag(tag_id: str, owner_id: str) -> Tag:
    now = datetime.now(timezone.utc)
    return Tag(id=tag_id, created_at=now, updated_at=now, owner_id=owner_id, name=tag_id, type=TagType.DOCUMENT)


class _FakeRebacPerTeam:
    """Only the exact team named in `owner_by_team` owns the tags in its set.

    Unlike `_FakeRebac`, this is team-id-aware — needed to prove `get_tag_for_user`
    scopes the service_agent bypass to the *tag's own* owning team, not to any
    team_id the caller happens to assert.
    """

    def __init__(self, owner_by_team: dict[str, set[str]]) -> None:
        self._owner_by_team = owner_by_team

    async def lookup_resources(self, subject_ref, permission, resource_type):
        if permission == TagPermission.OWNER:
            return [RebacReference(type=Resource.TAGS, id=t) for t in self._owner_by_team.get(subject_ref.id, set())]
        return []

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        raise AssertionError("service_agent path must not call the per-user permission check")


class _FakeTagStore:
    def __init__(self, tags: dict[str, Tag]) -> None:
        self._tags = tags

    async def get_tag_by_id(self, tag_id: str) -> Tag:
        return self._tags[tag_id]


def _svc_for_get_tag(rebac, tags: dict[str, Tag]) -> TagService:
    svc = TagService.__new__(TagService)
    svc.rebac = rebac
    svc._tag_store = _FakeTagStore(tags)
    return svc


@pytest.mark.asyncio
async def test_service_agent_gets_team_tags_despite_empty_user_baseline():
    # user_readable empty (service identity) but the team owns CIR → worker sees CIR.
    svc = _svc(_FakeRebac(team_tags={"tag-cir"}, user_readable=set()))
    result = await svc.resolve_authorized_tag_ids_in_rebac(_user(["service_agent"]), OwnerFilter.TEAM, "team-1")
    assert result == {"tag-cir"}


@pytest.mark.asyncio
async def test_service_agent_without_team_fails_closed():
    svc = _svc(_FakeRebac(team_tags={"tag-cir"}))
    result = await svc.resolve_authorized_tag_ids_in_rebac(_user(["service_agent"]), OwnerFilter.TEAM, None)
    assert result == set()


@pytest.mark.asyncio
async def test_normal_user_still_intersects_readable_and_team():
    # Regular user: result stays the intersection of user-readable and team-owned.
    svc = _svc(_FakeRebac(team_tags={"tag-cir"}, user_readable={"tag-a", "tag-cir"}))
    result = await svc.resolve_authorized_tag_ids_in_rebac(_user(["viewer"]), OwnerFilter.TEAM, "team-1")
    assert result == {"tag-cir"}


# ---------------------------------------------------------------------------
# get_tag_for_user — single-tag lookup (corpus filesystem's `_get_tag_for_user`
# and vector-search's explicit-tag resolution both funnel through this). This
# was the single-resource checkpoint missing the service_agent bypass: it used
# `check_user_permission_or_raise` directly, which always denies a service_agent
# (zero per-user ReBAC relations by design), and raised `AuthorizationError`
# rather than `PermissionError`, so the denial surfaced as an unhandled 500
# instead of a 403 at the controller boundary.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_agent_get_tag_for_user_allowed_when_owning_team_grants_it(monkeypatch):
    tag = _tag("tag-warfare", owner_id="team-fredlab")
    svc = _svc_for_get_tag(_FakeRebacPerTeam({"team-fredlab": {"tag-warfare"}}), {"tag-warfare": tag})

    def _fake_item_service(_tag_type):
        class _Items:
            async def retrieve_items_ids_for_tag(self, user, tag_id):
                return ["doc-1"]

        return _Items()

    monkeypatch.setattr(tag_service_module, "get_specific_tag_item_service", _fake_item_service)

    result = await svc.get_tag_for_user("tag-warfare", _user(["service_agent"]))
    assert result.id == "tag-warfare"
    assert result.item_ids == ["doc-1"]


@pytest.mark.asyncio
async def test_service_agent_get_tag_for_user_denied_for_a_different_teams_tag():
    # The tag is owned by team-other; the service_agent's own scope (however it
    # was derived upstream) never grants team-other's tags. `get_tag_for_user`
    # must scope to the *tag's own* owner_id, not trust an implicit caller scope.
    tag = _tag("tag-secret", owner_id="team-other")
    svc = _svc_for_get_tag(_FakeRebacPerTeam({"team-fredlab": {"tag-warfare"}}), {"tag-secret": tag})

    with pytest.raises(AuthorizationError):
        await svc.get_tag_for_user("tag-secret", _user(["service_agent"]))


@pytest.mark.asyncio
async def test_service_agent_get_tag_for_user_denied_for_personal_tag():
    # Personal tags store the user's own uid as owner_id, not a real ReBAC team —
    # lookup_resources(TEAM:<uid>, ...) matches nothing, so this fails closed.
    tag = _tag("tag-personal", owner_id="user-123")
    svc = _svc_for_get_tag(_FakeRebacPerTeam({}), {"tag-personal": tag})

    with pytest.raises(AuthorizationError):
        await svc.get_tag_for_user("tag-personal", _user(["service_agent"]))


@pytest.mark.asyncio
async def test_normal_user_get_tag_for_user_still_uses_direct_permission_check(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _RecordingRebac:
        async def check_user_permission_or_raise(self, user, permission, resource_id):
            calls.append((permission.value, resource_id))

    def _fake_item_service(_tag_type):
        class _Items:
            async def retrieve_items_ids_for_tag(self, user, tag_id):
                return []

        return _Items()

    monkeypatch.setattr(tag_service_module, "get_specific_tag_item_service", _fake_item_service)

    tag = _tag("tag-a", owner_id="team-1")
    svc = _svc_for_get_tag(_RecordingRebac(), {"tag-a": tag})

    result = await svc.get_tag_for_user("tag-a", _user(["viewer"]))
    assert calls == [(TagPermission.READ.value, "tag-a")]
    assert result.id == "tag-a"
