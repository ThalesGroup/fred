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
Offline unit test: PostgresHistoryStore.latest_exchange_id() — a HITL resume
reuses the interrupted turn's exchange_id (fred-runtime's agent_app.py,
_resolve_exchange_id) instead of minting a fresh one, so the chat UI's
per-exchange_id trace grouping can still correlate the pre-pause tool_call
with the post-resume tool_result.
"""

from __future__ import annotations

import pytest
from fred_core.history.history_schema import make_user_text
from fred_core.history.postgres_history_store import PostgresHistoryStore
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_latest_exchange_id_is_none_for_an_unknown_session(tmp_path) -> None:
    db = tmp_path / "history.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    store = PostgresHistoryStore(engine)

    assert await store.latest_exchange_id("no-such-session") is None


@pytest.mark.asyncio
async def test_latest_exchange_id_returns_the_highest_rank_rows_exchange(
    tmp_path,
) -> None:
    db = tmp_path / "history.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    store = PostgresHistoryStore(engine)

    await store.save(
        session_id="s1",
        messages=[make_user_text("s1", "exchange-1", 0, "first turn")],
        user_id="u1",
    )
    await store.save(
        session_id="s1",
        messages=[make_user_text("s1", "exchange-2", 1, "second turn")],
        user_id="u1",
    )

    assert await store.latest_exchange_id("s1") == "exchange-2"
