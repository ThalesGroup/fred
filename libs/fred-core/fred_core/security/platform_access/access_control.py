# SPDX-License-Identifier: Apache-2.0
import asyncio
import math
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, NamedTuple
from uuid import UUID

from fastapi import HTTPException
from fred_pod.security.platform_access import PlatformAccessPolicy
from fred_pod.security.structure import (
    KeycloakUser,
    Principal,
    SecurityConfiguration,
    is_service_agent,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.security.models import Resource
from fred_core.security.platform_access.models import PlatformAccessSettingsRow
from fred_core.security.platform_access.rules import allows, evaluate, path_key
from fred_core.security.platform_access.store import (
    PlatformAccessStore,
    warn_unavailable,
)
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
    RebacEngine,
    RebacReference,
)
from fred_core.sql.schema_guard import require_tables
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow


def token_time(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        else None
    )


class TeamSource(NamedTuple):
    team: TeamMetadataRow
    allowed: bool  # authorized team: every member is admitted
    free: bool  # Free team the person joined through one of its Free links


class PlatformAccess:
    def __init__(
        self,
        store: PlatformAccessStore,
        rebac: RebacEngine,
    ):
        self.store, self.rebac = store, rebac

    def observed_match(
        self, row: UserRow | None, policy: PlatformAccessPolicy | None
    ) -> bool:
        return bool(
            row is not None
            and not row.admission_conflicted
            and row.admission_expires_at is not None
            and row.admission_expires_at > time.time()
            and policy is not None
            and all(
                path_key(condition.claim) in (row.admission_attribute or {})
                for condition in policy.conditions
            )
            and allows(policy, evaluate(policy, row.admission_attribute or {}))
        )

    @staticmethod
    def policy(state: PlatformAccessSettingsRow) -> PlatformAccessPolicy | None:
        return (
            PlatformAccessPolicy.model_validate(state.policy)
            if state.policy is not None
            else None
        )

    async def state(
        self, session: AsyncSession | None = None
    ) -> PlatformAccessSettingsRow:
        state = await self.store.settings(session)
        if state is None:
            raise HTTPException(503, "platform_access_unavailable")
        try:
            self.policy(state)
        except ValueError:
            raise HTTPException(503, "platform_access_unavailable") from None
        return state

    async def observe(self, user: KeycloakUser) -> UserRow:
        state = await self.state()
        return await self.store.observe(user, self.policy(state))

    async def team_sources(
        self, uid: str, session: AsyncSession | None = None
    ) -> list[TeamSource]:
        """Current team-derived admission: membership plus a current team flag.

        Free counts only for people who joined through that team's Free link, so
        team admins adding members (by hand or team link) never grant admission.
        """
        joined = (await self.store.free_joined_teams(UUID(uid), session)).get(
            UUID(uid), set()
        )
        candidates = [
            TeamSource(
                team,
                team.platform_access_allowed,
                team.platform_access_free and team.id in joined,
            )
            for team in await self.store.teams(session, eligible_only=True)
        ]
        candidates = [source for source in candidates if source.allowed or source.free]
        memberships = await self.rebac.has_team_memberships(
            uid, [source.team.id for source in candidates]
        )
        if len(memberships) != len(candidates) or any(
            type(value) is not bool for value in memberships
        ):
            raise RuntimeError("Incomplete membership authority response")
        return [source for source, member in zip(candidates, memberships) if member]

    async def access_manager_uid(self, uid: str) -> bool:
        """Resolve the current Platform Access permission for a person's UID."""
        try:
            return await self.rebac.has_permission(
                RebacReference(Resource.USER, uid),
                OrganizationPermission.CAN_MANAGE_PLATFORM_ACCESS,
                RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
                consistency_token=self.rebac.HIGHER_CONSISTENCY,
            )
        except Exception as error:
            warn_unavailable("admin check", error)
            raise HTTPException(503, "platform_access_unavailable") from None

    async def access_manager(self, user: Principal) -> bool:
        """Ignore a workload's own identity when checking human admission."""
        if isinstance(user, KeycloakUser) and (
            user.service_account or is_service_agent(user)
        ):
            return False
        return await self.access_manager_uid(user.uid)

    async def eligible(
        self,
        user: Principal,
        session: AsyncSession | None = None,
        *,
        policy: PlatformAccessPolicy | None = None,
        use_current_policy: bool = True,
        excluding_team: str | None = None,
    ) -> bool:
        if use_current_policy:
            policy = self.policy(await self.state(session))
        if await self.access_manager(user):
            return True
        uid = UUID(user.uid)
        if isinstance(user, KeycloakUser):
            row = (
                await self.store.user(uid, session)
                if session is not None
                else await self.store.observe(user, policy)
            )
            result = await asyncio.to_thread(
                evaluate, policy, user.admission_claims, user.admission_invalid_claims
            )
            if allows(policy, result) and (
                row is None
                or row.admission_issued_at != user.admission_issued_at
                or not row.admission_conflicted
            ):
                return True
        elif await asyncio.to_thread(
            self.observed_match, await self.store.user(uid, session), policy
        ):
            return True
        if await self.store.exception(uid, session) is not None:
            return True
        return any(
            source.team.id != excluding_team
            for source in await self.team_sources(user.uid, session)
        )

    async def admitted(self, user: Principal) -> bool:
        try:
            state = await self.state()
            if not state.filtering_enabled:
                if isinstance(user, KeycloakUser):
                    await self.store.observe(user, self.policy(state))
                return True
            return await self.eligible(
                user, policy=self.policy(state), use_current_policy=False
            )
        except HTTPException:
            raise
        except Exception as error:
            warn_unavailable("admission", error)
            raise HTTPException(503, "platform_access_unavailable") from None


_available = False
_installed: PlatformAccess | None = None


def platform_access_available(security: SecurityConfiguration | None = None) -> bool:
    if security is None:
        return _available
    return bool(
        security.user.enabled
        and security.m2m.enabled
        and security.rebac is not None
        and security.rebac.enabled
    )


def configure_platform_access(security: SecurityConfiguration) -> None:
    global _available, _installed
    _available, _installed = platform_access_available(security), None
    if not _available:
        return
    assert security.rebac is not None
    if (
        security.rebac.timeout_millisec is None
        or not 1 <= security.rebac.timeout_millisec <= 30000
    ):
        raise ValueError(
            "Platform access requires OpenFGA timeout_millisec between 1 and 30000"
        )


async def initialize_platform_access(
    security: SecurityConfiguration,
    engine: AsyncEngine,
    rebac: RebacEngine,
    *,
    authority: bool = False,
) -> None:
    global _installed
    if not platform_access_available(security):
        return
    if not rebac.enabled or not rebac.requires_active_accounts:
        raise ValueError("Platform access requires an enforced account-status engine")
    if engine.dialect.name != "postgresql":
        raise ValueError("Platform access requires the shared PostgreSQL database")
    await require_tables(
        engine,
        [
            "platform_access_settings",
            "platform_access_users",
            "platform_access_removals",
            "users",
            "teammetadata",
            # Free admission is derived from Free-link joins on every backend.
            "platform_access_links",
            "platform_access_link_joiners",
        ],
        component="platform-access",
        migrate_command="make db-upgrade (apps/control-plane-backend)",
        version_table="alembic_version_control_plane",
    )
    access = PlatformAccess(PlatformAccessStore(engine), rebac)
    if authority:
        async with access.store.mutation() as session:
            state = await access.store.settings(session)
            if state is None:
                session.add(
                    PlatformAccessSettingsRow(
                        id=1,
                        policy=None,
                        revision=0,
                        filtering_enabled=False,
                    )
                )
    await access.state()
    await access.store.teams(eligible_only=True)
    await access.store.users(0, 1)
    # Free admission reads the joiner table on every filtered request: fail at
    # startup, not per request, when this role cannot read it.
    await access.store.free_joined_teams(UUID(int=0))
    _installed = access


def get_platform_access() -> PlatformAccess:
    if not _available:
        raise HTTPException(404, "platform_access_disabled")
    if _installed is None:
        raise HTTPException(503, "platform_access_unavailable")
    return _installed


async def enforce_platform_access(subject: Principal) -> None:
    if (
        not _available
        or isinstance(subject, KeycloakUser)
        and (is_service_agent(subject) or subject.service_account)
    ):
        return
    if not await get_platform_access().admitted(subject):
        raise HTTPException(403, "platform_access_denied")


async def forget_free_joins(team_id: str, user_id: str) -> None:
    """Call around removing a person from a team, so a later re-add by hand
    or team link cannot revive the Free admission source. Teams without Free
    links skip the policy lock, so their removals never depend on it."""
    if not _available or _installed is None:
        return
    try:
        uid = UUID(user_id)
    except ValueError:
        return  # not a person account: it can hold no Free join
    store = _installed.store
    if not await store.has_free_links(team_id):
        return
    async with store.mutation() as session:
        await store.forget_free_joins(team_id, uid, session)


@asynccontextmanager
async def platform_access_team_mutation(
    actor: Principal, removing_team: str
) -> AsyncIterator[None]:
    if not _available:
        yield
        return
    access = get_platform_access()
    async with access.store.mutation() as session:
        state = await access.state(session)
        workload = isinstance(actor, KeycloakUser) and (
            actor.service_account or is_service_agent(actor)
        )
        if (
            state.filtering_enabled
            and not workload
            and not await access.eligible(actor, session, excluding_team=removing_team)
        ):
            raise HTTPException(409, "platform_access_actor_lockout")
        yield
