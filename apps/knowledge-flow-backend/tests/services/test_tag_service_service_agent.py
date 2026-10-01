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

"""Service roles never replace explicit corpus-root grants."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import AuthorizationError, KeycloakUser, RelationType, Resource, TeamPermission
from fred_core.common import OwnerFilter
from fred_core.security.delegation import DelegationConfig, initialize_delegation, preserved_delegation

from knowledge_flow_backend.features.tag.structure import Tag, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService


def _tag(uid, *, path=None, owner="team-1"):
    now = datetime.now(timezone.utc)
    return Tag(id=uid, name=uid, path=path, owner_id=owner, created_at=now, updated_at=now, type=TagType.DOCUMENT)


def _user(uid="source", *, delegated=False):
    return KeycloakUser(uid=uid, username=uid, roles=["service_agent"], client_id="agents" if delegated else None, caller_roles=frozenset({"delegation_caller"}) if delegated else frozenset())


def _service(tags, grants=()):
    service = TagService.__new__(TagService)
    service.rebac = AsyncMock()
    service.rebac.enabled = True

    async def granted(subject, relation, target):
        return (subject.id, relation, target.id) in grants

    service.rebac.has_direct_relation.side_effect = granted
    service._tag_store = AsyncMock()

    async def listed(owner_id, *, path_prefix=None, limit=None, offset=0):
        selected = [tag for tag in tags if tag.owner_id == owner_id and (not path_prefix or tag.full_path == path_prefix or tag.full_path.startswith(path_prefix + "/"))]
        return selected[offset:] if limit is None else selected[offset : offset + limit]

    async def root(owner_id, tag_type, full_path):
        return next((tag for tag in tags if tag.owner_id == owner_id and tag.full_path == full_path), None)

    service._tag_store.list_by_owner.side_effect = listed
    service._tag_store.get_by_owner_type_full_path.side_effect = root
    service._tag_store.get_tag_by_id.side_effect = lambda uid: next(tag for tag in tags if tag.id == uid)
    service.document_metadata_service = SimpleNamespace(metadata_store=SimpleNamespace(document_uids_by_tags=AsyncMock(return_value={tag.id: ["doc-1"] for tag in tags})))
    return service


@pytest.mark.asyncio
async def test_service_role_alone_neither_lists_nor_reads_team_folder():
    service = _service([_tag("root")])
    assert await service.list_authorized_tags_ids(_user(), OwnerFilter.TEAM, "team-1") == set()
    with pytest.raises(AuthorizationError):
        await service.get_tag_for_user("root", _user())
    service.document_metadata_service.metadata_store.document_uids_by_tags.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("relation", [RelationType.VIEWER, RelationType.EDITOR])
async def test_exact_account_root_grant_allows_only_its_subtree(relation):
    service = _service([_tag("root"), _tag("child", path="root"), _tag("other"), _tag("foreign", owner="team-2")], {("source", relation, "root")})
    assert await service.list_authorized_tags_ids(_user(), OwnerFilter.TEAM, "team-1") == {"root", "child"}
    assert await service.list_authorized_tags_ids(_user("other-account"), OwnerFilter.TEAM, "team-1") == set()
    result = await service.get_tag_for_user("child", _user())
    assert result.item_ids == ["doc-1"]
    with pytest.raises(AuthorizationError):
        await service.get_tag_for_user("other", _user())
    service.rebac.lookup_user_resources.assert_not_called()
    service.rebac.lookup_resources.assert_not_called()


@pytest.mark.asyncio
async def test_service_pagination_applies_after_authorization_and_checks_each_root_once():
    service = _service([_tag("forbidden"), _tag("root"), _tag("child", path="root")], {("source", RelationType.EDITOR, "root")})
    result = await service.list_all_tags_for_user(_user(), team_id="team-1", limit=1, offset=1)
    assert [tag.id for tag in result] == ["child"]
    assert service.rebac.has_direct_relation.await_count == 3  # forbidden editor + viewer; root editor
    service.rebac.require_active_account.assert_awaited_once_with("source")


@pytest.mark.asyncio
async def test_viewer_grant_does_not_authorize_source_writes():
    service = _service([_tag("root")], {("source", RelationType.VIEWER, "root")})
    with pytest.raises(AuthorizationError):
        await service.corpus_access.get_folder(_user(), "root", write=True)


@pytest.mark.asyncio
async def test_personal_folder_requires_explicit_grant_too():
    service = _service([_tag("private", owner="personal-alice")])
    with pytest.raises(AuthorizationError):
        await service.get_tag_for_user("private", _user())


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [DelegationConfig(), DelegationConfig(accept_delegated_calls=True), DelegationConfig(act_for_people=True)])
async def test_delegated_caller_uses_human_team_policy_not_machine_grant(config):
    service = _service([_tag("root")], {("source", RelationType.EDITOR, "root")})
    user = _user(delegated=True)
    service.rebac.check_user_permission_or_raise.side_effect = AuthorizationError(user.uid, "read", Resource.TEAM)
    with preserved_delegation():
        initialize_delegation(config)
        with pytest.raises(AuthorizationError):
            await service.list_authorized_tags_ids(user, OwnerFilter.TEAM, "team-1")
    service.rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "team-1")
    service.rebac.has_direct_relation.assert_not_called()
