# Copyright Thales 2025
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

import logging
from typing import Any, List, Optional, cast

from fred_core.sql.async_session import make_session_factory, use_session
from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.agent_models import AgentRow
from agentic_backend.core.agents.store.base_agent_store import (
    AgentNotFoundError,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)

AgentSettingsAdapter = TypeAdapter(AgentSettings)


def _is_legacy_leader_payload(payload_json: Any) -> bool:
    return isinstance(payload_json, dict) and payload_json.get("type") == "leader"


class PostgresAgentStore(BaseAgentStore):
    """
    PostgreSQL-backed agent store using JSONB (async, ORM sessions).
    """

    def __init__(self, engine: AsyncEngine):
        self._sessions = make_session_factory(engine)
        self._seed_marker_id = "__static_seeded__"

    async def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
        session: AsyncSession | None = None,
    ) -> None:
        if settings.id == self._seed_marker_id:
            raise ValueError("Invalid agent id: reserved for seed marker")

        payload = AgentSettingsAdapter.dump_python(
            settings, mode="json", exclude_none=True
        )
        if tuning is not None and "tuning" not in payload:
            try:
                payload["tuning"] = tuning.model_dump(exclude_none=True)
            except Exception:
                logger.warning(
                    "[STORE][PG][AGENTS] Could not embed tuning into AgentSettings for '%s'",
                    settings.id,
                )

        row = AgentRow(id=settings.id, name=settings.name, payload_json=payload)
        async with use_session(self._sessions, session) as s:
            await s.merge(row)

    async def load_all(
        self, session: AsyncSession | None = None
    ) -> List[AgentSettings]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (await s.execute(select(AgentRow).order_by(AgentRow.name)))
                .scalars()
                .all()
            )

        out: List[AgentSettings] = []
        for row in rows:
            if row.id == self._seed_marker_id:
                continue
            if _is_legacy_leader_payload(row.payload_json):
                logger.info(
                    "[STORE][PG][AGENTS] Ignoring deprecated leader agent '%s'.", row.id
                )
                continue
            try:
                out.append(AgentSettingsAdapter.validate_python(row.payload_json or {}))
            except Exception as e:
                logger.error("[STORE][PG][AGENTS] Failed to parse AgentSettings: %s", e)
        return out

    async def get(
        self,
        agent_id: str,
        session: AsyncSession | None = None,
    ) -> Optional[AgentSettings]:
        if agent_id == self._seed_marker_id:
            return None
        async with use_session(self._sessions, session) as s:
            row = await s.get(AgentRow, agent_id)
        if row is None:
            return None
        if _is_legacy_leader_payload(row.payload_json):
            logger.info(
                "[STORE][PG][AGENTS] Ignoring deprecated leader agent '%s'.", agent_id
            )
            return None
        try:
            return AgentSettingsAdapter.validate_python(row.payload_json or {})
        except Exception as e:
            logger.error(
                "[STORE][PG][AGENTS] Failed to parse AgentSettings for '%s': %s",
                agent_id,
                e,
            )
            return None

    async def delete(
        self,
        agent_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        if agent_id == self._seed_marker_id:
            return
        async with use_session(self._sessions, session) as s:
            result = cast(
                CursorResult,
                await s.execute(delete(AgentRow).where(AgentRow.id == agent_id)),
            )
        if result.rowcount == 0:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

    async def static_seeded(self, session: AsyncSession | None = None) -> bool:
        async with use_session(self._sessions, session) as s:
            row = await s.get(AgentRow, self._seed_marker_id)
        return row is not None

    async def mark_static_seeded(self, session: AsyncSession | None = None) -> None:
        row = AgentRow(
            id=self._seed_marker_id,
            name=self._seed_marker_id,
            payload_json={},
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)
