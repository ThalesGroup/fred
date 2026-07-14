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

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fred_core.sql.async_session import make_session_factory
from fred_core.sql.base_sql import advisory_lock_key
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.bootstrap_models import (
    SINGLETON_ID,
    PlatformBootstrapRow,
)

ADVISORY_LOCK_KEY = "platform_bootstrap"


class PlatformBootstrapStore:
    """Durable "root bootstrap has completed" marker (AUTHZ-07, RFC Part 8 §42.3).

    Why this exists: the root-bootstrap endpoint must stay permanently inert
    once used, even if every `platform_admin` relation is later removed from
    OpenFGA. A live `lookup_subjects` count cannot provide that guarantee —
    that is precisely the bug shape the reverted `§24.7` escalation had
    (a condition true only "for now" treated as a standing safety property).
    This store is the one place that guarantee is anchored: a single durable
    row, never deleted by any product code path.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @asynccontextmanager
    async def advisory_lock(self) -> AsyncIterator[None]:
        """Hold a Postgres transaction-scoped advisory lock around the
        bootstrap check-then-write window — same primitive and rationale as
        `TeamMetadataStore.advisory_lock` (`rescue_team_admin`'s pattern):
        OpenFGA cannot express a conditional write, so concurrent callers must
        be serialized outside it. No-op on non-Postgres dialects (tests).
        """
        async with self._sessions() as s, s.begin():
            if self._engine.dialect.name == "postgresql":
                await s.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": advisory_lock_key(ADVISORY_LOCK_KEY)},
                )
            yield

    async def is_completed(self) -> bool:
        async with self._sessions() as s:
            row = await s.get(PlatformBootstrapRow, SINGLETON_ID)
        return row is not None

    async def mark_completed(self, completed_by: str) -> None:
        """Persist the durable marker. Call this *after* the `platform_admin`
        OpenFGA tuple write has succeeded (§42.3, revised): `add_relation` is
        idempotent, so if the process crashes between the two writes, a retry
        safely re-applies the same tuple and then closes the marker — no
        break-glass procedure (§41) needed for that case anymore.
        """
        async with self._sessions() as s, s.begin():
            s.add(
                PlatformBootstrapRow(
                    id=SINGLETON_ID,
                    completed_at=datetime.now(timezone.utc),
                    completed_by=completed_by,
                )
            )
