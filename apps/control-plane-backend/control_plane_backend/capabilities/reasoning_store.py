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

import logging

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.model_reasoning_models import ModelReasoningRow

logger = logging.getLogger(__name__)


class ModelReasoningStore:
    """Pure CRUD over ``model_reasoning`` (REASON-01,
    `MODEL-REASONING-ENABLEMENT-RFC.md` §5.5).

    Same select-then-write upsert shape as ``TeamRoutingPolicyStore`` —
    portable across the local SQLite dev DB and Postgres, no dialect-specific
    ``ON CONFLICT``. Authorization and "is this model even thinking-capable"
    are the service layer's job, never this store's.

    The read side deliberately returns only the ENABLED ids: an absent row and
    a stored ``false`` mean exactly the same thing (§5.6, off by default), so
    every caller wants the same one set and none of them should have to
    re-derive it.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def set_enabled(
        self,
        *,
        model_capability_id: str,
        reasoning_enabled: bool,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> bool:
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(ModelReasoningRow).where(
                        ModelReasoningRow.model_capability_id == model_capability_id
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(
                    ModelReasoningRow(
                        model_capability_id=model_capability_id,
                        reasoning_enabled=reasoning_enabled,
                        updated_by=updated_by,
                    )
                )
            else:
                existing.reasoning_enabled = reasoning_enabled
                existing.updated_by = updated_by
        return reasoning_enabled

    async def list_enabled_model_ids(
        self, *, session: AsyncSession | None = None
    ) -> set[str]:
        """Every model capability id whose reasoning is switched ON.

        One row per model that an admin has ever touched, and only the enabled
        ones come back — this is read once per session prep (§5.5, the
        `ExecutionPreparation` snapshot), never per turn.
        """

        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(ModelReasoningRow.model_capability_id).where(
                        ModelReasoningRow.reasoning_enabled.is_(True)
                    )
                )
            ).scalars()
            return set(rows)
