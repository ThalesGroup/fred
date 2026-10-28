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

"""Workbook spec store: SQL (in-memory SQLite) and memory implementations."""

from __future__ import annotations

import asyncio

import pytest
from fred_capability_spreadsheet.store import (
    MemoryWorkbookSpecStore,
    SpreadsheetBase,
    SqlWorkbookSpecStore,
    StoredWorkbook,
    WorkbookSpecStore,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


async def _sql_store() -> SqlWorkbookSpecStore:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(SpreadsheetBase.metadata.create_all)
    return SqlWorkbookSpecStore(async_sessionmaker(engine, expire_on_commit=False))


async def _exercise(store: WorkbookSpecStore) -> None:
    assert await store.get("s", "a") is None
    first = StoredWorkbook("w1", 1, "Budget", '{"sheets": []}')
    await store.put("s", "a", first)
    assert await store.get("s", "a") == first
    second = StoredWorkbook("w1", 2, "Budget", '{"sheets": [1]}')
    await store.put("s", "a", second)
    assert await store.get("s", "a") == second
    # Keyed by conversation and agent: another agent has its own base.
    assert await store.get("s", "b") is None
    await store.clear("s", "a")
    assert await store.get("s", "a") is None


@pytest.mark.parametrize("kind", ["sql", "memory"])
def test_store_round_trip(kind):
    async def run() -> None:
        store = await _sql_store() if kind == "sql" else MemoryWorkbookSpecStore()
        await _exercise(store)

    asyncio.run(run())
