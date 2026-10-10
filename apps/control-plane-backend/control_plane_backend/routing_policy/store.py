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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.context import ModelBinding
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.agent_instances.store import (
    clear_recommended_chat_profiles,
)
from control_plane_backend.models.platform_model_binding_models import (
    CHAT_MODEL_CAPABILITY,
    PlatformModelBindingRow,
)
from control_plane_backend.models.routing_policy_models import TeamRoutingPolicyRow
from control_plane_backend.routing_policy.schemas import (
    RoutingPolicyVersionConflictError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredTeamRoutingPolicy:
    """One team's stored routing policy row."""

    team_id: TeamId
    version: int
    chat_default_profile_id: str | None
    disabled_model_ids: tuple[str, ...]
    reasoning_default_off_model_ids: tuple[str, ...]
    updated_by: str | None
    updated_at: datetime | None


def _json_id_list(payload: str | None) -> tuple[str, ...]:
    try:
        value = json.loads(payload or "[]")
    except ValueError:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _row_to_record(row: TeamRoutingPolicyRow) -> StoredTeamRoutingPolicy:
    return StoredTeamRoutingPolicy(
        team_id=TeamId(row.team_id),
        version=row.version,
        chat_default_profile_id=row.chat_default_profile_id,
        disabled_model_ids=_json_id_list(row.disabled_model_ids_json),
        reasoning_default_off_model_ids=_json_id_list(
            row.reasoning_default_off_model_ids_json
        ),
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
        disabled_model_ids: Sequence[str],
        reasoning_default_off_model_ids: Sequence[str],
        updated_by: str | None,
        cleared_recommendation_profile_ids: frozenset[str] = frozenset(),
        expected_version: int | None = None,
        session: AsyncSession | None = None,
    ) -> StoredTeamRoutingPolicy:
        """Replace the policy and, in the same transaction, clear the team's
        instance recommendations naming `cleared_recommendation_profile_ids`.
        `expected_version` (0 = no row yet) refuses a write over a newer one."""

        disabled = tuple(disabled_model_ids)
        reasoning_off = tuple(reasoning_default_off_model_ids)
        async with use_session(self._sessions, session) as s:
            existing = await s.get(
                TeamRoutingPolicyRow, str(team_id), with_for_update=True
            )
            actual = existing.version if existing is not None else 0
            if expected_version is not None and expected_version != actual:
                raise RoutingPolicyVersionConflictError(
                    expected=expected_version, actual=actual
                )
            if existing is None:
                version = 1
                s.add(
                    TeamRoutingPolicyRow(
                        team_id=str(team_id),
                        version=version,
                        chat_default_profile_id=chat_default_profile_id,
                        disabled_model_ids_json=json.dumps(list(disabled)),
                        reasoning_default_off_model_ids_json=json.dumps(
                            list(reasoning_off)
                        ),
                        updated_by=updated_by,
                    )
                )
            else:
                version = existing.version + 1
                existing.version = version
                existing.chat_default_profile_id = chat_default_profile_id
                existing.disabled_model_ids_json = json.dumps(list(disabled))
                existing.reasoning_default_off_model_ids_json = json.dumps(
                    list(reasoning_off)
                )
                existing.updated_by = updated_by
            if cleared_recommendation_profile_ids:
                await clear_recommended_chat_profiles(
                    s,
                    profile_ids=cleared_recommendation_profile_ids,
                    team_id=team_id,
                )
        return StoredTeamRoutingPolicy(
            team_id=team_id,
            version=version,
            chat_default_profile_id=chat_default_profile_id,
            disabled_model_ids=disabled,
            reasoning_default_off_model_ids=reasoning_off,
            updated_by=updated_by,
            updated_at=None,
        )

    async def get(
        self,
        *,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> StoredTeamRoutingPolicy | None:
        # Primary-key read: it runs on the per-turn runtime-binding call.
        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamRoutingPolicyRow, str(team_id))
        return _row_to_record(row) if row is not None else None

    async def list_team_ids_referencing_model(
        self,
        capability_id: str,
        default_profile_ids: frozenset[str] = frozenset(),
        session: AsyncSession | None = None,
    ) -> list[TeamId]:
        """Teams whose exception lists name `capability_id`, or whose default
        is one of its `default_profile_ids` (revocation cleanup)."""

        pattern = f"%{json.dumps(capability_id)}%"
        conditions = [
            TeamRoutingPolicyRow.disabled_model_ids_json.like(pattern),
            TeamRoutingPolicyRow.reasoning_default_off_model_ids_json.like(pattern),
        ]
        if default_profile_ids:
            conditions.append(
                TeamRoutingPolicyRow.chat_default_profile_id.in_(
                    sorted(default_profile_ids)
                )
            )
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(TeamRoutingPolicyRow.team_id).where(or_(*conditions))
                )
            ).all()
        return [TeamId(row[0]) for row in rows]

    async def apply_model_revocation(
        self,
        *,
        team_id: TeamId,
        capability_id: str,
        recommendation_profile_ids: frozenset[str],
        session: AsyncSession | None = None,
    ) -> list[str]:
        """Drop a model the team lost from its exception lists, its default
        (the pod default takes over) and the team's recommendations naming
        it, in one transaction. Returns the ids of the instances whose
        recommendation was cleared. No version bump: this is a platform side
        effect, not a team edit."""

        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamRoutingPolicyRow, str(team_id))
            if row is not None:
                if row.chat_default_profile_id in recommendation_profile_ids:
                    row.chat_default_profile_id = None
                disabled = _json_id_list(row.disabled_model_ids_json)
                reasoning_off = _json_id_list(row.reasoning_default_off_model_ids_json)
                if capability_id in disabled:
                    row.disabled_model_ids_json = json.dumps(
                        [i for i in disabled if i != capability_id]
                    )
                if capability_id in reasoning_off:
                    row.reasoning_default_off_model_ids_json = json.dumps(
                        [i for i in reasoning_off if i != capability_id]
                    )
            if not recommendation_profile_ids:
                return []
            return await clear_recommended_chat_profiles(
                s, profile_ids=recommendation_profile_ids, team_id=team_id
            )


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
