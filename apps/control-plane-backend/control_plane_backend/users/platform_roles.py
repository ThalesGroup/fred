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

"""Platform-role management (PLATFORM-ADMIN-DELEGATION-RFC.md, #2405).

Model: root-managed admins, delegated observers. Any `platform_admin` may
grant/revoke `platform_observer`; granting and revoking `platform_admin` is
reserved to the bootstrap root — the uid in `platformbootstrap.completed_by`,
the same durable anchor `POST /reset-rebac` already preserves. The root
itself is unrevocable, for every caller including itself.
"""

from __future__ import annotations

import asyncio
import logging

from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    Resource,
)

from control_plane_backend.bootstrap.store import PlatformBootstrapStore
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import (
    PlatformAdminRootOnlyError,
    PlatformBootstrapNotCompletedError,
    PlatformRoleHolder,
    PlatformRoleNotHeldError,
    PlatformRoleRelation,
    PlatformRoleRootProtectedError,
    PlatformRolesRebacDisabledError,
    PlatformRolesResponse,
    UserSummary,
)
from control_plane_backend.users.service import get_users_by_ids

logger = logging.getLogger(__name__)

_ORGANIZATION_REF = RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)


async def _holders_of(rebac: RebacEngine, relation: PlatformRoleRelation) -> set[str]:
    """Uids holding one direct org-level relation, or raise if ReBAC is off."""
    subjects = await rebac.lookup_subjects(
        _ORGANIZATION_REF, relation.to_relation(), Resource.USER
    )
    if isinstance(subjects, RebacDisabledResult):
        raise PlatformRolesRebacDisabledError()
    return {subject.id for subject in subjects}


async def _check_root_guards(
    user: KeycloakUser,
    bootstrap_store: PlatformBootstrapStore,
    *,
    revoke_target: str | None,
) -> None:
    """RFC §3 protection rules for the `platform_admin` relation.

    Why this function exists:
    - both the grant and revoke paths must apply the exact same rule set, in
      the same order: no root yet → 409; caller is not the root → 403; on
      revoke, target is the root → 403 (for every caller, root included —
      self-demotion is irreversible because bootstrap never reopens).
    """
    completed_by = await bootstrap_store.get_completed_by()
    if completed_by is None:
        raise PlatformBootstrapNotCompletedError()
    if user.uid != completed_by:
        raise PlatformAdminRootOnlyError()
    if revoke_target is not None and revoke_target == completed_by:
        raise PlatformRoleRootProtectedError()


async def list_platform_roles(
    user: KeycloakUser,
    rebac: RebacEngine,
    bootstrap_store: PlatformBootstrapStore,
    user_deps: UserServiceDependencies,
) -> PlatformRolesResponse:
    """List every platform-role holder for the admin UI (RFC §3.1).

    How to use it:
    - call from `GET /users/platform-roles`; requires `can_administer_users`
    - holders come from direct OpenFGA tuples; display identity is resolved
      via the cached Keycloak summaries with an id-only fallback, so a
      deleted Keycloak account never hides a still-granted tuple
    """
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_USERS, ORGANIZATION_ID
    )

    admins, observers, completed_by = await asyncio.gather(
        _holders_of(rebac, PlatformRoleRelation.PLATFORM_ADMIN),
        _holders_of(rebac, PlatformRoleRelation.PLATFORM_OBSERVER),
        bootstrap_store.get_completed_by(),
    )

    relations_by_uid: dict[str, list[PlatformRoleRelation]] = {}
    for uid in admins:
        relations_by_uid.setdefault(uid, []).append(PlatformRoleRelation.PLATFORM_ADMIN)
    for uid in observers:
        relations_by_uid.setdefault(uid, []).append(
            PlatformRoleRelation.PLATFORM_OBSERVER
        )

    summaries = await get_users_by_ids(relations_by_uid.keys(), user_deps)
    holders = [
        PlatformRoleHolder(
            user=summaries.get(uid) or UserSummary(id=uid),
            relations=relations,
            is_bootstrap_root=uid == completed_by,
        )
        for uid, relations in relations_by_uid.items()
    ]
    holders.sort(key=lambda h: (h.user.username or "", h.user.id))

    return PlatformRolesResponse(
        holders=holders,
        caller_is_bootstrap_root=completed_by is not None and user.uid == completed_by,
    )


async def grant_platform_role(
    user: KeycloakUser,
    target_user_id: str,
    relation: PlatformRoleRelation,
    rebac: RebacEngine,
    bootstrap_store: PlatformBootstrapStore,
) -> None:
    """Grant one platform role to a user (RFC §3).

    How to use it:
    - call from `POST /users/{user_id}/platform-roles`
    - `platform_observer`: any `platform_admin` may grant
    - `platform_admin`: bootstrap root only (`PlatformAdminRootOnlyError`),
      409 if bootstrap never ran
    - idempotent: re-granting a held role is a no-op (`add_relation` ignores
      duplicates), matching the bootstrap endpoint's own retry semantics
    """
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_USERS, ORGANIZATION_ID
    )
    if not rebac.enabled:
        raise PlatformRolesRebacDisabledError()
    if relation is PlatformRoleRelation.PLATFORM_ADMIN:
        await _check_root_guards(user, bootstrap_store, revoke_target=None)

    await rebac.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, target_user_id),
            relation=relation.to_relation(),
            resource=_ORGANIZATION_REF,
        ),
        actor_uid=user.uid,
    )
    logger.info(
        "[PLATFORM-ROLES] %s granted %s to %s",
        user.uid,
        relation.value,
        target_user_id,
    )


async def revoke_platform_role(
    user: KeycloakUser,
    target_user_id: str,
    relation: PlatformRoleRelation,
    rebac: RebacEngine,
    bootstrap_store: PlatformBootstrapStore,
) -> None:
    """Revoke one platform role from a user (RFC §3).

    How to use it:
    - call from `DELETE /users/{user_id}/platform-roles/{relation}`
    - `platform_observer`: any `platform_admin` may revoke
    - `platform_admin`: bootstrap root only, and never targeting the root
      itself (`PlatformRoleRootProtectedError`), 409 if bootstrap never ran
    - revoking a role the target does not hold is a 404
      (`PlatformRoleNotHeldError`), mirroring the team-role revoke surface
    """
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_USERS, ORGANIZATION_ID
    )
    if relation is PlatformRoleRelation.PLATFORM_ADMIN:
        await _check_root_guards(user, bootstrap_store, revoke_target=target_user_id)

    holders = await _holders_of(rebac, relation)
    if target_user_id not in holders:
        raise PlatformRoleNotHeldError(target_user_id, relation.value)

    await rebac.delete_relation(
        Relation(
            subject=RebacReference(Resource.USER, target_user_id),
            relation=relation.to_relation(),
            resource=_ORGANIZATION_REF,
        )
    )
    logger.info(
        "[PLATFORM-ROLES] %s revoked %s from %s",
        user.uid,
        relation.value,
        target_user_id,
    )
