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
from typing import NamedTuple

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.model_reasoning_models import ModelReasoningRow

logger = logging.getLogger(__name__)


class ModelReasoningDisplay(NamedTuple):
    """One enabled model's toggle-time display snapshot.

    Both fields are display only and both are `None`-able: `effort` is the
    level a reasoning turn runs with (the pod always applies the live
    `settings.reasoning_effort`, never this copy), `display_name` is the
    composer chip's model label. One tuple rather than two parallel dicts so
    the send path stays one query and a model cannot be paired with another
    model's label.
    """

    effort: str | None
    display_name: str | None


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
        default_effort: str | None = None,
        display_name: str | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        # `default_effort` and `display_name` are display SNAPSHOTs of the
        # model's ops-authored `settings.reasoning_effort` and
        # `model_display_name`, taken by the service at toggle time so the
        # send path never fetches the catalog; the pod always applies the live
        # settings value. NULL = no effort key on the thinking profile / no
        # display name authored in `models_catalog.yaml`.
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
                        default_effort=default_effort,
                        display_name=display_name,
                        updated_by=updated_by,
                    )
                )
            else:
                existing.reasoning_enabled = reasoning_enabled
                existing.default_effort = default_effort
                existing.display_name = display_name
                existing.updated_by = updated_by
        return reasoning_enabled

    async def list_enabled_model_ids(
        self, *, session: AsyncSession | None = None
    ) -> set[str]:
        """Every model capability id whose reasoning is switched ON.

        One row per model that an admin has ever touched, and only the enabled
        ones come back. Read at session prep and also on every managed turn
        from `get_runtime_binding_for_team` — the pod does not trust a
        client-forwarded copy of this value, so it needs a fresh answer each
        turn rather than once per session. A single indexed boolean-column
        read; cheap enough to not need its own cache.
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

    async def list_enabled_display_snapshots(
        self, *, session: AsyncSession | None = None
    ) -> dict[str, ModelReasoningDisplay]:
        """Enabled model ids → their toggle-time display snapshot.

        Same single indexed read as `list_enabled_model_ids`, two extra
        columns — feeds the composer control's `params.effort` and
        `params.display_name` at session prep. Either field being `None` is
        normal, not an error: no effort key on the thinking profile (the menu
        falls back to a generic On label), no `model_display_name` authored
        (the frontend derives a label from the capability id)."""

        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(
                        ModelReasoningRow.model_capability_id,
                        ModelReasoningRow.default_effort,
                        ModelReasoningRow.display_name,
                    ).where(ModelReasoningRow.reasoning_enabled.is_(True))
                )
            ).all()
        return {
            model_id: ModelReasoningDisplay(effort=effort, display_name=display_name)
            for model_id, effort, display_name in rows
        }
