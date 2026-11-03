# SPDX-License-Identifier: Apache-2.0
import asyncio
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.delegation import require_active_subject
from fred_core.security.models import AccountStatusError
from fred_core.security.platform_access.access_control import PlatformAccess
from fred_core.security.platform_access.models import (
    PlatformAccessLinkJoinerRow,
    PlatformAccessLinkRow,
    PlatformAccessRemovalRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.rules import (
    allows,
    evaluate,
    extract_claims,
    path_key,
)
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.sql.accent_folding import fold_text
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from fred_pod.security.platform_access import PlatformAccessPolicy
from fred_pod.security.structure import KeycloakUser, is_service_agent
from pydantic import JsonValue
from sqlalchemy import delete, func, inspect, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from control_plane_backend.platform_access.directory import PlatformAccessDirectory
from control_plane_backend.platform_access.schemas import (
    AdmissionSource,
    CreatePlatformEnrollmentLink,
    EnrollmentResult,
    FreeEnrollmentPreview,
    PlatformAccessActivationPreview,
    PlatformAccessActivationUser,
    PlatformAccessOwnClaims,
    PlatformAccessPolicyPreview,
    PlatformAccessState,
    PlatformAccessStatus,
    PlatformAccessTeam,
    PlatformAccessUser,
    PlatformAccessUsersPage,
    PlatformEnrollmentJoiner,
    PlatformEnrollmentJoinersPage,
    PlatformEnrollmentLinkInfo,
    PlatformEnrollmentLinksPage,
    PlatformEnrollmentLinkStatus,
    PlatformT0Preview,
    PlatformT0RefreshMode,
    RefreshPlatformT0,
    TeamJoinLink,
)
from control_plane_backend.platform_access.t0 import run_t0
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.teams.service import _add_team_member_relation
from control_plane_backend.users.schemas import UserSummary


async def has_admission_sources(
    access: PlatformAccess,
    state: PlatformAccessSettingsRow,
    session: AsyncSession | None = None,
) -> bool:
    if state.policy is not None:
        return True
    async with access.store.read(session) as active:
        if await active.scalar(select(select(PlatformAccessUserRow.user_id).exists())):
            return True
        return bool(
            await active.scalar(
                select(
                    select(TeamMetadataRow.id)
                    .where(
                        ~TeamMetadataRow.id.startswith("personal-"),
                        # A Free team only admits its Free-link joiners.
                        TeamMetadataRow.platform_access_allowed
                        | (
                            TeamMetadataRow.platform_access_free
                            & select(PlatformAccessLinkJoinerRow.user_id)
                            .join(
                                PlatformAccessLinkRow,
                                PlatformAccessLinkRow.id
                                == PlatformAccessLinkJoinerRow.link_id,
                            )
                            .where(
                                PlatformAccessLinkRow.team_id == TeamMetadataRow.id,
                                PlatformAccessLinkRow.kind == "free",
                                PlatformAccessLinkJoinerRow.deleted_at.is_(None),
                            )
                            .exists()
                        ),
                    )
                    .exists()
                )
            )
        )


async def state_view(
    access: PlatformAccess,
    state: PlatformAccessSettingsRow,
    session: AsyncSession | None = None,
) -> PlatformAccessState:
    return PlatformAccessState(
        filtering_enabled=state.filtering_enabled,
        t0_completed_at=state.t0_completed_at,
        policy=PlatformAccess.policy(state),
        revision=state.revision,
        has_admission_sources=await has_admission_sources(access, state, session),
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
    access: PlatformAccess,
    actor: KeycloakUser,
    enabled: bool,
    expected_revision: int | None = None,
) -> PlatformAccessState:
    async with access.store.mutation() as session:
        state = await access.state(session)
        if expected_revision is not None and expected_revision != state.revision:
            raise HTTPException(409, "platform_access_policy_conflict")
        if enabled and not await has_admission_sources(access, state, session):
            raise HTTPException(409, "platform_access_policy_required")
        state.filtering_enabled = enabled
        await preserve_actor(access, actor, session)
        return await state_view(access, state, session)


async def grant_users(
    access: PlatformAccess,
    actor: KeycloakUser,
    user_ids: list[UUID],
    directory: PlatformAccessDirectory | None = None,
) -> int:
    selected = sorted(set(user_ids))
    profiles = (
        await directory.by_ids(str(uid) for uid in selected)
        if directory is not None and not directory.local
        else None
    )
    if profiles is not None and set(profiles) != {str(uid) for uid in selected}:
        raise HTTPException(404, "user_not_found")
    granted_count = 0
    async with access.store.mutation() as session:
        await access.state(session)
        now = datetime.now(timezone.utc)
        for start in range(0, len(selected), 500):
            batch = selected[start : start + 500]
            existing_rows = list(
                (
                    await session.scalars(select(UserRow).where(UserRow.id.in_(batch)))
                ).all()
            )
            existing = {row.id for row in existing_rows}
            if profiles is None and (
                existing != set(batch)
                or directory is not None
                and directory.local
                and any(row.username is None for row in existing_rows)
            ):
                raise HTTPException(404, "user_not_found")
            if profiles is not None:
                session.add_all(
                    [UserRow(id=uid) for uid in batch if uid not in existing]
                )
                await session.flush()
            granted = set(
                await session.scalars(
                    select(PlatformAccessUserRow.user_id).where(
                        PlatformAccessUserRow.user_id.in_(batch)
                    )
                )
            )
            new_batch = [uid for uid in batch if uid not in granted]
            session.add_all(
                [
                    PlatformAccessUserRow(
                        user_id=uid,
                        source="manual",
                        granted_by=actor.uid,
                        granted_at=now,
                    )
                    for uid in new_batch
                ]
            )
            granted_count += len(new_batch)
    return granted_count


async def set_user(
    access: PlatformAccess,
    actor: KeycloakUser,
    uid: UUID,
    grant: bool,
    directory: PlatformAccessDirectory | None = None,
) -> None:
    profile = None
    if grant and directory is not None and not directory.local:
        profile = (await directory.by_ids([str(uid)])).get(str(uid))
        if profile is None:
            raise HTTPException(404, "user_not_found")
    async with access.store.mutation() as session:
        await access.state(session)
        row = await access.store.user(uid, session)
        if row is None and profile is None:
            raise HTTPException(404, "user_not_found")
        if grant and directory is not None and directory.local and row is not None:
            if row.username is None:
                raise HTTPException(404, "user_not_found")
        if row is None and profile is not None:
            session.add(UserRow(id=uid))
            await session.flush()
        if grant:
            await access.store.add_exception(uid, actor.uid, "manual", session)
        else:
            exception = await access.store.exception(uid, session)
            if exception is not None:
                removal = await session.get(PlatformAccessRemovalRow, uid)
                if removal is None:
                    removal = PlatformAccessRemovalRow(user_id=uid)
                    session.add(removal)
                removal.removed_at = datetime.now(timezone.utc)
                removal.removed_by = actor.uid
                await session.delete(exception)
        await preserve_actor(access, actor, session)


async def users_page(
    access: PlatformAccess,
    offset: int,
    limit: int,
    query: str,
    exceptions_only: bool = False,
    directory: PlatformAccessDirectory | None = None,
) -> PlatformAccessUsersPage:
    policy = access.policy(await access.state())
    if directory is not None and not directory.local:
        if exceptions_only:
            try:
                query_id = UUID(query.strip())
            except ValueError:
                query_id = None
            if query_id is not None:
                rows = await access.store.users_with_exceptions(
                    offset, limit, str(query_id), exceptions_only=True
                )
                total = await access.store.user_count(
                    str(query_id), exceptions_only=True
                )
                resolved = await directory.by_ids(str(row.id) for row, _ in rows)
            elif query.strip():
                candidates = await access.store.users_with_exceptions(
                    0, None, exceptions_only=True
                )
                resolved = await directory.by_ids(str(row.id) for row, _ in candidates)
                needle = fold_text(query.strip())
                matched = [
                    (row, exception)
                    for row, exception in candidates
                    if (profile := resolved.get(str(row.id))) is not None
                    and any(
                        needle in fold_text(value)
                        for value in (
                            profile.username,
                            profile.email,
                            profile.first_name,
                            profile.last_name,
                        )
                        if value
                    )
                ]
                total = len(matched)
                rows = matched[offset : offset + limit]
            else:
                rows = await access.store.users_with_exceptions(
                    offset, limit, exceptions_only=True
                )
                total = await access.store.user_count(exceptions_only=True)
                resolved = await directory.by_ids(str(row.id) for row, _ in rows)
            entries = [
                (resolved.get(str(row.id), UserSummary(id=str(row.id))), row, exception)
                for row, exception in rows
            ]
        else:
            selected, total = await directory.search_page(query.strip(), offset, limit)
            ids = {directory.uuid(profile) for profile in selected}
            async with access.store.read() as session:
                local_rows = {
                    UUID(str(row.id)): row
                    for row in (
                        await session.scalars(
                            select(UserRow).where(UserRow.id.in_(ids))
                        )
                    ).all()
                }
                exceptions = {
                    UUID(str(row.user_id)): row
                    for row in (
                        await session.scalars(
                            select(PlatformAccessUserRow).where(
                                PlatformAccessUserRow.user_id.in_(ids)
                            )
                        )
                    ).all()
                }
            entries = [
                (
                    profile,
                    local_rows.get(directory.uuid(profile)),
                    exceptions.get(directory.uuid(profile)),
                )
                for profile in selected
            ]
    else:
        identities_only = (
            directory is not None and directory.local and not exceptions_only
        )
        rows = await access.store.users_with_exceptions(
            offset,
            limit,
            query,
            exceptions_only=exceptions_only,
            identities_only=identities_only,
        )
        total = await access.store.user_count(
            query, exceptions_only=exceptions_only, identities_only=identities_only
        )
        entries = [
            (
                UserSummary(
                    id=str(row.id),
                    username=row.username,
                    email=row.email,
                    first_name=row.first_name,
                    last_name=row.last_name,
                ),
                row,
                exception,
            )
            for row, exception in rows
        ]
    slots = asyncio.Semaphore(8)

    async def project(
        profile: UserSummary,
        row: UserRow | None,
        exception: PlatformAccessUserRow | None,
    ) -> PlatformAccessUser:
        async with slots:
            uid = profile.id
            sources: list[AdmissionSource] = []
            if await access.access_manager_uid(uid):
                sources.append(AdmissionSource(kind="admin"))
            if await asyncio.to_thread(access.observed_match, row, policy):
                sources.append(AdmissionSource(kind="attribute"))
            if exception is not None:
                sources.append(
                    AdmissionSource(
                        kind="t0" if exception.source == "t0" else "manual",
                        granted_by=exception.granted_by,
                        granted_at=exception.granted_at,
                    )
                )
            for team, allowed, free in await access.team_sources(uid):
                if allowed:
                    sources.append(
                        AdmissionSource(
                            kind="team", team_id=team.id, team_name=team.name
                        )
                    )
                if free:
                    sources.append(
                        AdmissionSource(
                            kind="free", team_id=team.id, team_name=team.name
                        )
                    )
            return PlatformAccessUser(
                user_id=uid,
                username=profile.username or uid,
                email=profile.email,
                first_name=profile.first_name,
                last_name=profile.last_name,
                sources=sources,
            )

    items = await asyncio.gather(*(project(*entry) for entry in entries))
    return PlatformAccessUsersPage(items=items, total=total)


async def activation_preview(
    access: PlatformAccess, directory: PlatformAccessDirectory | None = None
) -> PlatformAccessActivationPreview:
    directory_profiles = (
        await directory.search()
        if directory is not None and not directory.local
        else None
    )
    async with access.store.read() as session:
        state = await access.state(session)
        policy, revision = access.policy(state), state.revision
        rows = list((await session.scalars(select(UserRow).order_by(UserRow.id))).all())
        exceptions = {
            row.user_id: row
            for row in (await session.scalars(select(PlatformAccessUserRow))).all()
        }
        teams = await access.store.teams(session, eligible_only=True)
        free_joined = await access.store.free_joined_teams(session=session)
    if directory_profiles is None:
        entries = [
            (
                UserSummary(
                    id=str(row.id),
                    username=row.username,
                    email=row.email,
                    first_name=row.first_name,
                    last_name=row.last_name,
                ),
                row,
            )
            for row in rows
            if directory is None or row.username is not None
        ]
    else:
        by_id = {UUID(str(row.id)): row for row in rows}
        entries = [
            (profile, by_id.get(UUID(profile.id))) for profile in directory_profiles
        ]
    slots = asyncio.Semaphore(8)

    async def project(
        profile: UserSummary, row: UserRow | None
    ) -> PlatformAccessActivationUser:
        async with slots:
            uid = profile.id
            outcome: Literal["allowed", "blocked", "unknown"] = "unknown"
            sources: list[AdmissionSource] = []
            try:
                await access.rebac.require_active_account(uid)
            except AccountStatusError as error:
                outcome = "unknown" if error.unavailable else "blocked"
            else:
                if await access.access_manager_uid(uid):
                    sources.append(AdmissionSource(kind="admin"))
                exception = exceptions.get(UUID(uid))
                if exception:
                    sources.append(
                        AdmissionSource(
                            kind="t0" if exception.source == "t0" else "manual",
                            granted_by=exception.granted_by,
                            granted_at=exception.granted_at,
                        )
                    )
                if sources:
                    outcome = "allowed"
                elif policy is None:
                    outcome = "blocked"
                elif (
                    row is not None
                    and not row.admission_conflicted
                    and row.admission_expires_at is not None
                    and row.admission_expires_at > time.time()
                    and all(
                        path_key(condition.claim) in (row.admission_attribute or {})
                        for condition in policy.conditions
                    )
                ):
                    result = await asyncio.to_thread(
                        evaluate, policy, row.admission_attribute or {}
                    )
                    if not any(
                        reason in ("timeout", "unavailable")
                        for reason in result.reasons
                    ):
                        outcome = "allowed" if allows(policy, result) else "blocked"
                        if outcome == "allowed":
                            sources.append(AdmissionSource(kind="attribute"))
                if outcome != "allowed":
                    # Free admits only people who joined through that team's Free link.
                    joined = free_joined.get(UUID(uid), set())
                    candidates = [
                        team
                        for team in teams
                        if team.platform_access_allowed or team.id in joined
                    ]
                    for start in range(0, len(candidates), 8):
                        batch = candidates[start : start + 8]
                        memberships = await access.rebac.has_team_memberships(
                            uid, [team.id for team in batch]
                        )
                        if len(memberships) != len(batch) or any(
                            type(value) is not bool for value in memberships
                        ):
                            raise HTTPException(503, "platform_access_unavailable")
                        for team, member in zip(batch, memberships, strict=True):
                            if member:
                                sources.append(
                                    AdmissionSource(
                                        kind="free"
                                        if team.platform_access_free
                                        and team.id in joined
                                        else "team",
                                        team_id=team.id,
                                        team_name=team.name,
                                    )
                                )
                        if sources:
                            outcome = "allowed"
                            break
            return PlatformAccessActivationUser(
                user_id=uid,
                username=profile.username or uid,
                email=profile.email,
                first_name=profile.first_name,
                last_name=profile.last_name,
                sources=sources,
                outcome=outcome,
            )

    # Queue work in bounded batches as well as limiting in-flight authority calls.
    items: list[PlatformAccessActivationUser] = []
    for start in range(0, len(entries), 100):
        items.extend(
            await asyncio.gather(
                *(project(*entry) for entry in entries[start : start + 100])
            )
        )
    if (await access.state()).revision != revision:
        raise HTTPException(409, "platform_access_policy_conflict")
    return PlatformAccessActivationPreview(
        users=items,
        allowed=sum(row.outcome == "allowed" for row in items),
        blocked=sum(row.outcome == "blocked" for row in items),
        unknown=sum(row.outcome == "unknown" for row in items),
        revision=revision,
        checked_at=datetime.now(timezone.utc),
    )


async def t0(
    access: PlatformAccess,
    actor: KeycloakUser | None = None,
    directory: PlatformAccessDirectory | None = None,
    refresh_mode: PlatformT0RefreshMode | None = None,
) -> PlatformT0Preview:
    result, _ = await run_t0(access, actor, directory, refresh_mode)
    return result


async def import_t0(
    access: PlatformAccess,
    actor: KeycloakUser,
    directory: PlatformAccessDirectory | None = None,
    refresh: RefreshPlatformT0 | None = None,
) -> tuple[PlatformT0Preview, int | None]:
    return await run_t0(access, actor, directory, refresh=refresh)


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


# Platform administrators manage Free-team links only; team join links are managed
# by team admins through the single-link functions below.
FREE_LINKS = PlatformAccessLinkRow.kind == "free"


def new_link_row(
    team_id: str,
    actor: KeycloakUser,
    kind: str,
    note: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[str, PlatformAccessLinkRow]:
    token = secrets.token_urlsafe(32)
    return token, PlatformAccessLinkRow(
        id=uuid4(),
        team_id=team_id,
        kind=kind,
        token=token,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        note=note,
        created_by=actor.uid,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        opening_count=0,
    )


def link_view(
    link: PlatformAccessLinkRow, free: bool, now: datetime
) -> PlatformEnrollmentLinkInfo:
    expires = utc(link.expires_at)
    status: PlatformEnrollmentLinkStatus = (
        "revoked"
        if link.revoked_at
        else "expired"
        if expires is not None and expires <= now
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


async def generate_link_record(
    access: PlatformAccess,
    team_id: str,
    actor: KeycloakUser,
    body: CreatePlatformEnrollmentLink | None = None,
) -> tuple[str, UUID]:
    body = body or CreatePlatformEnrollmentLink()
    async with access.store.mutation() as session:
        await access.state(session)
        team = await require_team(access, team_id, session)
        if not team.platform_access_free:
            raise HTTPException(409, "team_not_free")
        now = datetime.now(timezone.utc)
        if body.expires_at is not None and body.expires_at <= now:
            raise HTTPException(409, "free_enrollment_expiry_past")
        token, link = new_link_row(team_id, actor, "free", body.note, body.expires_at)
        session.add(link)
        return token, link.id


async def generate_link(
    access: PlatformAccess,
    team_id: str,
    actor: KeycloakUser,
    body: CreatePlatformEnrollmentLink | None = None,
) -> str:
    token, _ = await generate_link_record(access, team_id, actor, body)
    return token


async def list_links(
    access: PlatformAccess,
    team_id: str,
    offset: int,
    limit: int,
    status: PlatformEnrollmentLinkStatus | None = None,
) -> PlatformEnrollmentLinksPage:
    async with access.store.read() as session:
        await access.state(session)
        team = await require_team(access, team_id, session)
        now = datetime.now(timezone.utc)
        predicate = (PlatformAccessLinkRow.team_id == team_id) & FREE_LINKS
        if status == "revoked":
            predicate &= PlatformAccessLinkRow.revoked_at.is_not(None)
        elif status == "expired":
            predicate &= PlatformAccessLinkRow.revoked_at.is_(None) & (
                PlatformAccessLinkRow.expires_at <= now
            )
        elif status in ("active", "suspended"):
            predicate &= (
                PlatformAccessLinkRow.revoked_at.is_(None)
                & or_(
                    PlatformAccessLinkRow.expires_at.is_(None),
                    PlatformAccessLinkRow.expires_at > now,
                )
                & (team.platform_access_free == (status == "active"))
            )
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
            items=[link_view(link, team.platform_access_free, now) for link in rows],
            total=int(
                await session.scalar(
                    select(func.count())
                    .select_from(PlatformAccessLinkRow)
                    .where(predicate)
                )
                or 0
            ),
            inactive_count=int(
                await session.scalar(
                    select(func.count())
                    .select_from(PlatformAccessLinkRow)
                    .where(
                        PlatformAccessLinkRow.team_id == team_id,
                        FREE_LINKS,
                        obsolete_links(now),
                    )
                )
                or 0
            ),
        )


async def list_link_joiners(
    access: PlatformAccess, team_id: str, link_id: UUID, offset: int, limit: int
) -> PlatformEnrollmentJoinersPage:
    async with access.store.read() as session:
        await access.state(session)
        await owned_link(access, team_id, link_id, session)
        rows = await session.execute(
            select(PlatformAccessLinkJoinerRow, UserRow)
            .outerjoin(UserRow, UserRow.id == PlatformAccessLinkJoinerRow.user_id)
            .where(PlatformAccessLinkJoinerRow.link_id == link_id)
            .order_by(
                PlatformAccessLinkJoinerRow.joined_at,
                PlatformAccessLinkJoinerRow.user_id,
            )
            .offset(offset)
            .limit(limit)
        )
        total = await session.scalar(
            select(func.count())
            .select_from(PlatformAccessLinkJoinerRow)
            .where(PlatformAccessLinkJoinerRow.link_id == link_id)
        )
        return PlatformEnrollmentJoinersPage(
            items=[
                PlatformEnrollmentJoiner(
                    user_id=str(joiner.user_id),
                    username=(
                        joiner.username_snapshot
                        if joiner.deleted_at or user is None
                        else user.username
                    ),
                    first_name=(
                        joiner.first_name_snapshot
                        if joiner.deleted_at or user is None
                        else user.first_name
                    ),
                    last_name=(
                        joiner.last_name_snapshot
                        if joiner.deleted_at or user is None
                        else user.last_name
                    ),
                    joined_at=joiner.joined_at,
                    deleted=joiner.deleted_at is not None or user is None,
                )
                for joiner, user in rows
            ],
            total=int(total or 0),
        )


async def mark_user_join_history_deleted(
    store: PlatformAccessStore, user_id: str, *, table_may_be_missing: bool = False
) -> None:
    try:
        uid = UUID(user_id)
    except ValueError:
        return
    async with store.mutation() as session:
        if table_may_be_missing and not await session.run_sync(
            lambda sync: inspect(sync.connection()).has_table(
                PlatformAccessLinkJoinerRow.__tablename__
            )
        ):
            return
        profile = await session.get(UserRow, uid)
        snapshots: dict[str, Any] = {}
        if profile is not None:
            for field in ("username", "first_name", "last_name"):
                value = getattr(profile, field)
                if value is not None:
                    snapshots[f"{field}_snapshot"] = value
        await session.execute(
            update(PlatformAccessLinkJoinerRow)
            .where(PlatformAccessLinkJoinerRow.user_id == uid)
            .values(deleted_at=datetime.now(timezone.utc), **snapshots)
        )


def obsolete_links(now: datetime) -> ColumnElement[bool]:
    return or_(
        PlatformAccessLinkRow.revoked_at.is_not(None),
        PlatformAccessLinkRow.expires_at <= now,
    )


async def delete_inactive_links(access: PlatformAccess, team_id: str) -> int:
    async with access.store.mutation() as session:
        await access.state(session)
        await require_team(access, team_id, session)
        result = await session.execute(
            delete(PlatformAccessLinkRow).where(
                PlatformAccessLinkRow.team_id == team_id,
                FREE_LINKS,
                obsolete_links(datetime.now(timezone.utc)),
            )
        )
        return cast(CursorResult[Any], result).rowcount


async def owned_link(
    access: PlatformAccess, team_id: str, link_id: UUID, session: AsyncSession
) -> PlatformAccessLinkRow:
    await require_team(access, team_id, session)
    link = await session.get(PlatformAccessLinkRow, link_id)
    if link is None or link.team_id != team_id or link.kind != "free":
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


async def team_link(
    access: PlatformAccess, team_id: str, session: AsyncSession
) -> PlatformAccessLinkRow | None:
    await require_team(access, team_id, session)
    return await session.scalar(
        select(PlatformAccessLinkRow).where(
            PlatformAccessLinkRow.team_id == team_id,
            PlatformAccessLinkRow.kind == "team",
        )
    )


def team_link_view(link: PlatformAccessLinkRow | None) -> TeamJoinLink:
    if link is None:
        return TeamJoinLink(enabled=False)
    return TeamJoinLink(enabled=not link.paused, token=link.token)


async def get_team_link(access: PlatformAccess, team_id: str) -> TeamJoinLink:
    async with access.store.read() as session:
        await access.state(session)
        return team_link_view(await team_link(access, team_id, session))


async def set_team_link(
    access: PlatformAccess, team_id: str, actor: KeycloakUser, enabled: bool
) -> TeamJoinLink:
    """Pausing and resuming keep the same URL; the first enabling creates it."""
    async with access.store.mutation() as session:
        await access.state(session)
        link = await team_link(access, team_id, session)
        if link is None and enabled:
            _, link = new_link_row(team_id, actor, "team")
            session.add(link)
        elif link is not None:
            link.paused = not enabled
        return team_link_view(link)


async def regenerate_team_link(
    access: PlatformAccess, team_id: str, actor: KeycloakUser
) -> TeamJoinLink:
    """Replaces the team's link for good: the previous URL becomes invalid."""
    async with access.store.mutation() as session:
        await access.state(session)
        await require_team(access, team_id, session)
        await session.execute(
            delete(PlatformAccessLinkRow).where(
                PlatformAccessLinkRow.team_id == team_id,
                PlatformAccessLinkRow.kind == "team",
            )
        )
        _, link = new_link_row(team_id, actor, "team")
        session.add(link)
        return team_link_view(link)


async def require_link_caller(
    access: PlatformAccess, user: KeycloakUser, token: str
) -> None:
    """A team link never admits: its caller must already have platform access."""
    async with access.store.read() as session:
        link, _ = await require_link(access, token, session)
    if link.kind == "team" and not await access.admitted(user):
        raise HTTPException(403, "team_link_requires_platform_access")


async def record_opening(
    access: PlatformAccess, token: str, user: KeycloakUser
) -> None:
    await require_link_caller(access, user, token)
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
    await access.observe(user)
    await require_link_caller(access, user, token)
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
    await require_link_caller(access, user, token)
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
) -> EnrollmentResult:
    await access.observe(user)
    await require_link_caller(access, user, token)
    joined = False
    async with access.store.mutation() as session:
        await require_active_subject(user)
        await access.state(session)
        link, team = await require_link(access, token, session)
        if await cgu_required(access, user.uid, version, session):
            raise HTTPException(403, "user_not_accept_gcu")
        if not (await access.rebac.has_team_memberships(user.uid, [team.id]))[0]:
            await _add_team_member_relation(
                access.rebac, TeamId(team.id), user.uid, UserTeamRelation.TEAM_MEMBER
            )
            joined = True
        # The joiner row is the Free admission source, so a member who enrolls
        # through a Free link gets it too; team links never record one.
        if (
            link.kind == "free"
            and await session.get(
                PlatformAccessLinkJoinerRow, (link.id, UUID(user.uid))
            )
            is None
        ):
            session.add(
                PlatformAccessLinkJoinerRow(
                    link_id=link.id,
                    user_id=UUID(user.uid),
                    joined_at=datetime.now(timezone.utc),
                    username_snapshot=user.username,
                    first_name_snapshot=user.first_name,
                    last_name_snapshot=user.last_name,
                )
            )
            joined = True
    if joined:
        emit_audit_log(
            "team.join_link.joined"
            if link.kind == "team"
            else "platform.access.free.enrolled",
            actor_uid=user.uid,
            team_id=team.id,
            link_id=str(link.id),
        )
    status = await self_status(access, user, version)
    return EnrollmentResult(
        **status.model_dump(), team_id=team.id if status.admitted else None
    )


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
        return await state_view(access, state, session)
