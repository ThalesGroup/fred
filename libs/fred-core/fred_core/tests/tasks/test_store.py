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

"""`TaskStore.get_task` — one task's summary, projected exactly as `list_tasks`."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from fred_core.common import PostgresStoreConfig
from fred_core.sql import create_async_engine_from_config
from fred_core.tasks.store import TaskStore
from fred_core.tests.tasks.task_tables import TASK_TABLES, Base


@pytest_asyncio.fixture
async def build_store():
    """Same pattern as test_reconcile.py's `build_service` — a fresh aiosqlite
    engine per test, disposed on teardown."""
    engines: list[Any] = []

    async def _build(tmp_path) -> TaskStore:
        engine = create_async_engine_from_config(
            PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
        )
        engines.append(engine)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return TaskStore(engine, TASK_TABLES)

    yield _build

    for engine in engines:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_task_projects_like_list_tasks(tmp_path, build_store) -> None:
    store = await build_store(tmp_path)
    await store.create(task_id="t1", kind="ingestion", created_by="u1")

    (listed,) = await store.list_tasks()

    assert await store.get_task("t1") == listed


@pytest.mark.asyncio
async def test_get_task_of_unknown_id_is_none(tmp_path, build_store) -> None:
    store = await build_store(tmp_path)

    assert await store.get_task("missing") is None
