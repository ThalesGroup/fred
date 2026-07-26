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

"""
Offline unit test: PostgresHistoryStore.save() emits persist_sql_ms /
persist_pool_wait_ms (TURN-01 — these names existed in the KPI summary
formatter but were emitted by no code site at all).
"""

from __future__ import annotations

import pytest
from fred_core.history.history_schema import make_user_text
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from sqlalchemy.ext.asyncio import create_async_engine


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)


@pytest.mark.asyncio
async def test_save_emits_persist_sql_and_pool_wait_metrics(tmp_path) -> None:
    db = tmp_path / "history.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    writer = _RecordingKPIWriter()
    store = PostgresHistoryStore(engine, kpi=writer)

    await store.save(
        session_id="s1",
        messages=[make_user_text("s1", "exchange-1", 0, "hello")],
        user_id="u1",
    )

    names = {e["name"] for e in writer.emitted}
    assert {"persist_sql_ms", "persist_pool_wait_ms"} <= names
    for event in writer.emitted:
        assert event["dims"] == {"store": "history", "op": "save"}
        assert event["value"] >= 0.0


@pytest.mark.asyncio
async def test_save_is_silent_without_a_kpi_writer(tmp_path) -> None:
    db = tmp_path / "history.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    store = PostgresHistoryStore(engine)  # kpi=None default

    await store.save(
        session_id="s1",
        messages=[make_user_text("s1", "exchange-1", 0, "hello")],
        user_id="u1",
    )
