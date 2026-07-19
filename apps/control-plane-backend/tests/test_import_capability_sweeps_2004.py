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

"""GitHub #2004 item 3 — the Kea/Swift bulk import must never leave an agent
instance with the `selected_capability_ids=None` bypass sentinel #1980 closed
for the live enroll/update path.

`run_import` writes `agent_instance` rows directly (kea classification /
swift-native passthrough), never through `enroll_agent_instance` /
`_apply_capability_selection`. These tests prove the new Phase 6 wiring: the
two compatibility sweeps (`materialize_default_capability_selections`,
`grant_existing_teams_served_templates`) run once per import, scoped to
exactly the teams that import just touched — not the whole platform, and not
at all when there is nothing to fix up or no `product_deps` was supplied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.import_export import importer as importer_module
from control_plane_backend.import_export.bundle import KBundle
from control_plane_backend.import_export.importer import run_import
from control_plane_backend.models.base import Base as CPBase
from fred_core.models import Base as CoreBase
from fred_core.scheduler import SchedulerBackend
from fred_core.tasks.models import StartMigrationRequest
from fred_core.tasks.service import TaskService
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class _FakeManifest:
    def __init__(self, source_platform: str) -> None:
        self.source_platform = source_platform
        self.content_keys: list[str] = []


class _FakeBundle:
    """Duck-types the `KBundle` surface `run_import` actually calls, without
    the real zip/manifest machinery — same spirit as the fakes used in
    `test_capability_selection_1974.py`."""

    def __init__(
        self,
        *,
        source_platform: str = "swift",
        agent_instance_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.manifest = _FakeManifest(source_platform)
        self._tables: dict[str, list[dict[str, Any]]] = {
            "agent_instance": agent_instance_rows or [],
            "agent": [],
            "tag": [],
            "metadata": [],
            "team_metadata": [],
        }

    def iter_table(self, table: str):
        return iter(self._tables.get(table, []))

    def openfga_tuples(self) -> list[dict[str, Any]]:
        return []

    def demo_users(self) -> list[Any]:
        return []

    def close(self) -> None:
        pass


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import fred_core.tasks.orm_models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


async def _run(
    engine: AsyncEngine, bundle: _FakeBundle, *, product_deps: Any = None
) -> None:
    task_service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
    start = await task_service.start(StartMigrationRequest(), created_by="tester")
    await run_import(
        bundle=cast(KBundle, bundle),
        import_id="imp-2004",
        task_id=start.task_id,
        task_service=task_service,
        engine=engine,
        agent_instance_store=AgentInstanceStore(engine),
        product_deps=product_deps,
    )


def _patch_sweeps(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"materialize": [], "grant": []}

    class _Summary:
        materialized = 0
        grants_written = 0

    async def _fake_materialize(deps, *, dry_run=False, team_ids=None):
        calls["materialize"].append(team_ids)
        return _Summary()

    async def _fake_grant(deps, *, dry_run=False, team_ids=None):
        calls["grant"].append(team_ids)
        return _Summary()

    monkeypatch.setattr(
        importer_module, "materialize_default_capability_selections", _fake_materialize
    )
    monkeypatch.setattr(
        importer_module, "grant_existing_teams_served_templates", _fake_grant
    )
    return calls


@pytest.mark.asyncio
async def test_import_runs_capability_sweeps_scoped_to_imported_teams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_sweeps(monkeypatch)
    engine = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        bundle = _FakeBundle(
            agent_instance_rows=[
                {
                    "agent_instance_id": "ai-1",
                    "team_id": "team-x",
                    "template_id": "runtime-a:sql_expert",
                    "source_runtime_id": "runtime-a",
                    "source_agent_id": "sql_expert",
                    "display_name": "SQL Expert",
                    "enabled": True,
                    "tuning_json": None,
                }
            ]
        )
        await _run(engine, bundle, product_deps=object())
    finally:
        await engine.dispose()

    assert calls["materialize"] == [{"team-x"}]
    assert calls["grant"] == [{"team-x"}]


@pytest.mark.asyncio
async def test_import_skips_sweeps_when_no_agents_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_sweeps(monkeypatch)
    engine = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        await _run(engine, _FakeBundle(agent_instance_rows=[]), product_deps=object())
    finally:
        await engine.dispose()

    assert calls["materialize"] == []
    assert calls["grant"] == []


@pytest.mark.asyncio
async def test_import_skips_sweeps_when_no_product_deps_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`product_deps` stays optional — callers that don't supply it (existing
    tests, any future non-route caller) must not error, just skip Phase 6."""

    calls = _patch_sweeps(monkeypatch)
    engine = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        bundle = _FakeBundle(
            agent_instance_rows=[
                {
                    "agent_instance_id": "ai-1",
                    "team_id": "team-x",
                    "template_id": "runtime-a:sql_expert",
                    "source_runtime_id": "runtime-a",
                    "source_agent_id": "sql_expert",
                    "display_name": "SQL Expert",
                    "enabled": True,
                    "tuning_json": None,
                }
            ]
        )
        await _run(engine, bundle, product_deps=None)
    finally:
        await engine.dispose()

    assert calls["materialize"] == []
    assert calls["grant"] == []
