# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""One request's SQL ownership boundary and local space permission decision."""

from dataclasses import dataclass
from uuid import UUID

from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacReference,
    SpacePermission,
)
from fred_core.security.structure import KeycloakUser
from fred_core.teams.space_models import SpaceContext
from fred_core.teams.space_store import SpaceStore


@dataclass(frozen=True)
class SpaceAccess:
    context: SpaceContext
    permission: SpacePermission
    space_ids: tuple[str, ...]


async def authorize_space(
    user: KeycloakUser,
    space_id: str | None,
    permission: SpacePermission,
    *,
    spaces: SpaceStore,
    rebac: RebacEngine,
) -> SpaceAccess:
    """Resolve SQL identity and authorize once; results belong to this request only."""
    try:
        user_id = UUID(user.uid)
    except ValueError:
        raise AuthorizationError(user.uid, "enter_space", Resource.USER) from None
    context = await spaces.resolve_for_user(user_id, space_id)
    if context is None:
        raise AuthorizationError(user.uid, "enter_space", Resource.USER)

    # Only common corpus/agent use reaches ancestors. Writes and analysis stay local.
    targets = context.ancestry
    if permission not in (SpacePermission.READ_CORPUS, SpacePermission.USE_AGENTS):
        targets = targets[:1]
    checks = [
        (permission, RebacReference(Resource(kind), identifier))
        for kind, identifier in targets
    ]
    allowed = await rebac.has_permissions(
        RebacReference(Resource.USER, user.uid),
        checks,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )
    authorized_ids = tuple(
        reference.id
        for (_, reference), granted in zip(checks, allowed, strict=True)
        if granted
    )
    if context.id not in authorized_ids:
        raise AuthorizationError(user.uid, permission.value, Resource(context.kind))
    return SpaceAccess(context, permission, authorized_ids)
