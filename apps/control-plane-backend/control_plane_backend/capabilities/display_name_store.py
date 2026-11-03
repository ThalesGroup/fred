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

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.model_display_name_models import (
    ModelDisplayNameOverrideRow,
)


class ModelDisplayNameOverrideStore:
    """Persist operator labels independently of pod catalog refreshes."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def list_all(self, *, session: AsyncSession | None = None) -> dict[str, str]:
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(
                        ModelDisplayNameOverrideRow.model_capability_id,
                        ModelDisplayNameOverrideRow.display_name,
                    )
                )
            ).all()
        return {model_id: display_name for model_id, display_name in rows}

    async def set(
        self,
        *,
        model_capability_id: str,
        display_name: str | None,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            if display_name is None:
                await s.execute(
                    delete(ModelDisplayNameOverrideRow).where(
                        ModelDisplayNameOverrideRow.model_capability_id
                        == model_capability_id
                    )
                )
                return
            existing = await s.get(ModelDisplayNameOverrideRow, model_capability_id)
            if existing is None:
                s.add(
                    ModelDisplayNameOverrideRow(
                        model_capability_id=model_capability_id,
                        display_name=display_name,
                        updated_by=updated_by,
                    )
                )
            else:
                existing.display_name = display_name
                existing.updated_by = updated_by
