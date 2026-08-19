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

"""#2170: two backends sharing one database must not see each other's tasks.

control-plane and knowledge-flow both migrate the `fred` database. When they
mapped one shared `task_run`, each backend's `GET /tasks` returned the other's
rows and the Activity page — which queries every backend and merges client-side
— listed every task twice. The fix is a prefixed pair per owner, so these tests
use the same two-owners-one-engine setup the product has.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

from fred_core.tasks.orm_models import (
    TaskEventLogColumns,
    TaskRunColumns,
    TaskTables,
    single_active_migration_index_name,
    task_event_log_table_args,
    task_run_table_args,
)
from fred_core.tasks.store import TaskStore


class _Base(DeclarativeBase):
    pass


def _declare(prefix: str) -> TaskTables:
    run, log = f"{prefix}task_run", f"{prefix}task_event_log"
    run_cls = type(
        f"{prefix}TaskRunRow",
        (TaskRunColumns, _Base),
        {"__tablename__": run, "__table_args__": task_run_table_args(run)},
    )
    log_cls = type(
        f"{prefix}TaskEventLogRow",
        (TaskEventLogColumns, _Base),
        {"__tablename__": log, "__table_args__": task_event_log_table_args(log)},
    )
    return TaskTables(run=run_cls, event_log=log_cls)


_ALPHA = _declare("alpha_")
_BETA = _declare("beta_")


@pytest.mark.asyncio
async def test_each_owner_only_lists_its_own_tasks(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'shared.sqlite3'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)

        alpha = TaskStore(engine, _ALPHA)
        beta = TaskStore(engine, _BETA)
        await alpha.create(task_id="a-1", kind="migration", created_by="u")
        await beta.create(task_id="b-1", kind="ingestion", created_by="u")

        assert [t.task_id for t in await alpha.list_tasks()] == ["a-1"]
        assert [t.task_id for t in await beta.list_tasks()] == ["b-1"]
        # Cross-reads miss entirely rather than returning a foreign row.
        assert await alpha.get_run("b-1") is None
        assert await beta.get_run("a-1") is None
    finally:
        await engine.dispose()


def test_owners_share_no_index_name() -> None:
    """Postgres scopes index names per schema, so two owners in one database
    cannot both name an index `ix_task_run_kind`. Every index must carry its
    table name — this fails the moment someone adds a hardcoded one."""
    names = {}
    for label, tables in (("alpha", _ALPHA), ("beta", _BETA)):
        names[label] = {
            ix.name
            for model in (tables.run, tables.event_log)
            for ix in model.__table__.indexes  # type: ignore[attr-defined]
        } | {
            c.name
            for model in (tables.run, tables.event_log)
            for c in model.__table__.constraints  # type: ignore[attr-defined]
            if c.name is not None
        }
    assert names["alpha"] and names["beta"]
    assert not names["alpha"] & names["beta"]


def test_exclusion_index_name_tracks_the_table() -> None:
    """`import_export/api.py` recognises a concurrent-migration 409 by this exact
    string, derived from the same helper rather than restated — so the helper and
    the index it names must agree for whatever table an owner picks."""
    assert single_active_migration_index_name("alpha_task_run") in {
        ix.name
        for ix in _ALPHA.run.__table__.indexes  # type: ignore[attr-defined]
    }
