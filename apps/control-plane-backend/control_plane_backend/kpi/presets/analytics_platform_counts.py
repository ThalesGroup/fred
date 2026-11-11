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

"""Analytics figures read from Postgres and ReBAC rather than from KPI events."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from fastapi import HTTPException, Request
from fred_core.common import TeamId
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.platform_access.models import PlatformAccessUserRow
from fred_core.users.store.postgres_user_store import get_user_store
from sqlalchemy import select

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.analytics_common import PeriodValue, Windows
from control_plane_backend.platform_access.service import activation_preview
from control_plane_backend.teams.service import team_member_ids

logger = logging.getLogger(__name__)

ADMITTED_TTL_SECONDS = 600
ADMITTED_TIMEOUT_SECONDS = 60
# A failed count is remembered briefly so a slow ReBAC does not stall every load.
ADMITTED_FAILURE_TTL_SECONDS = 90
# Policy revision -> (expiry on the monotonic clock, admitted user ids or None). Pod-local.
_admitted: dict[int, tuple[float, frozenset[str] | None]] = {}
_admitted_lock = asyncio.Lock()


async def people_with_access(
    request: Request,
    team_ids: Sequence[TeamId],
    user_ids: Sequence[str] | None = None,
) -> int | None:
    """Members of the selected teams; else, when access filtering is on, users the
    admission rule admits plus the whitelisted ones; else every known user.
    A user filter keeps its matches only (they are known users). None = unknown."""
    matched = set(user_ids) if user_ids is not None else None
    if team_ids:
        rebac = get_application_container(request).get_rebac_engine()
        members = await team_member_ids(rebac, list(team_ids))
        people = set().union(*members.values())
        return len(people & matched if matched is not None else people)
    try:
        access = get_platform_access()
        state = await access.state()
    except HTTPException as error:
        # 404: platform access is not installed, nobody is filtered out.
        if error.status_code != 404:
            return None
        if matched is not None:
            return len(matched)
        return await get_user_store().count_identities()
    if state.filtering_enabled:
        admitted = await _admitted_users(access, state.revision)
        if admitted is None:
            return None
        return len(admitted & matched if matched is not None else admitted)
    if matched is not None:
        return len(matched)
    return await get_user_store().count_identities()


async def _whitelisted_ids(access: PlatformAccess) -> set[str]:
    async with access.store.read() as session:
        return {
            str(user_id)
            for user_id in await session.scalars(select(PlatformAccessUserRow.user_id))
        }


async def _admitted_users(
    access: PlatformAccess, revision: int
) -> frozenset[str] | None:
    """Distinct users the activation preview allows or the whitelist holds, cached:
    the preview checks every user against ReBAC, too slow for each page load."""
    async with _admitted_lock:
        cached = _admitted.get(revision)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        try:
            async with asyncio.timeout(ADMITTED_TIMEOUT_SECONDS):
                preview, whitelisted = await asyncio.gather(
                    activation_preview(access), _whitelisted_ids(access)
                )
        except Exception:
            # Any failure (ReBAC, database, timeout) leaves the figure unknown, not the page broken.
            logger.warning("[KPI] admitted user count unavailable", exc_info=True)
            _admitted[revision] = (
                time.monotonic() + ADMITTED_FAILURE_TTL_SECONDS,
                None,
            )
            return None
        admitted = frozenset(
            whitelisted
            | {user.user_id for user in preview.users if user.outcome == "allowed"}
        )
        _admitted.clear()
        entry = (time.monotonic() + ADMITTED_TTL_SECONDS, admitted)
        _admitted[revision] = _admitted[preview.revision] = entry
        return admitted


async def agents_created_published(
    request: Request,
    windows: Windows,
    team_ids: Sequence[TeamId],
    user_ids: Sequence[str] | None = None,
) -> PeriodValue:
    store = get_application_container(request).get_agent_instance_store()
    current, previous = await store.count_published_created(
        [
            (windows.since, windows.until),
            (windows.previous_since, windows.since),
        ],
        [str(team_id) for team_id in team_ids],
        created_by=user_ids,
        excluded=windows.days.excluded_ranges(windows.previous_since, windows.until),
    )
    return PeriodValue(current=float(current), previous=float(previous))
