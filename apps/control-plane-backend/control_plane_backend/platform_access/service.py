# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.delegation import require_active_subject
from fred_core.security.platform_access.access_control import PlatformAccess
from fred_core.security.platform_access.models import (
    PlatformAccessLinkRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.rules import evaluate, extract_claims
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from fred_pod.security.platform_access import PlatformAccessPolicy
from fred_pod.security.structure import KeycloakUser, is_service_agent
from pydantic import JsonValue
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.platform_access.schemas import (
    AdmissionSource,
    CreatePlatformEnrollmentLink,
    FreeEnrollmentPreview,
    PlatformAccessClaim,
    PlatformAccessOwnClaims,
    PlatformAccessPolicyPreview,
    PlatformAccessState,
    PlatformAccessStatus,
    PlatformAccessTeam,
    PlatformAccessUser,
    PlatformAccessUsersPage,
    PlatformEnrollmentLinkInfo,
    PlatformEnrollmentLinksPage,
    PlatformT0Preview,
)
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.teams.service import _add_team_member_relation


def state_view(state: PlatformAccessSettingsRow) -> PlatformAccessState:
    return PlatformAccessState(
        filtering_enabled=state.filtering_enabled,
        t0_completed_at=state.t0_completed_at,
        policy=PlatformAccess.policy(state),
        revision=state.revision,
    )


def team_view(team: TeamMetadataRow) -> PlatformAccessTeam:
    return PlatformAccessTeam(
        team_id=team.id,
        name=team.name,
        allowed=team.platform_access_allowed,
        free=team.platform_access_free,
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
        from fred_core.security.whitelist_access_control.access_control import (
            is_whitelist_active,
        )

        if enabled and is_whitelist_active():
            raise HTTPException(409, "platform_access_legacy_gate_conflict")
        if enabled and state.policy is None:
            raise HTTPException(409, "platform_access_policy_required")
        state.filtering_enabled = enabled
        await preserve_actor(access, actor, session)
        return state_view(state)


async def grant_users(
    access: PlatformAccess, actor: KeycloakUser, user_ids: list[UUID]
) -> None:
    selected = set(user_ids)
    async with access.store.mutation() as session:
        await access.state(session)
        existing = set(
            await session.scalars(select(UserRow.id).where(UserRow.id.in_(selected)))
        )
        if existing != selected:
            raise HTTPException(404, "user_not_found")
        for uid in selected:
            await access.store.add_exception(uid, actor.uid, "manual", session)


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
    policy = access.policy(await access.state())
    rows = await access.store.users(offset, limit, query)
    slots = asyncio.Semaphore(8)

    async def project(row: UserRow) -> PlatformAccessUser:
        async with slots:
            uid = str(row.id)
            sources: list[AdmissionSource] = []
            if await asyncio.to_thread(access.observed_match, row, policy):
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
    async with access.store.read() as session:
        state = await access.state(session)
        rows = list((await session.scalars(select(UserRow))).all())
    revision = state.revision
    policy = access.policy(state)
    matches = await asyncio.to_thread(
        lambda: [access.observed_match(row, policy) for row in rows]
    )
    matching, candidates = sum(matches), len(rows) - sum(matches)
    if actor is None:
        return PlatformT0Preview(
            candidates=candidates, matching=matching, completed_at=state.t0_completed_at
        )
    async with access.store.mutation() as session:
        state = await access.state(session)
        if state.t0_completed_at is not None:
            return PlatformT0Preview(
                candidates=candidates,
                matching=matching,
                completed_at=state.t0_completed_at,
            )
        if state.revision != revision:
            raise HTTPException(409, "platform_access_t0_snapshot_changed")
        if state.filtering_enabled and state.t0_completed_at is None:
            raise HTTPException(409, "t0_requires_inactive_filtering")
        if state.t0_completed_at is None:
            existing = set(
                (await session.scalars(select(PlatformAccessUserRow.user_id))).all()
            )
            present = set((await session.scalars(select(UserRow.id))).all())
            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    PlatformAccessUserRow(
                        user_id=row.id,
                        source="t0",
                        granted_by=actor.uid,
                        granted_at=now,
                    )
                    for row, matched in zip(rows, matches, strict=True)
                    if not matched and row.id in present and row.id not in existing
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
        await preserve_actor(access, actor, session)
        return team_view(team)


def utc(value: datetime | None) -> datetime | None:
    return (
        value.replace(tzinfo=timezone.utc)
        if value is not None and value.tzinfo is None
        else value
    )


def link_view(link: PlatformAccessLinkRow, free: bool) -> PlatformEnrollmentLinkInfo:
    expires = utc(link.expires_at)
    status: Literal["active", "suspended", "expired", "revoked"] = (
        "revoked"
        if link.revoked_at
        else "expired"
        if expires is not None and expires <= datetime.now(timezone.utc)
        else "suspended"
        if not free
        else "active"
    )
    return PlatformEnrollmentLinkInfo(
        id=link.id,
        note=link.note,
        created_at=utc(link.created_at) or link.created_at,
        expires_at=expires,
        revoked_at=utc(link.revoked_at),
        status=status,
        opening_count=link.opening_count,
        last_opened_at=utc(link.last_opened_at),
        recoverable=link.token is not None,
    )


async def generate_link(
    access: PlatformAccess,
    team_id: str,
    actor: KeycloakUser,
    body: CreatePlatformEnrollmentLink | None = None,
) -> str:
    body = body or CreatePlatformEnrollmentLink()
    async with access.store.mutation() as session:
        await access.state(session)
        team = await require_team(access, team_id, session)
        if not team.platform_access_free:
            raise HTTPException(409, "team_not_free")
        now = datetime.now(timezone.utc)
        if body.expires_at is not None and body.expires_at <= now:
            raise HTTPException(409, "free_enrollment_expiry_past")
        token = secrets.token_urlsafe(32)
        session.add(
            PlatformAccessLinkRow(
                id=uuid4(),
                team_id=team_id,
                token=token,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                note=body.note,
                created_by=actor.uid,
                created_at=now,
                expires_at=body.expires_at,
                opening_count=0,
            )
        )
        return token


async def list_links(
    access: PlatformAccess, team_id: str, offset: int, limit: int
) -> PlatformEnrollmentLinksPage:
    async with access.store.read() as session:
        await access.state(session)
        team = await require_team(access, team_id, session)
        predicate = PlatformAccessLinkRow.team_id == team_id
        rows = await session.scalars(
            select(PlatformAccessLinkRow)
            .where(predicate)
            .order_by(
                PlatformAccessLinkRow.created_at.desc(), PlatformAccessLinkRow.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        return PlatformEnrollmentLinksPage(
            items=[link_view(link, team.platform_access_free) for link in rows],
            total=int(
                await session.scalar(
                    select(func.count())
                    .select_from(PlatformAccessLinkRow)
                    .where(predicate)
                )
                or 0
            ),
        )


async def owned_link(
    access: PlatformAccess, team_id: str, link_id: UUID, session: AsyncSession
) -> PlatformAccessLinkRow:
    await require_team(access, team_id, session)
    link = await session.get(PlatformAccessLinkRow, link_id)
    if link is None or link.team_id != team_id:
        raise HTTPException(404, "free_enrollment_link_invalid")
    return link


async def reveal_link(access: PlatformAccess, team_id: str, link_id: UUID) -> str:
    async with access.store.read() as session:
        await access.state(session)
        link = await owned_link(access, team_id, link_id, session)
        if link.token is None:
            raise HTTPException(409, "free_enrollment_link_not_recoverable")
        return link.token


async def revoke_link(access: PlatformAccess, team_id: str, link_id: UUID) -> None:
    async with access.store.mutation() as session:
        await access.state(session)
        link = await owned_link(access, team_id, link_id, session)
        if link.revoked_at is None:
            link.revoked_at = datetime.now(timezone.utc)


async def require_link(
    access: PlatformAccess, token: str, session: AsyncSession
) -> tuple[PlatformAccessLinkRow, TeamMetadataRow]:
    if len(token) != 43:
        raise HTTPException(404, "free_enrollment_link_invalid")
    result = await access.store.link(
        hashlib.sha256(token.encode()).hexdigest(), session
    )
    if result is None:
        raise HTTPException(404, "free_enrollment_link_invalid")
    return result


async def record_opening(access: PlatformAccess, token: str) -> None:
    async with access.store.mutation() as session:
        await access.state(session)
        link, _ = await require_link(access, token, session)
        link.opening_count += 1
        link.last_opened_at = datetime.now(timezone.utc)


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
    await access.observe(user)
    async with access.store.read() as session:
        _, team = await require_link(access, token, session)
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
    await access.observe(user)
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
    await access.observe(user)
    async with access.store.mutation() as session:
        await require_active_subject(user)
        await access.state(session)
        _, team = await require_link(access, token, session)
        if await cgu_required(access, user.uid, version, session):
            raise HTTPException(403, "user_not_accept_gcu")
        if not (await access.rebac.has_team_memberships(user.uid, [team.id]))[0]:
            await _add_team_member_relation(
                access.rebac, TeamId(team.id), user.uid, UserTeamRelation.TEAM_MEMBER
            )
    emit_audit_log("platform.access.free.enrolled", actor_uid=user.uid, team_id=team.id)
    return await self_status(access, user, version)


async def claim_catalog(access: PlatformAccess) -> list[PlatformAccessClaim]:
    await access.state()
    kinds: tuple[Literal["string", "string_array"], ...] = ("string", "string_array")
    return [
        PlatformAccessClaim(
            path=row.path,
            types=[
                kind
                for kind, seen in zip(
                    kinds, (row.string_seen, row.array_seen), strict=True
                )
                if seen
            ],
        )
        for row in await access.store.claims()
    ]


def require_own_credential(actor: KeycloakUser) -> None:
    if (
        not isinstance(actor, KeycloakUser)
        or actor.service_account
        or is_service_agent(actor)
    ):
        raise HTTPException(403, "requires_own_credential")


def own_claims(payload: dict[str, object]) -> PlatformAccessOwnClaims:
    visited, budget = 0, 60_000
    truncated = False

    def project(value: object, depth: int) -> tuple[bool, JsonValue]:
        nonlocal visited, budget, truncated
        if visited >= 1024 or depth > 16 or budget <= 0:
            truncated = True
            return False, None
        visited += 1
        budget -= 2
        if isinstance(value, dict):
            result: dict[str, JsonValue] = {}
            for key, child in value.items():
                if visited >= 1024 or budget <= 0:
                    truncated = True
                    break
                visited += 1
                if not isinstance(key, str) or len(key) > 256:
                    truncated = True
                    continue
                cost = len(json.dumps(key, ensure_ascii=True)) + 2
                if cost > budget:
                    truncated = True
                    break
                budget -= cost
                included, projected = project(child, depth + 1)
                if included:
                    result[key] = projected
            return True, result
        if isinstance(value, list):
            if len(value) > 32:
                truncated = True
                return False, None
            items: list[JsonValue] = []
            for child in value:
                included, projected = project(child, depth + 1)
                if not included:
                    return False, None
                items.append(projected)
            return True, items
        if value is None or isinstance(value, (str, bool, int, float)):
            if isinstance(value, str) and len(value) > 1024:
                truncated = True
                return False, None
            cost = len(json.dumps(value, ensure_ascii=True)) + 1
            if cost > budget:
                truncated = True
                return False, None
            budget -= cost
            return True, cast(JsonValue, value)
        truncated = True
        return False, None

    _, projected = project(payload, 0)
    claims = cast(dict[str, JsonValue], projected)
    facts, _ = extract_claims(claims)
    original, _ = extract_claims(payload)
    return PlatformAccessOwnClaims(
        claims=claims,
        selectable_paths=[json.loads(key) for key in facts if key in original],
        truncated=truncated,
    )


async def preview_policy(
    access: PlatformAccess, actor: KeycloakUser, policy: PlatformAccessPolicy
) -> PlatformAccessPolicyPreview:
    require_own_credential(actor)
    async with access.store.read() as session:
        await access.state(session)
        result = await asyncio.to_thread(
            evaluate, policy, actor.admission_claims, actor.admission_invalid_claims
        )
        admitted = await access.eligible(
            actor, session, policy=policy, use_current_policy=False
        )
        return PlatformAccessPolicyPreview(
            matched=result.matched, admitted=admitted, conditions=result.reasons
        )


async def save_policy(
    access: PlatformAccess,
    actor: KeycloakUser,
    policy: PlatformAccessPolicy,
    expected_revision: int,
) -> PlatformAccessState:
    async with access.store.mutation() as session:
        state = await access.state(session)
        if state.revision != expected_revision:
            raise HTTPException(409, "platform_access_policy_conflict")
        state.policy = policy.model_dump()
        state.revision += 1
        await preserve_actor(access, actor, session)
        return state_view(state)
