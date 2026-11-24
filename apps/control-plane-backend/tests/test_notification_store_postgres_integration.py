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

"""`NotificationStore.upsert` and `resolve` against a real PostgreSQL.

The SQLite tests cover the rules; this one covers the dialect: the
`ON CONFLICT` on the partial unique index of open rows only exists as written
on Postgres.

Run:

    docker compose -f scripts/docker-compose.postgres.yml up -d
    export FRED_PG_DSN="postgresql+asyncpg://test:test@localhost:5433/test_migrations"  # pragma: allowlist secret
    .venv/bin/pytest tests/test_notification_store_postgres_integration.py -m integration_postgres

Each test gets its own throwaway schema, dropped on teardown.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.notifications.schemas import AgentRepublishNeededPayload
from control_plane_backend.notifications.store import (
    NotificationDraft,
    NotificationStore,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_PG_DSN_ENV = "FRED_PG_DSN"
_DEFAULT_DSN = "postgresql+asyncpg://test:test@localhost:5433/test_migrations"  # pragma: allowlist secret


@pytest_asyncio.fixture
async def store() -> AsyncIterator[NotificationStore]:
    dsn = os.environ.get(_PG_DSN_ENV, _DEFAULT_DSN)
    schema = f"notifications_itest_{uuid.uuid4().hex[:8]}"

    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    await admin.dispose()

    engine: AsyncEngine = create_async_engine(
        dsn, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    try:
        yield NotificationStore(engine)
    finally:
        await engine.dispose()
        admin = create_async_engine(dsn)
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _draft(recipient: str, editor: str) -> NotificationDraft:
    return NotificationDraft(
        recipient_id=recipient,
        group_key="agent.republish_needed:e1",
        team_id="alpha",
        payload=AgentRepublishNeededPayload(
            team_id="alpha",
            agent_instance_id="agent-1",
            agent_name="Analyst",
            entry_id="e1",
            editor_name=editor,
        ),
    )


@pytest.mark.asyncio
async def test_upsert_refreshes_the_open_row_and_resolve_reopens_the_group(
    store: NotificationStore,
) -> None:
    await store.upsert([_draft("alice", "Bob"), _draft("dave", "Bob")])
    [first], _ = await store.list_page("alice", limit=50)
    assert await store.mark_seen("alice", first.id)

    # The same statement may carry the subject twice; the last payload wins.
    await store.upsert([_draft("alice", "Carol"), _draft("alice", "Erin")])
    [again], _ = await store.list_page("alice", limit=50)
    assert again.id == first.id and again.seen_at is not None
    assert again.payload["editor_name"] == "Erin"

    await store.resolve(
        ["agent.republish_needed:e1"],
        actor_uid="dave",
        actor_name="Dave",
        outcome="republished",
    )
    assert (await store.list_page("dave", limit=50))[0] == []
    [handled], _ = await store.list_page("alice", limit=50)
    assert handled.handled_by_name == "Dave"

    # A handled row leaves the open index: the next emission is a new row.
    await store.upsert([_draft("alice", "Frank")])
    rows, _ = await store.list_page("alice", limit=50)
    assert [row.handled_at is None for row in rows] == [True, False]
