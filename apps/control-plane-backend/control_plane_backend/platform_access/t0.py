# SPDX-License-Identifier: Apache-2.0
"""Prepare and commit initial T0 imports or explicitly confirmed refreshes."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from fred_core.security.platform_access.access_control import PlatformAccess
from fred_core.security.platform_access.models import (
    PlatformAccessRemovalRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.users.user_models import UserRow
from fred_pod.security.structure import KeycloakUser
from sqlalchemy import select

from control_plane_backend.platform_access.directory import PlatformAccessDirectory
from control_plane_backend.platform_access.schemas import (
    PlatformT0Preview,
    PlatformT0RefreshMode,
    RefreshPlatformT0,
)
from control_plane_backend.users.schemas import UserSummary


def _check_refresh(
    state: PlatformAccessSettingsRow,
    mode: PlatformT0RefreshMode,
    refresh: RefreshPlatformT0 | None,
) -> None:
    if state.t0_completed_at is None:
        raise HTTPException(409, "t0_requires_completed_import")
    if refresh is not None and (
        state.revision != refresh.expected_revision
        or state.t0_completed_at.replace(
            tzinfo=state.t0_completed_at.tzinfo or timezone.utc
        ).astimezone(timezone.utc)
        != refresh.expected_completed_at.astimezone(timezone.utc)
    ):
        raise HTTPException(409, "platform_access_t0_snapshot_changed")
    if not state.t0_removal_history_complete and mode == "preserve_removals":
        raise HTTPException(409, "platform_access_t0_full_refresh_required")


async def run_t0(
    access: PlatformAccess,
    actor: KeycloakUser | None = None,
    directory: PlatformAccessDirectory | None = None,
    refresh_mode: PlatformT0RefreshMode | None = None,
    refresh: RefreshPlatformT0 | None = None,
) -> tuple[PlatformT0Preview, int | None]:
    """Preview without an actor; commit with one, validating refresh consent twice."""
    mode = refresh.mode if refresh is not None else refresh_mode
    state = await access.state()
    result = PlatformT0Preview(
        candidates=0,
        matching=0,
        completed_at=state.t0_completed_at,
        revision=state.revision,
        removal_history_complete=state.t0_removal_history_complete,
    )
    if mode is None and state.t0_completed_at is not None:
        return result, None
    if mode is not None:
        _check_refresh(state, mode, refresh)
    directory_profiles = (
        await directory.search()
        if directory is not None and not directory.local
        else None
    )
    async with access.store.read() as session:
        state = await access.state(session)
        rows = list((await session.scalars(select(UserRow))).all())
        existing = set(await session.scalars(select(PlatformAccessUserRow.user_id)))
        removed = (
            set(await session.scalars(select(PlatformAccessRemovalRow.user_id)))
            if mode == "preserve_removals"
            else set()
        )
    revision = state.revision
    policy = access.policy(state)
    by_id = {UUID(str(row.id)): row for row in rows}
    profiles = (
        directory_profiles
        if directory_profiles is not None
        else [
            UserSummary(
                id=str(row.id),
                username=row.username,
                email=row.email,
                first_name=row.first_name,
                last_name=row.last_name,
            )
            for row in rows
            if directory is None or row.username is not None
        ]
    )
    matches = await asyncio.to_thread(
        lambda: [
            access.observed_match(by_id.get(UUID(profile.id)), policy)
            for profile in profiles
        ]
    )
    candidates = [
        profile
        for profile, matched in zip(profiles, matches, strict=True)
        if not matched
    ]
    result.completed_at = state.t0_completed_at
    result.revision = revision
    result.removal_history_complete = state.t0_removal_history_complete
    result.matching = sum(matches)
    result.removed_skipped = sum(
        UUID(profile.id) in removed and UUID(profile.id) not in existing
        for profile in candidates
    )
    result.candidates = (
        sum(
            UUID(profile.id) not in existing and UUID(profile.id) not in removed
            for profile in candidates
        )
        if mode is not None
        else len(candidates)
    )
    if actor is None:
        if mode is not None:
            _check_refresh(state, mode, refresh)
        return result, None
    async with access.store.mutation() as session:
        state = await access.state(session)
        if mode is None and state.t0_completed_at is not None:
            result.completed_at = state.t0_completed_at
            result.removal_history_complete = state.t0_removal_history_complete
            return result, None
        if mode is not None:
            _check_refresh(state, mode, refresh)
        if state.revision != revision:
            raise HTTPException(409, "platform_access_t0_snapshot_changed")
        if mode is None and state.filtering_enabled:
            raise HTTPException(409, "t0_requires_inactive_filtering")
        existing = set(await session.scalars(select(PlatformAccessUserRow.user_id)))
        removed = (
            set(await session.scalars(select(PlatformAccessRemovalRow.user_id)))
            if mode == "preserve_removals"
            else set()
        )
        present = set(await session.scalars(select(UserRow.id)))
        now = datetime.now(timezone.utc)
        if state.t0_completed_at is not None:
            now = max(
                now,
                state.t0_completed_at.replace(
                    tzinfo=state.t0_completed_at.tzinfo or timezone.utc
                ).astimezone(timezone.utc)
                + timedelta(microseconds=1),
            )
        selected = [
            p
            for p in candidates
            if UUID(p.id) not in existing and UUID(p.id) not in removed
        ]
        added = 0
        for start in range(0, len(selected), 100):
            batch = selected[start : start + 100]
            if directory_profiles is not None:
                session.add_all(
                    [UserRow(id=UUID(p.id)) for p in batch if UUID(p.id) not in present]
                )
                await session.flush()
            new_rows = [
                PlatformAccessUserRow(
                    user_id=UUID(p.id),
                    source="t0",
                    granted_by=actor.uid,
                    granted_at=now,
                )
                for p in batch
                if directory_profiles is not None or UUID(p.id) in present
            ]
            session.add_all(new_rows)
            await session.flush()
            added += len(new_rows)
        state.t0_completed_at = now
        state.t0_removal_history_complete = True
        result.completed_at = now
        result.removal_history_complete = True
        result.imported_count = added
        return result, added
