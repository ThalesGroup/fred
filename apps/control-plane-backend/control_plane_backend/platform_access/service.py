# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.delegation import require_active_subject
from fred_core.security.platform_access.access_control import PlatformAccess
from fred_core.security.platform_access.models import (
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.sql import use_session
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from fred_pod.security.structure import KeycloakUser
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.platform_access.schemas import (
    AdmissionSource,
    FreeEnrollmentPreview,
    PlatformAccessState,
    PlatformAccessStatus,
    PlatformAccessTeam,
    PlatformAccessUser,
    PlatformAccessUsersPage,
    PlatformT0Preview,
)
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.teams.service import _add_team_member_relation


def state_view(state: PlatformAccessSettingsRow) -> PlatformAccessState:
    return PlatformAccessState(
        filtering_enabled=state.filtering_enabled, t0_completed_at=state.t0_completed_at
    )


def team_view(team: TeamMetadataRow) -> PlatformAccessTeam:
    return PlatformAccessTeam(
        team_id=team.id,
        name=team.name,
        allowed=team.platform_access_allowed,
        free=team.platform_access_free,
        has_enrollment_link=team.enrollment_token_hash is not None,
    )


async def preserve_actor(
    access: PlatformAccess, actor: KeycloakUser, session: AsyncSession
) -> None:
    await session.flush()
    state = await access.state(session)
    if state.filtering_enabled and not await access.eligible(actor, session):
        raise HTTPException(409, "platform_access_actor_lockout")


async def set_filtering(
    access: PlatformAccess, actor: KeycloakUser, enabled: bool
) -> PlatformAccessState:
    async with access.store.mutation() as session:
        state = await access.state(session)
        state.filtering_enabled = enabled
        await preserve_actor(access, actor, session)
        return state_view(state)


async def set_user(
    access: PlatformAccess, actor: KeycloakUser, uid: UUID, grant: bool
) -> None:
    async with access.store.mutation() as session:
        await access.state(session)
        if await access.store.user(uid, session) is None:
            raise HTTPException(404, "user_not_found")
        if grant:
            await access.store.add_exception(uid, actor.uid, "manual", session)
        else:
            await session.execute(
                delete(PlatformAccessUserRow).where(
                    PlatformAccessUserRow.user_id == uid
                )
            )
        await preserve_actor(access, actor, session)


async def users_page(
    access: PlatformAccess, offset: int, limit: int, query: str
) -> PlatformAccessUsersPage:
    rows = await access.store.users(offset, limit, query)
    slots = asyncio.Semaphore(8)

    async def project(row: UserRow) -> PlatformAccessUser:
        async with slots:
            uid = str(row.id)
            sources: list[AdmissionSource] = []
            if await asyncio.to_thread(access.observed_match, row):
                sources.append(AdmissionSource(kind="attribute"))
            exception = await access.store.exception(UUID(uid))
            if exception is not None:
                sources.append(
                    AdmissionSource(
                        kind="t0" if exception.source == "t0" else "manual",
                        granted_by=exception.granted_by,
                        granted_at=exception.granted_at,
                    )
                )
            for team in await access.team_sources(uid):
                if team.platform_access_allowed:
                    sources.append(
                        AdmissionSource(
                            kind="team", team_id=team.id, team_name=team.name
                        )
                    )
                if team.platform_access_free:
                    sources.append(
                        AdmissionSource(
                            kind="free", team_id=team.id, team_name=team.name
                        )
                    )
            return PlatformAccessUser(
                user_id=uid, username=row.username, email=row.email, sources=sources
            )

    items = await asyncio.gather(*(project(row) for row in rows))
    return PlatformAccessUsersPage(
        items=items, total=await access.store.user_count(query)
    )


async def t0(
    access: PlatformAccess, actor: KeycloakUser | None = None
) -> PlatformT0Preview:
    async with access.store.mutation() as session:
        state = await access.state(session)
        if (
            actor is not None
            and state.filtering_enabled
            and state.t0_completed_at is None
        ):
            raise HTTPException(409, "t0_requires_inactive_filtering")
        rows = list((await session.scalars(select(UserRow))).all())
        matches = await asyncio.to_thread(
            lambda: [access.observed_match(row) for row in rows]
        )
        matching = sum(matches)
        candidates = len(rows) - matching
        if actor is not None and state.t0_completed_at is None:
            existing = set(
                (await session.scalars(select(PlatformAccessUserRow.user_id))).all()
            )
            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    PlatformAccessUserRow(
                        user_id=row.id,
                        source="t0",
                        granted_by=actor.uid,
                        granted_at=now,
                    )
                    for row, matches_attribute in zip(rows, matches, strict=True)
                    if not matches_attribute and row.id not in existing
                ]
            )
            state.t0_completed_at = now
        return PlatformT0Preview(
            candidates=candidates, matching=matching, completed_at=state.t0_completed_at
        )


async def require_team(
    access: PlatformAccess, team_id: str, session: AsyncSession
) -> TeamMetadataRow:
    if team_id.startswith("personal-"):
        raise HTTPException(400, "personal_team_not_eligible")
    team = await access.store.team(team_id, session)
    if team is None:
        raise HTTPException(404, "team_not_found")
    return team


async def set_team(
    access: PlatformAccess, actor: KeycloakUser, team_id: str, allowed: bool, free: bool
) -> PlatformAccessTeam:
    async with access.store.mutation() as session:
        await access.state(session)
        team = await require_team(access, team_id, session)
        team.platform_access_allowed, team.platform_access_free = allowed, free
        if not free:
            team.enrollment_token_hash = None
        await preserve_actor(access, actor, session)
        return team_view(team)


async def generate_link(access: PlatformAccess, team_id: str) -> str:
    async with access.store.mutation() as session:
        await access.state(session)
        team = await require_team(access, team_id, session)
        if not team.platform_access_free:
            raise HTTPException(409, "team_not_free")
        token = secrets.token_urlsafe(32)
        team.enrollment_token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token


async def require_link(
    access: PlatformAccess, token: str, session: AsyncSession
) -> TeamMetadataRow:
    if len(token) != 43:
        raise HTTPException(404, "free_enrollment_link_invalid")
    team = await access.store.link_team(
        hashlib.sha256(token.encode()).hexdigest(), session
    )
    if team is None:
        raise HTTPException(404, "free_enrollment_link_invalid")
    return team


async def cgu_required(
    access: PlatformAccess,
    uid: str,
    version: str | None,
    session: AsyncSession | None = None,
) -> bool:
    row = await access.store.user(UUID(uid), session)
    return version is not None and (
        row is None
        or row.gcuVersionAccepted is None
        or row.gcuVersionAccepted != version
    )


async def self_status(
    access: PlatformAccess, user: KeycloakUser, version: str | None
) -> PlatformAccessStatus:
    admitted = await access.admitted(user)
    return PlatformAccessStatus(
        admitted=admitted, cgu_required=await cgu_required(access, user.uid, version)
    )


async def preview_link(
    access: PlatformAccess, user: KeycloakUser, token: str, version: str | None
) -> FreeEnrollmentPreview:
    await access.state()
    await access.store.observe(user, access.path_fingerprint)
    async with use_session(access.store.sessions) as session:
        team = await require_link(access, token, session)
        return FreeEnrollmentPreview(
            team_name=team.name or team.id,
            cgu_required=await cgu_required(access, user.uid, version, session),
        )


async def accept_cgu(
    access: PlatformAccess,
    user: KeycloakUser,
    token: str,
    version: str,
    current: str | None,
) -> None:
    await access.store.observe(user, access.path_fingerprint)
    async with access.store.mutation() as session:
        await access.state(session)
        await require_link(access, token, session)
        if version != current:
            raise HTTPException(409, "gcu_version_changed")
        row = await access.store.user(UUID(user.uid), session)
        assert row is not None
        row.gcuVersionAccepted = version
        row.gcuAcceptedAt = datetime.now(timezone.utc)


async def enroll(
    access: PlatformAccess, user: KeycloakUser, token: str, version: str | None
) -> PlatformAccessStatus:
    await access.store.observe(user, access.path_fingerprint)
    async with access.store.mutation() as session:
        await require_active_subject(user)
        await access.state(session)
        team = await require_link(access, token, session)
        if await cgu_required(access, user.uid, version, session):
            raise HTTPException(403, "user_not_accept_gcu")
        if not (await access.rebac.has_team_memberships(user.uid, [team.id]))[0]:
            await _add_team_member_relation(
                access.rebac, TeamId(team.id), user.uid, UserTeamRelation.TEAM_MEMBER
            )
    emit_audit_log("platform.access.free.enrolled", actor_uid=user.uid, team_id=team.id)
    return await self_status(access, user, version)
