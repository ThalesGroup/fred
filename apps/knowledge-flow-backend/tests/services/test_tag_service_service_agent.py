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

import pytest
from fred_core import RebacReference, Resource, TagPermission
from fred_core.common import OwnerFilter
from fred_core.security.structure import KeycloakUser

from knowledge_flow_backend.features.tag.tag_service import TagService


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
