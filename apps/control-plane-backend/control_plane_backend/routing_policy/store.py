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

import json
import logging
from dataclasses import dataclass
from datetime import datetime

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.context import ModelBinding
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.platform_model_binding_models import (
    CHAT_MODEL_CAPABILITY,
    PlatformModelBindingRow,
)
from control_plane_backend.models.routing_policy_models import TeamRoutingPolicyRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredTeamRoutingPolicy:
    """One team's stored routing policy row."""

    team_id: TeamId
    version: int
    chat_default_profile_id: str | None
    agent_profile_overrides: dict[str, str]
    updated_by: str | None
    updated_at: datetime | None


def _row_to_record(row: TeamRoutingPolicyRow) -> StoredTeamRoutingPolicy:
    return StoredTeamRoutingPolicy(
        team_id=TeamId(row.team_id),
        version=row.version,
        chat_default_profile_id=row.chat_default_profile_id,
        agent_profile_overrides=json.loads(row.agent_profile_overrides_json or "{}"),
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class TeamRoutingPolicyStore:
    """Pure CRUD over ``team_routing_policy`` (TEAM-05, #2118).

    Same select-then-write upsert shape as ``TeamCapabilitySettingsStore`` —
    portable across the local SQLite dev DB and Postgres, no dialect-specific
    ``ON CONFLICT``. This store never checks authorization or capability
    enablement — that's the service layer's job (``service.py``), same
    separation ``team_capability_settings`` draws between its store and
    ``enablement.py``.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def upsert(
        self,
        *,
        team_id: TeamId,
        chat_default_profile_id: str | None,
        agent_profile_overrides: dict[str, str],
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredTeamRoutingPolicy:
        overrides_payload = json.dumps(agent_profile_overrides)
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(TeamRoutingPolicyRow).where(
                        TeamRoutingPolicyRow.team_id == str(team_id)
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                version = 1
                s.add(
                    TeamRoutingPolicyRow(
                        team_id=str(team_id),
                        version=version,
                        chat_default_profile_id=chat_default_profile_id,
                        agent_profile_overrides_json=overrides_payload,
                        updated_by=updated_by,
                    )
                )
            else:
                version = existing.version + 1
                existing.version = version
                existing.chat_default_profile_id = chat_default_profile_id
                existing.agent_profile_overrides_json = overrides_payload
                existing.updated_by = updated_by
        return StoredTeamRoutingPolicy(
            team_id=team_id,
            version=version,
            chat_default_profile_id=chat_default_profile_id,
            agent_profile_overrides=agent_profile_overrides,
            updated_by=updated_by,
            updated_at=None,
        )

    async def get(
        self,
        *,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> StoredTeamRoutingPolicy | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamRoutingPolicyRow).where(
                        TeamRoutingPolicyRow.team_id == str(team_id)
                    )
                )
            ).scalar_one_or_none()
        return _row_to_record(row) if row is not None else None


@dataclass(frozen=True)
class StoredPlatformModelBinding:
    """The stored platform-wide `chat` model binding row — chat-only, at most
    one row ever exists — carrying the canonical `ModelBinding` rather than a
    split provider/name/settings triple — there is exactly one typed shape
    for this data from the store boundary up."""

    binding: ModelBinding
    updated_by: str | None
    updated_at: datetime


def _binding_row_to_record(
    row: PlatformModelBindingRow,
) -> StoredPlatformModelBinding:
    """Validates the raw row through `ModelBinding` on every read — the
    fail-closed boundary: a row written before this contract tightened, or
    inserted by bypassing this store entirely, raises `ValidationError` here
    rather than handing a caller a binding that looks well-formed but isn't.
    """
    return StoredPlatformModelBinding(
        binding=ModelBinding.model_validate(
            {
                "provider": row.provider,
                "name": row.name,
                "settings": json.loads(row.settings_json or "{}"),
            }
        ),
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class PlatformModelBindingStore:
    """Pure CRUD over ``platform_model_binding`` — chat-only, at most one
    row, always keyed `model_capability="chat"`. This
    store's methods take no capability argument at all: there is structurally
    no way to reach this code path with anything but the `chat` row, on top
    of the table's own CHECK constraint.

    Same select-then-write upsert shape as ``TeamRoutingPolicyStore``, and
    the same separation of concerns: this store never checks authorization,
    that is `routing_policy/service.py`'s job. Unlike `model_reasoning`'s
    boolean column, a `(provider, name)` binding has no natural "off"
    sentinel, so `delete` (not a stored falsy value) is how an admin unsets
    the binding — an absent row means unset.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(
        self, *, session: AsyncSession | None = None
    ) -> StoredPlatformModelBinding | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(PlatformModelBindingRow).where(
                        PlatformModelBindingRow.model_capability
                        == CHAT_MODEL_CAPABILITY
                    )
                )
            ).scalar_one_or_none()
        return _binding_row_to_record(row) if row is not None else None

    async def _set_once(
        self,
        *,
        binding: ModelBinding,
        settings_payload: str,
        updated_by: str | None,
        session: AsyncSession | None,
    ) -> StoredPlatformModelBinding:
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(PlatformModelBindingRow).where(
                        PlatformModelBindingRow.model_capability
                        == CHAT_MODEL_CAPABILITY
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                row = PlatformModelBindingRow(
                    model_capability=CHAT_MODEL_CAPABILITY,
                    provider=binding.provider,
                    name=binding.name,
                    settings_json=settings_payload,
                    updated_by=updated_by,
                )
                s.add(row)
            else:
                row = existing
                row.provider = binding.provider
                row.name = binding.name
                row.settings_json = settings_payload
                row.updated_by = updated_by
            # Flush so the Python-side `default`/`onupdate` (utcnow)
            # callables populate `row.updated_at` before this method
            # returns it — the commit at `use_session`'s exit alone
            # wouldn't hand the value back to this local variable.
            await s.flush()
            updated_at = row.updated_at
        return StoredPlatformModelBinding(
            binding=binding,
            updated_by=updated_by,
            updated_at=updated_at,
        )

    async def set(
        self,
        *,
        binding: ModelBinding,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredPlatformModelBinding:
        """Persists only a validated `ModelBinding` — `binding.settings` is
        already `ModelBindingSettings`, so the only settings-to-JSON
        conversion in this path is `model_dump(mode="json",
        exclude_none=True)`, never a hand-rolled dict.

        `_set_once`'s select-then-insert races a concurrent first-ever
        `set()` (two admins, or a client retrying a timed-out PUT) landing on
        the same `model_capability="chat"` primary key: both see no row and
        both attempt an insert, and the DB's own PK constraint lets only one
        commit through. Retried once here, only when this call owns its own
        transaction (`session is None` — the only shape any caller uses
        today): the loser's own `use_session` block rolls back cleanly on
        `IntegrityError`, and a fresh transaction re-reads the row the
        winner just committed and updates it instead, so the loser still
        gets a normal `StoredPlatformModelBinding` back rather than a bare
        500 for what should be an ordinary upsert.
        """

        settings_payload = json.dumps(
            binding.settings.model_dump(mode="json", exclude_none=True)
        )
        try:
            return await self._set_once(
                binding=binding,
                settings_payload=settings_payload,
                updated_by=updated_by,
                session=session,
            )
        except IntegrityError:
            if session is not None:
                raise
            return await self._set_once(
                binding=binding,
                settings_payload=settings_payload,
                updated_by=updated_by,
                session=session,
            )

    async def delete(
        self,
        *,
        session: AsyncSession | None = None,
    ) -> bool:
        """Unset the binding. Returns whether a row actually existed to
        delete — "unset" must be representable as row-absence, since
        `ModelBinding` has no natural off-sentinel."""

        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(PlatformModelBindingRow).where(
                        PlatformModelBindingRow.model_capability
                        == CHAT_MODEL_CAPABILITY
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                return False
            await s.delete(existing)
        return True
