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

"""PLATFORM-ADMIN-DELEGATION-RFC.md (#2405): root-managed admins, delegated
observers.

The load-bearing guarantees these tests lock in:
- `platform_admin` is granted and revoked by the bootstrap root only — the
  uid in `platformbootstrap.completed_by`, never a live tuple count;
- the root itself is unrevocable, for every caller including itself;
- `platform_observer` carries none of those restrictions;
- with no bootstrap marker there is no root, so `platform_admin` management
  refuses (409-mapped) instead of falling open.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from control_plane_backend.users.platform_roles import (
    grant_platform_role,
    list_platform_roles,
    revoke_platform_role,
)
from control_plane_backend.users.schemas import (
    PlatformAdminRootOnlyError,
    PlatformBootstrapNotCompletedError,
    PlatformRoleNotHeldError,
    PlatformRoleRelation,
    PlatformRoleRootProtectedError,
    PlatformRolesRebacDisabledError,
)
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)

ROOT_UID = "root-sub"
ADMIN_UID = "admin-sub"
OTHER_UID = "other-sub"

_ORG_REF = RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)


class _FakeRebac:
    def __init__(
        self,
        *,
        enabled: bool = True,
        admins: set[str] | None = None,
        observers: set[str] | None = None,
        disabled_reads: bool = False,
    ) -> None:
        self.enabled = enabled
        self._admins = admins if admins is not None else set()
        self._observers = observers if observers is not None else set()
        self._disabled_reads = disabled_reads
        self.added: list[tuple[Relation, str | None]] = []
        self.deleted: list[Relation] = []
        self.permission_checks: list[tuple[str, object]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        self.permission_checks.append((user.uid, permission))

    async def lookup_subjects(self, resource, relation, subject_type, **kwargs):
        if self._disabled_reads:
            return RebacDisabledResult()
        assert resource == _ORG_REF
        holders = (
            self._admins if relation == RelationType.PLATFORM_ADMIN else self._observers
        )
        return [RebacReference(Resource.USER, uid) for uid in sorted(holders)]

    async def add_relation(self, relation: Relation, *, actor_uid=None):
        self.added.append((relation, actor_uid))
        return None

    async def delete_relation(self, relation: Relation):
        self.deleted.append(relation)
        return None


class _FakeBootstrapStore:
    def __init__(self, completed_by: str | None = ROOT_UID) -> None:
        self._completed_by = completed_by

    async def get_completed_by(self) -> str | None:
        return self._completed_by


class _FakeUserDeps:
    """`list_platform_roles` resolves display identity through
    `get_users_by_ids`, which degrades to `{}` when Keycloak M2M is disabled
    — the exact behaviour this fake reproduces."""

    def create_keycloak_admin_client(self):
        from fred_core import KeycloackDisabled

        return KeycloackDisabled()


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=f"{uid}@example.com")


def _args(rebac: _FakeRebac, store: _FakeBootstrapStore):
    return cast(Any, rebac), cast(Any, store)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_flags_the_bootstrap_root_and_the_calling_root():
    rebac = _FakeRebac(admins={ROOT_UID, ADMIN_UID}, observers={OTHER_UID})
    response = await list_platform_roles(
        _user(ROOT_UID),
        *_args(rebac, _FakeBootstrapStore()),
        cast(Any, _FakeUserDeps()),
    )

    assert response.caller_is_bootstrap_root is True
    by_uid = {h.user.id: h for h in response.holders}
    assert set(by_uid) == {ROOT_UID, ADMIN_UID, OTHER_UID}
    assert by_uid[ROOT_UID].is_bootstrap_root is True
    assert by_uid[ADMIN_UID].is_bootstrap_root is False
    assert by_uid[ADMIN_UID].relations == [PlatformRoleRelation.PLATFORM_ADMIN]
    assert by_uid[OTHER_UID].relations == [PlatformRoleRelation.PLATFORM_OBSERVER]


@pytest.mark.asyncio
async def test_list_caller_flag_false_for_appointed_admin():
    rebac = _FakeRebac(admins={ROOT_UID, ADMIN_UID})
    response = await list_platform_roles(
        _user(ADMIN_UID),
        *_args(rebac, _FakeBootstrapStore()),
        cast(Any, _FakeUserDeps()),
    )
    assert response.caller_is_bootstrap_root is False


@pytest.mark.asyncio
async def test_list_refuses_when_rebac_disabled():
    rebac = _FakeRebac(disabled_reads=True)
    with pytest.raises(PlatformRolesRebacDisabledError):
        await list_platform_roles(
            _user(ROOT_UID),
            *_args(rebac, _FakeBootstrapStore()),
            cast(Any, _FakeUserDeps()),
        )


# ---------------------------------------------------------------------------
# grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_any_admin_grants_platform_observer():
    rebac = _FakeRebac()
    await grant_platform_role(
        _user(ADMIN_UID),
        OTHER_UID,
        PlatformRoleRelation.PLATFORM_OBSERVER,
        *_args(rebac, _FakeBootstrapStore()),
    )

    assert len(rebac.added) == 1
    relation, actor_uid = rebac.added[0]
    assert relation.subject == RebacReference(Resource.USER, OTHER_UID)
    assert relation.relation == RelationType.PLATFORM_OBSERVER
    assert relation.resource == _ORG_REF
    assert actor_uid == ADMIN_UID


@pytest.mark.asyncio
async def test_root_grants_platform_admin():
    rebac = _FakeRebac()
    await grant_platform_role(
        _user(ROOT_UID),
        OTHER_UID,
        PlatformRoleRelation.PLATFORM_ADMIN,
        *_args(rebac, _FakeBootstrapStore()),
    )

    assert len(rebac.added) == 1
    relation, actor_uid = rebac.added[0]
    assert relation.relation == RelationType.PLATFORM_ADMIN
    assert actor_uid == ROOT_UID


@pytest.mark.asyncio
async def test_appointed_admin_cannot_grant_platform_admin():
    """RFC §3: appointed admins cannot grow the admin population."""
    rebac = _FakeRebac()
    with pytest.raises(PlatformAdminRootOnlyError):
        await grant_platform_role(
            _user(ADMIN_UID),
            OTHER_UID,
            PlatformRoleRelation.PLATFORM_ADMIN,
            *_args(rebac, _FakeBootstrapStore()),
        )
    assert rebac.added == []


@pytest.mark.asyncio
async def test_grant_platform_admin_refuses_when_bootstrap_never_ran():
    """RFC §3: with no marker there is no root — refuse rather than fall open,
    and point the operator at the still-open bootstrap endpoint."""
    rebac = _FakeRebac()
    with pytest.raises(PlatformBootstrapNotCompletedError):
        await grant_platform_role(
            _user(ADMIN_UID),
            OTHER_UID,
            PlatformRoleRelation.PLATFORM_ADMIN,
            *_args(rebac, _FakeBootstrapStore(completed_by=None)),
        )
    assert rebac.added == []


@pytest.mark.asyncio
async def test_grant_refuses_when_rebac_disabled():
    """With ReBAC disabled `add_relation` is a silent no-op — refuse instead
    of returning 204 while granting nothing."""
    rebac = _FakeRebac(enabled=False)
    with pytest.raises(PlatformRolesRebacDisabledError):
        await grant_platform_role(
            _user(ADMIN_UID),
            OTHER_UID,
            PlatformRoleRelation.PLATFORM_OBSERVER,
            *_args(rebac, _FakeBootstrapStore()),
        )
    assert rebac.added == []


# ---------------------------------------------------------------------------
# revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_revokes_an_appointed_admin():
    rebac = _FakeRebac(admins={ROOT_UID, ADMIN_UID})
    await revoke_platform_role(
        _user(ROOT_UID),
        ADMIN_UID,
        PlatformRoleRelation.PLATFORM_ADMIN,
        *_args(rebac, _FakeBootstrapStore()),
    )

    assert len(rebac.deleted) == 1
    assert rebac.deleted[0].subject == RebacReference(Resource.USER, ADMIN_UID)
    assert rebac.deleted[0].relation == RelationType.PLATFORM_ADMIN


@pytest.mark.asyncio
async def test_appointed_admins_cannot_revoke_each_other():
    """RFC §3: revoking `platform_admin` is reserved to the bootstrap root —
    an appointed admin revoking another must 403, not depend on tuple state."""
    rebac = _FakeRebac(admins={ROOT_UID, ADMIN_UID, OTHER_UID})
    with pytest.raises(PlatformAdminRootOnlyError):
        await revoke_platform_role(
            _user(ADMIN_UID),
            OTHER_UID,
            PlatformRoleRelation.PLATFORM_ADMIN,
            *_args(rebac, _FakeBootstrapStore()),
        )
    assert rebac.deleted == []


@pytest.mark.asyncio
async def test_appointed_admin_cannot_drop_their_own_admin_role():
    """RFC §3: no self-service exit either — stepping down goes through the
    root."""
    rebac = _FakeRebac(admins={ROOT_UID, ADMIN_UID})
    with pytest.raises(PlatformAdminRootOnlyError):
        await revoke_platform_role(
            _user(ADMIN_UID),
            ADMIN_UID,
            PlatformRoleRelation.PLATFORM_ADMIN,
            *_args(rebac, _FakeBootstrapStore()),
        )
    assert rebac.deleted == []


@pytest.mark.asyncio
async def test_root_cannot_revoke_itself():
    """The load-bearing rule: root self-demotion is irreversible because
    bootstrap never reopens — refused outright."""
    rebac = _FakeRebac(admins={ROOT_UID})
    with pytest.raises(PlatformRoleRootProtectedError):
        await revoke_platform_role(
            _user(ROOT_UID),
            ROOT_UID,
            PlatformRoleRelation.PLATFORM_ADMIN,
            *_args(rebac, _FakeBootstrapStore()),
        )
    assert rebac.deleted == []


@pytest.mark.asyncio
async def test_revoke_platform_admin_refuses_when_bootstrap_never_ran():
    rebac = _FakeRebac(admins={ADMIN_UID})
    with pytest.raises(PlatformBootstrapNotCompletedError):
        await revoke_platform_role(
            _user(ADMIN_UID),
            ADMIN_UID,
            PlatformRoleRelation.PLATFORM_ADMIN,
            *_args(rebac, _FakeBootstrapStore(completed_by=None)),
        )
    assert rebac.deleted == []


@pytest.mark.asyncio
async def test_any_admin_revokes_platform_observer():
    """Observer tuples carry no root protection — even the root's own
    observer role is revocable by any admin (RFC §3: the restriction set is
    scoped to the `platform_admin` relation, nothing else)."""
    rebac = _FakeRebac(observers={ROOT_UID})
    await revoke_platform_role(
        _user(ADMIN_UID),
        ROOT_UID,
        PlatformRoleRelation.PLATFORM_OBSERVER,
        *_args(rebac, _FakeBootstrapStore()),
    )
    assert len(rebac.deleted) == 1
    assert rebac.deleted[0].relation == RelationType.PLATFORM_OBSERVER


@pytest.mark.asyncio
async def test_revoke_unheld_role_is_a_404_shaped_error():
    rebac = _FakeRebac(observers=set())
    with pytest.raises(PlatformRoleNotHeldError):
        await revoke_platform_role(
            _user(ADMIN_UID),
            OTHER_UID,
            PlatformRoleRelation.PLATFORM_OBSERVER,
            *_args(rebac, _FakeBootstrapStore()),
        )
    assert rebac.deleted == []
