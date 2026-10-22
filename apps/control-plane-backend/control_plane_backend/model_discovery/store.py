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
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.context import ModelBinding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.model_discovery_models import (
    ModelDiscoverySourceStateRow,
    PlatformModelFallbackRow,
)


@dataclass(frozen=True)
class StoredDiscoverySourceState:
    source_id: str
    yaml_url: str
    override_url: str | None
    active_url: str | None
    inventory: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    new_ids: list[str]
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None

    @property
    def effective_url(self) -> str:
        return self.override_url or self.yaml_url


def _source_record(row: ModelDiscoverySourceStateRow) -> StoredDiscoverySourceState:
    return StoredDiscoverySourceState(
        source_id=row.source_id,
        yaml_url=row.yaml_url,
        override_url=row.override_url,
        active_url=row.active_url,
        inventory=json.loads(row.inventory_json),
        removed=json.loads(row.removed_json),
        new_ids=json.loads(row.new_ids_json),
        last_success_at=row.last_success_at,
        last_attempt_at=row.last_attempt_at,
        last_error=row.last_error,
    )


class ModelDiscoveryStateStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def list_all(
        self, *, session: AsyncSession | None = None
    ) -> list[StoredDiscoverySourceState]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (await s.execute(select(ModelDiscoverySourceStateRow))).scalars().all()
            )
            return [_source_record(row) for row in rows]

    async def get(
        self, source_id: str, *, session: AsyncSession | None = None
    ) -> StoredDiscoverySourceState | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(ModelDiscoverySourceStateRow, source_id)
            return _source_record(row) if row is not None else None

    async def save_success(
        self,
        *,
        source_id: str,
        yaml_url: str,
        effective_url: str,
        inventory: list[dict[str, Any]],
        override_update: bool = False,
        override_url: str | None = None,
        expected_override_url: str | None = None,
        updated_by: str | None = None,
    ) -> StoredDiscoverySourceState | None:
        async with use_session(self._sessions) as s:
            row = await s.get(
                ModelDiscoverySourceStateRow, source_id, with_for_update=True
            )
            if row is None:
                row = ModelDiscoverySourceStateRow(
                    source_id=source_id,
                    yaml_url=yaml_url,
                    override_url=None,
                    inventory_json="[]",
                    removed_json="[]",
                    new_ids_json="[]",
                )
                s.add(row)
            if override_update and row.override_url != expected_override_url:
                return None
            if not override_update and (row.override_url or yaml_url) != effective_url:
                return None
            if override_update:
                row.override_url = override_url
                row.updated_by = updated_by
            previous = {item["id"]: item for item in json.loads(row.inventory_json)}
            current = {item["id"]: item for item in inventory}
            removed = {item["id"]: item for item in json.loads(row.removed_json)}
            previously_removed_ids = set(removed)
            removed.update(
                {key: item for key, item in previous.items() if key not in current}
            )
            for key in current:
                removed.pop(key, None)
            row.yaml_url = yaml_url
            row.active_url = effective_url
            row.inventory_json = json.dumps(list(current.values()))
            row.removed_json = json.dumps(list(removed.values()))
            row.new_ids_json = json.dumps(
                sorted(current.keys() - previous.keys() - previously_removed_ids)
            )
            row.last_attempt_at = utcnow()
            row.last_success_at = row.last_attempt_at
            row.last_error = None
            return _source_record(row)

    async def record_failure(
        self, *, source_id: str, yaml_url: str, error: str
    ) -> StoredDiscoverySourceState:
        async with use_session(self._sessions) as s:
            row = await s.get(
                ModelDiscoverySourceStateRow, source_id, with_for_update=True
            )
            if row is None:
                row = ModelDiscoverySourceStateRow(
                    source_id=source_id,
                    yaml_url=yaml_url,
                    override_url=None,
                    inventory_json="[]",
                    removed_json="[]",
                    new_ids_json="[]",
                )
                s.add(row)
            row.last_attempt_at = utcnow()
            row.last_error = error[:1000]
            return _source_record(row)


class PlatformModelFallbackStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(self, *, session: AsyncSession | None = None) -> ModelBinding | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(PlatformModelFallbackRow, "chat")
            if row is None:
                return None
            return ModelBinding.model_validate(
                {
                    "provider": row.provider,
                    "name": row.name,
                    "settings": json.loads(row.settings_json),
                }
            )

    async def set(self, binding: ModelBinding, *, updated_by: str | None) -> None:
        async with use_session(self._sessions) as s:
            row = await s.get(PlatformModelFallbackRow, "chat")
            if row is None:
                s.add(
                    PlatformModelFallbackRow(
                        model_capability="chat",
                        provider=binding.provider,
                        name=binding.name,
                        settings_json=json.dumps(
                            binding.settings.model_dump(mode="json", exclude_none=True)
                        ),
                        updated_by=updated_by,
                    )
                )
            else:
                row.provider = binding.provider
                row.name = binding.name
                row.settings_json = json.dumps(
                    binding.settings.model_dump(mode="json", exclude_none=True)
                )
                row.updated_by = updated_by

    async def delete(self) -> None:
        async with use_session(self._sessions) as s:
            row = await s.get(PlatformModelFallbackRow, "chat")
            if row is not None:
                await s.delete(row)
