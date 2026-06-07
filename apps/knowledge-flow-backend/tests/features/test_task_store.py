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

"""Unit tests for TaskStore — replay fidelity including target/owner round-trip."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.models import Base as CoreBase
from fred_core.tasks.models import IngestionTaskEvent, TaskState, TaskTarget
from fred_core.tasks.store import TaskNotFoundError, TaskStore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    import fred_core.tasks.orm_models  # noqa: F401 — registers ORM models with CoreBase

    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_task_store_replay_preserves_target_and_owner(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_target.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="t1", kind="ingestion", created_by="user-42")

        event = IngestionTaskEvent(
            task_id="t1",
            state=TaskState.running,
            seq=0,
            timestamp=_NOW,
            target=TaskTarget(type="document", id="doc-abc", label="report.pdf"),
            owner="user-42",
        )
        await store.record_event(event)

        replayed = await store.replay_events("t1", after_seq=-1)
        assert len(replayed) == 1
        assert replayed[0].target is not None
        assert replayed[0].target.type == "document"
        assert replayed[0].target.id == "doc-abc"
        assert replayed[0].target.label == "report.pdf"
        assert replayed[0].owner == "user-42"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_replay_target_none_when_not_set(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_no_target.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="t2", kind="ingestion", created_by=None)

        event = IngestionTaskEvent(
            task_id="t2",
            state=TaskState.running,
            seq=0,
            timestamp=_NOW,
        )
        await store.record_event(event)

        replayed = await store.replay_events("t2", after_seq=-1)
        assert len(replayed) == 1
        assert replayed[0].target is None
        assert replayed[0].owner is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_record_event_raises_for_unknown_task(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_unknown.sqlite3")
    try:
        store = TaskStore(engine)
        event = IngestionTaskEvent(task_id="ghost", state=TaskState.running, seq=0, timestamp=_NOW)
        with pytest.raises(TaskNotFoundError):
            await store.record_event(event)
    finally:
        await engine.dispose()
