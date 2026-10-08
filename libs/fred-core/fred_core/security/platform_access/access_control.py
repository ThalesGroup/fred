# SPDX-License-Identifier: Apache-2.0
import asyncio
import math
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
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

from fred_core.security.platform_access.models import PlatformAccessSettingsRow
from fred_core.security.platform_access.rules import allows, evaluate, path_key
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.rebac_engine import RebacEngine
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
            from fred_core.security.whitelist_access_control.access_control import (
                is_whitelist_active,
            )

            if state.filtering_enabled and is_whitelist_active():
                raise ValueError("Conflicting legacy admission gate")
            if state.filtering_enabled and state.policy is None:
                raise ValueError("Active filtering requires a policy")
        except ValueError:
            raise HTTPException(503, "platform_access_unavailable") from None
        return state

    async def observe(self, user: KeycloakUser) -> UserRow:
        state = await self.state()
        return await self.store.observe(user, self.policy(state))

    async def team_sources(
        self, uid: str, session: AsyncSession | None = None
    ) -> list[TeamMetadataRow]:
        teams = await self.store.teams(session, eligible_only=True)
        memberships = await self.rebac.has_team_memberships(
            uid, [team.id for team in teams]
        )
        if len(memberships) != len(teams) or any(
            type(value) is not bool for value in memberships
        ):
            raise RuntimeError("Incomplete membership authority response")
        return [team for team, member in zip(teams, memberships) if member]

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
            team.id != excluding_team
            for team in await self.team_sources(user.uid, session)
        )

    async def admitted(self, user: Principal) -> bool:
        try:
            state = await self.state()
            if isinstance(user, KeycloakUser):
                    if not state.filtering_enabled:
                if isinstance(user, KeycloakUser):
                    await self.store.observe(user, self.policy(state))
                return True
            return await self.eligible(
                user, policy=self.policy(state), use_current_policy=False
            )
        except HTTPException:
            raise
        except Exception:
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
            "users",
            "teammetadata",
            *(["platform_access_links"] if authority else []),
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
