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

Direct tuples only: schema.fga defines `platform_observer: [user] or
platform_admin`, so any expanded read (`lookup_subjects` — OpenFGA ListUsers)
would report every admin as a computed observer: a phantom chip in the UI
whose revocation passes the held-check and then silently no-ops
(`on_missing_deletes=IGNORE`). Every read here therefore goes through the
direct-tuple primitives (`list_direct_relations` / `has_direct_relation`).
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
    emit_audit_log,
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
    UserNotFoundError,
    UserSummary,
)
from control_plane_backend.users.service import (
    get_users_by_ids,
    user_exists_in_keycloak,
)

logger = logging.getLogger(__name__)

_ORGANIZATION_REF = RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)


def _require_rebac(rebac: RebacEngine) -> None:
    """One guard for all three entrypoints: with ReBAC disabled every write is
    a silent no-op and every direct read a `RebacDisabledResult`, so the whole
    surface refuses up front — uniformly 503, never a root-guard 403/409 for a
    deployment where the feature cannot work at all."""
    if not rebac.enabled:
        raise PlatformRolesRebacDisabledError()


async def _direct_holders(
    rebac: RebacEngine,
) -> dict[PlatformRoleRelation, set[str]]:
    """Uids holding each platform role as a *direct* tuple on the org object.

    One exact Read (`list_direct_relations`) instead of two ListUsers calls —
    see the module docstring for why expanded reads are wrong here.
    """
    tuples = await rebac.list_direct_relations(_ORGANIZATION_REF)
    if isinstance(tuples, RebacDisabledResult):
        raise PlatformRolesRebacDisabledError()

    holders: dict[PlatformRoleRelation, set[str]] = {
        PlatformRoleRelation.PLATFORM_ADMIN: set(),
        PlatformRoleRelation.PLATFORM_OBSERVER: set(),
    }
    for relation in tuples:
        if relation.subject.type is not Resource.USER:
            continue
        try:
            role = PlatformRoleRelation(relation.relation.value)
        except ValueError:
            continue
        holders[role].add(relation.subject.id)
    return holders


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
    _require_rebac(rebac)
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_USERS, ORGANIZATION_ID
    )

    holders_by_role, completed_by = await asyncio.gather(
        _direct_holders(rebac),
        bootstrap_store.get_completed_by(),
    )

    relations_by_uid: dict[str, list[PlatformRoleRelation]] = {}
    for role, uids in holders_by_role.items():
        for uid in uids:
            relations_by_uid.setdefault(uid, []).append(role)

    summaries = await get_users_by_ids(relations_by_uid.keys(), user_deps)
    holders = [
        PlatformRoleHolder(
            user=summaries.get(uid) or UserSummary(id=uid),
            relations=relations,
            is_bootstrap_root=uid == completed_by,
        )
        for uid, relations in relations_by_uid.items()
    ]
    # Root first, then alphabetical: the protected identity is the anchor of
    # the whole model, so the admin UI shows it pinned at the top.
    holders.sort(
        key=lambda h: (not h.is_bootstrap_root, h.user.username or "", h.user.id)
    )

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
    user_deps: UserServiceDependencies,
) -> None:
    """Grant one platform role to a user (RFC §3).

    How to use it:
    - call from `POST /users/{user_id}/platform-roles`
    - `platform_observer`: any `platform_admin` may grant
    - `platform_admin`: bootstrap root only (`PlatformAdminRootOnlyError`),
      409 if bootstrap never ran
    - the target must exist in Keycloak (`UserNotFoundError`, 404) — an
      org-level tuple for a typo'd uid would be a live grant for whoever ever
      authenticates with that sub; skipped only when Keycloak M2M is disabled
      (dev mode), where existence cannot be verified
    - idempotent: re-granting a held role is a no-op (`add_relation` ignores
      duplicates), matching the bootstrap endpoint's own retry semantics
    """
    _require_rebac(rebac)
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_USERS, ORGANIZATION_ID
    )
    if relation is PlatformRoleRelation.PLATFORM_ADMIN:
        await _check_root_guards(user, bootstrap_store, revoke_target=None)

    if await user_exists_in_keycloak(target_user_id, user_deps) is False:
        raise UserNotFoundError(target_user_id)

    await rebac.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, target_user_id),
            relation=relation.to_relation(),
            resource=_ORGANIZATION_REF,
        ),
        actor_uid=user.uid,
    )
    logger.info("%s granted %s to %s", user.uid, relation.value, target_user_id)


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
    - revoking a role the target does not hold as a *direct* tuple is a 404
      (`PlatformRoleNotHeldError`) — a computed-only membership (an admin's
      implied observer role) has no tuple to delete, so it 404s instead of
      returning a success that changed nothing
    """
    _require_rebac(rebac)
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_USERS, ORGANIZATION_ID
    )
    if relation is PlatformRoleRelation.PLATFORM_ADMIN:
        await _check_root_guards(user, bootstrap_store, revoke_target=target_user_id)

    subject = RebacReference(Resource.USER, target_user_id)
    held = await rebac.has_direct_relation(
        subject, relation.to_relation(), _ORGANIZATION_REF
    )
    if not held:
        raise PlatformRoleNotHeldError(target_user_id, relation.value)

    await rebac.delete_relation(
        Relation(
            subject=subject,
            relation=relation.to_relation(),
            resource=_ORGANIZATION_REF,
        )
    )
    # `add_relation` audits at the engine chokepoint ("authz.relation.granted")
    # but `delete_relation` has no audit emission anywhere in fred-core — and
    # this surface is the product's first interactive revocation of
    # `platform_admin`, exactly the write OBSERVABILITY-AND-AUDIT.md §5 says
    # must be reconstructible. Emitted here at the call site until fred-core
    # grows the symmetric revoke chokepoint (candidate follow-up noted in
    # #2405); `_require_rebac` above guarantees the engine is enabled.
    emit_audit_log(
        "authz.relation.revoked",
        actor_uid=user.uid,
        subject=f"{subject.type.value}:{subject.id}",
        relation=relation.value,
        resource=f"{_ORGANIZATION_REF.type.value}:{_ORGANIZATION_REF.id}",
    )
    logger.info("%s revoked %s from %s", user.uid, relation.value, target_user_id)
