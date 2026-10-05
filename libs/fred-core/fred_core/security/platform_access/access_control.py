# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import json
import math
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import regex
from fastapi import HTTPException
from fred_pod.security.structure import (
    KeycloakUser,
    PlatformAccessConfiguration,
    Principal,
    SecurityConfiguration,
    is_service_agent,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.security.platform_access.models import PlatformAccessSettingsRow
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.sql.schema_guard import require_tables
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow


def normalize_attribute(value: object) -> str | list[str] | None:
    if isinstance(value, str):
        return value if 0 < len(value) <= 1024 else None
    if (
        isinstance(value, list)
        and 0 < len(value) <= 32
        and all(isinstance(item, str) and 0 < len(item) <= 1024 for item in value)
    ):
        return value
    return None


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
        config: PlatformAccessConfiguration,
        store: PlatformAccessStore,
        rebac: RebacEngine,
    ):
        self.config, self.store, self.rebac = config, store, rebac
        self.path_fingerprint = hashlib.sha256(
            json.dumps(config.jwt_claim).encode()
        ).hexdigest()
        self.fingerprint = hashlib.sha256(
            json.dumps([config.jwt_claim, config.accepted_regex]).encode()
        ).hexdigest()
        self.matcher = regex.compile(config.accepted_regex or r"(?!)")

    def matches(self, value: object) -> bool:
        normalized = normalize_attribute(value)
        values = [normalized] if isinstance(normalized, str) else normalized or []
        deadline = time.monotonic() + 0.025
        try:
            for item in values:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                if self.matcher.fullmatch(item, timeout=remaining):
                    return True
        except TimeoutError:
            return False
        return False

    def observed_match(self, row: UserRow | None) -> bool:
        return bool(
            row is not None
            and not row.admission_conflicted
            and row.admission_claim_path == self.path_fingerprint
            and row.admission_expires_at is not None
            and row.admission_expires_at > time.time()
            and self.matches(row.admission_attribute)
        )

    async def state(
        self, session: AsyncSession | None = None
    ) -> PlatformAccessSettingsRow:
        state = await self.store.settings(session)
        if state is None or state.policy_fingerprint != self.fingerprint:
            raise HTTPException(503, "platform_access_unavailable")
        return state

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
        self, user: Principal, session: AsyncSession | None = None
    ) -> bool:
        uid = UUID(user.uid)
        if isinstance(user, KeycloakUser):
            row = (
                await self.store.user(uid, session)
                if session is not None
                else await self.store.observe(user, self.path_fingerprint)
            )
            # Equally-issued conflicting evidence cannot regain eligibility through replay.
            if await asyncio.to_thread(self.matches, user.admission_attribute) and (
                row is None
                or row.admission_issued_at != user.admission_issued_at
                or not row.admission_conflicted
            ):
                return True
        elif await asyncio.to_thread(
            self.observed_match, await self.store.user(uid, session)
        ):
            return True
        if await self.store.exception(uid, session) is not None:
            return True
        return bool(await self.team_sources(user.uid, session))

    async def admitted(self, user: Principal) -> bool:
        try:
            state = await self.state()
            if not state.filtering_enabled:
                if isinstance(user, KeycloakUser):
                    await self.store.observe(user, self.path_fingerprint)
                return True
            return await self.eligible(user)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "platform_access_unavailable") from None


_configured: PlatformAccessConfiguration = PlatformAccessConfiguration()
_installed: PlatformAccess | None = None


def configure_platform_access(security: SecurityConfiguration) -> None:
    global _configured, _installed
    _configured, _installed = security.platform_access, None
    if not _configured.enabled:
        return
    if (
        not security.user.enabled
        or not security.m2m.enabled
        or security.user_directory != "local"
        or security.rebac is None
        or not security.rebac.enabled
    ):
        raise ValueError(
            "Platform access requires user and workload authentication, local directory and ReBAC"
        )
    if (
        security.rebac.timeout_millisec is None
        or not 1 <= security.rebac.timeout_millisec <= 30000
    ):
        raise ValueError(
            "Platform access requires OpenFGA timeout_millisec between 1 and 30000"
        )
    from fred_core.security.whitelist_access_control.access_control import (
        is_whitelist_active,
    )

    if is_whitelist_active():
        raise ValueError(
            "Platform access cannot coexist with the legacy file whitelist"
        )


async def initialize_platform_access(
    security: SecurityConfiguration,
    engine: AsyncEngine,
    rebac: RebacEngine,
    *,
    authority: bool = False,
) -> None:
    global _installed
    if not security.platform_access.enabled:
        return
    if not rebac.enabled or not rebac.requires_active_accounts:
        raise ValueError("Platform access requires an enforced account-status engine")
    if engine.dialect.name != "postgresql":
        raise ValueError("Platform access requires the shared PostgreSQL database")
    await require_tables(
        engine,
        ["platform_access_settings", "platform_access_users", "users", "teammetadata"],
        component="platform-access",
        migrate_command="make db-upgrade (apps/control-plane-backend)",
        version_table="alembic_version_control_plane",
    )
    access = PlatformAccess(
        security.platform_access, PlatformAccessStore(engine), rebac
    )
    if authority:
        async with access.store.mutation() as session:
            state = await access.store.settings(session)
            if state is None:
                session.add(
                    PlatformAccessSettingsRow(
                        id=1, policy_fingerprint=access.fingerprint
                    )
                )
            else:
                state.policy_fingerprint = access.fingerprint
    await access.state()
    await access.store.teams(eligible_only=True)
    await access.store.users(0, 1)
    _installed = access


def get_platform_access() -> PlatformAccess:
    if not _configured.enabled:
        raise HTTPException(404, "platform_access_disabled")
    if _installed is None:
        raise HTTPException(503, "platform_access_unavailable")
    return _installed


async def enforce_platform_access(subject: Principal) -> None:
    if (
        not _configured.enabled
        or isinstance(subject, KeycloakUser)
        and (is_service_agent(subject) or subject.service_account)
    ):
        return
    if not await get_platform_access().admitted(subject):
        raise HTTPException(403, "platform_access_denied")


def platform_access_configuration() -> PlatformAccessConfiguration:
    return _configured


@asynccontextmanager
async def platform_access_team_mutation() -> AsyncIterator[None]:
    if not _configured.enabled:
        yield
        return
    access = get_platform_access()
    async with access.store.mutation() as session:
        await access.state(session)
        yield
