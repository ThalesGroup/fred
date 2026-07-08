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

"""Audit-field (created_by / updated_by) behavior of the agent store and service.

Offline: uses in-memory async SQLite for the store and mocks for the service
collaborators. The audit columns are server-authoritative: stamped from the
acting user's uid, never from client-sent payload values, and never clobbered
by system writes (startup/seed paths save without an actor).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import KeycloakUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from agentic_backend.common.structures import Agent
from agentic_backend.core.agents import agent_service as agent_service_module
from agentic_backend.core.agents.agent_service import AgentService
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.agent_models import AgentRow
from agentic_backend.core.agents.store.postgres_agent_store import PostgresAgentStore


async def _make_store() -> PostgresAgentStore:
    # Real in-memory async SQLite: exercises the actual insert/update SQL,
    # fully offline (no Postgres).
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(AgentRow.metadata.create_all)
    return PostgresAgentStore(engine=engine)


def _settings(agent_id: str = "a-1", **overrides) -> Agent:
    return Agent(id=agent_id, name="Rico", enabled=True, **overrides)


def _tuning() -> AgentTuning:
    return AgentTuning(role="Test role", description="Test description", fields=[])


def test_save_with_actor_stamps_created_by_and_updated_by():
    async def _run() -> None:
        store = await _make_store()
        await store.save(_settings(), _tuning(), actor_uid="u-creator")

        loaded = await store.get("a-1")
        assert loaded is not None
        assert loaded.created_by == "u-creator"
        assert loaded.updated_by == "u-creator"
        # Timestamps come from the row columns (server defaults).
        assert loaded.created_at is not None
        assert loaded.updated_at is not None

    asyncio.run(_run())


def test_update_with_other_actor_changes_updated_by_and_preserves_created_by():
    async def _run() -> None:
        store = await _make_store()
        await store.save(_settings(), _tuning(), actor_uid="u-creator")
        await store.save(
            _settings().model_copy(update={"name": "Rico v2"}),
            _tuning(),
            actor_uid="u-editor",
        )

        loaded = await store.get("a-1")
        assert loaded is not None
        assert loaded.name == "Rico v2"
        assert loaded.created_by == "u-creator"
        assert loaded.updated_by == "u-editor"

    asyncio.run(_run())


def test_save_without_actor_preserves_audit_columns():
    async def _run() -> None:
        store = await _make_store()
        await store.save(_settings(), _tuning(), actor_uid="u-creator")
        # System write (e.g. startup reconciliation): no actor.
        await store.save(_settings().model_copy(update={"name": "Seeded"}), _tuning())

        loaded = await store.get("a-1")
        assert loaded is not None
        assert loaded.name == "Seeded"
        assert loaded.created_by == "u-creator"
        assert loaded.updated_by == "u-creator"

    asyncio.run(_run())


def test_seed_insert_without_actor_leaves_audit_columns_null():
    async def _run() -> None:
        store = await _make_store()
        await store.save(_settings(), _tuning())

        loaded = await store.get("a-1")
        assert loaded is not None
        assert loaded.created_by is None
        assert loaded.updated_by is None

    asyncio.run(_run())


def test_client_sent_audit_values_are_ignored_and_stripped_from_payload():
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(AgentRow.metadata.create_all)
        store = PostgresAgentStore(engine=engine)

        # A client round-tripping the full agent payload could send stale/forged
        # audit values: they must not reach the columns nor the payload blob.
        forged = _settings(created_by="u-forged", updated_by="u-forged")
        await store.save(forged, _tuning(), actor_uid="u-real")

        loaded = await store.get("a-1")
        assert loaded is not None
        assert loaded.created_by == "u-real"
        assert loaded.updated_by == "u-real"

        async with engine.connect() as conn:
            payload = (await conn.execute(select(AgentRow.payload_json))).scalar_one()
        assert payload is not None
        for key in ("created_by", "updated_by", "created_at", "updated_at"):
            assert key not in payload

    asyncio.run(_run())


# ---------------- Service-level stamping ----------------


def _build_user(uid: str = "u-1") -> KeycloakUser:
    return KeycloakUser(
        uid=uid,
        username="alice",
        roles=["user"],
        email="alice@example.com",
        groups=[],
    )


def _build_service(monkeypatch, *, store, rebac, manager) -> AgentService:
    monkeypatch.setattr(agent_service_module, "get_agent_store", lambda: store)
    monkeypatch.setattr(agent_service_module, "get_rebac_engine", lambda: rebac)
    return AgentService(agent_manager=manager)


@pytest.mark.asyncio
async def test_create_v2_agent_stamps_actor(monkeypatch):
    rebac = SimpleNamespace(
        enabled=True,
        add_user_relation=AsyncMock(),
    )
    manager = SimpleNamespace(create_dynamic_agent=AsyncMock())

    service = _build_service(
        monkeypatch, store=SimpleNamespace(), rebac=rebac, manager=manager
    )

    created = await service.create_v2_agent(_build_user("u-42"), "Rico")

    assert created.created_by == "u-42"
    assert created.updated_by == "u-42"
    assert manager.create_dynamic_agent.await_args.kwargs["actor_uid"] == "u-42"


@pytest.mark.asyncio
async def test_update_agent_stamps_actor(monkeypatch):
    persisted = Agent(id="a-3", name="Tessa", enabled=True)
    rebac = SimpleNamespace(
        enabled=True,
        check_user_permission_or_raise=AsyncMock(),
        lookup_subjects=AsyncMock(return_value=[]),
    )
    manager = SimpleNamespace(
        get_agent_settings=AsyncMock(return_value=persisted),
        update_agent=AsyncMock(return_value=True),
    )

    service = _build_service(
        monkeypatch, store=SimpleNamespace(), rebac=rebac, manager=manager
    )

    await service.update_agent(_build_user("u-editor"), persisted)

    assert manager.update_agent.await_args.kwargs["actor_uid"] == "u-editor"
