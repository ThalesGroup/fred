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

"""AUTHZ-07 Step 3 — platform import task observability.

Before this change: `import_export/api.py` threw away the `MigrationReport`
`run_import()` returned and emitted an empty terminal `succeeded` event with no
target beyond a raw UUID — a partial reconciliation (silently skipped grants)
was indistinguishable from full success once the task list was reloaded.

This file proves, through the real ASGI route (`create_app()` + `httpx`
`ASGITransport`, same pattern as `test_main.py`), that:
- the task is created with a canonical, durable `TaskTarget`
  (`type="platform_import"`, `id=import_id`, a real label — never a bare
  UUID), independent of whether the operator supplied a label;
- the terminal `succeeded` event carries the full structured `MigrationResult`
  (via `MigrationDetail.result`), and a non-empty `warnings` list survives a
  reload without the task ever reading as a different state;
- an exception during import lands `failed` with the error message and the
  same canonical target — never `succeeded`.

`run_import`/`open_bundle` are monkeypatched at the `import_export.api` call
site so these tests exercise only the API layer's own responsibility (target
construction, event building, persistence/read-back) — `run_import`'s own
provisioning logic is covered exhaustively in `test_import_export_users.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.import_export import api as import_export_api
from control_plane_backend.import_export.importer import (
    MigrationReport,
    to_migration_result,
)
from control_plane_backend.main import create_app
from fred_core import KeycloakUser, get_current_user
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def _make_app(uid: str) -> Any:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid=uid, username=uid, roles=[]
    )
    return app


async def _post_import(
    client: AsyncClient, *, label: str | None, filename: str
) -> dict[str, Any]:
    data = {"label": label} if label is not None else {}
    resp = await client.post(
        "/control-plane/v1/import-export/import",
        files={"file": (filename, b"fake-zip-bytes", "application/zip")},
        data=data,
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _get_task(client: AsyncClient, task_id: str) -> dict[str, Any]:
    resp = await client.get("/control-plane/v1/tasks", params={"scope": "platform"})
    assert resp.status_code == 200, resp.text
    tasks = {t["task_id"]: t for t in resp.json()["tasks"]}
    assert task_id in tasks, f"task {task_id} not found in {list(tasks)}"
    return tasks[task_id]


def _stub_open_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_export_api, "open_bundle", lambda data: object())


def _stub_run_import(monkeypatch: pytest.MonkeyPatch, report: MigrationReport) -> None:
    async def _fake_run_import(**kwargs: Any) -> MigrationReport:
        return report

    monkeypatch.setattr(import_export_api, "run_import", _fake_run_import)


def _stub_run_import_raises(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    async def _fake_run_import(**kwargs: Any) -> MigrationReport:
        raise RuntimeError(message)

    monkeypatch.setattr(import_export_api, "run_import", _fake_run_import)


# ── target construction (pure function) ────────────────────────────────────


def test_import_target_prefers_trimmed_explicit_label() -> None:
    target = import_export_api._import_target(
        "imp-1", "  Demo bundle  ", "kea-snapshot.zip"
    )
    assert target.type == import_export_api.IMPORT_TARGET_TYPE
    assert target.id == "imp-1"
    assert target.label == "Demo bundle"


def test_import_target_falls_back_to_filename_without_label() -> None:
    target = import_export_api._import_target("imp-1", None, "kea-snapshot.zip")
    assert target.label == "kea-snapshot.zip"

    target_blank = import_export_api._import_target("imp-1", "   ", "kea-snapshot.zip")
    assert target_blank.label == "kea-snapshot.zip"


def test_import_target_falls_back_to_default_when_neither_present() -> None:
    target = import_export_api._import_target("imp-1", None, None)
    assert target.label == import_export_api._DEFAULT_IMPORT_LABEL
    assert target.label  # never blank


# ── MigrationReport -> MigrationResult conversion ───────────────────────────


def test_to_migration_result_maps_every_field() -> None:
    report = MigrationReport(
        import_id="imp-1",
        source_platform="kea",
        agents_imported=4,
        agents_skipped=1,
        agents_gap=2,
        tags_imported=5,
        tags_skipped=0,
        docs_imported=10,
        docs_skipped=1,
        teams_imported=3,
        teams_skipped=0,
        identities_created=15,
        users_processed=15,
        users_skipped=["ghost"],
        teams_provisioned=3,
        team_roles_granted=14,
        team_roles_skipped=0,
        platform_roles_granted=2,
        warnings=["agent x: gap"],
    )
    result = to_migration_result(report)
    assert result.import_id == "imp-1"
    assert result.source_platform == "kea"
    assert result.agents_imported == 4
    assert result.agents_skipped == 1
    assert result.agents_gap == 2
    assert result.tags_imported == 5
    assert result.docs_imported == 10
    assert result.docs_skipped == 1
    assert result.teams_imported == 3
    assert result.identities_created == 15
    assert result.users_processed == 15
    assert result.users_skipped == ["ghost"]
    assert result.teams_provisioned == 3
    assert result.team_roles_granted == 14
    assert result.platform_roles_granted == 2
    assert result.warnings == ["agent x: gap"]

    # Defensive copy, not a shared reference — mutating the source report must
    # never retroactively change an already-converted, already-persisted result.
    report.warnings.append("late warning")
    assert result.warnings == ["agent x: gap"]


# ── real route: target + terminal event + GET /tasks persistence ───────────


@pytest.mark.asyncio
async def test_import_start_sets_canonical_target_with_explicit_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app("admin-a")
    _stub_open_bundle(monkeypatch)
    _stub_run_import(
        monkeypatch, MigrationReport(import_id="ignored", source_platform="swift")
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            launch = await _post_import(
                client, label="  Demo bundle  ", filename="kea-snapshot.zip"
            )
            task = await _get_task(client, launch["task_id"])
    finally:
        app.dependency_overrides.clear()

    assert task["target"]["type"] == import_export_api.IMPORT_TARGET_TYPE
    assert task["target"]["id"] == launch["import_id"]
    assert task["target"]["label"] == "Demo bundle"
    assert task["state"] == "succeeded"


@pytest.mark.asyncio
async def test_import_start_without_label_falls_back_to_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app("admin-b")
    _stub_open_bundle(monkeypatch)
    _stub_run_import(
        monkeypatch, MigrationReport(import_id="ignored", source_platform="swift")
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            launch = await _post_import(client, label=None, filename="kea-snapshot.zip")
            task = await _get_task(client, launch["task_id"])
    finally:
        app.dependency_overrides.clear()

    assert task["target"]["label"] == "kea-snapshot.zip"


@pytest.mark.asyncio
async def test_import_success_without_warnings_produces_full_structured_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app("admin-c")
    _stub_open_bundle(monkeypatch)
    report = MigrationReport(
        import_id="ignored",
        source_platform="swift",
        agents_imported=3,
        tags_imported=2,
        docs_imported=1,
        teams_imported=1,
        identities_created=15,
        users_processed=15,
        teams_provisioned=3,
        team_roles_granted=14,
        platform_roles_granted=2,
    )
    _stub_run_import(monkeypatch, report)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            launch = await _post_import(
                client, label="clean run", filename="snapshot.zip"
            )
            task = await _get_task(client, launch["task_id"])
    finally:
        app.dependency_overrides.clear()

    assert task["state"] == "succeeded"
    assert task["progress"] == 1.0
    detail = task["detail"]
    assert detail is not None
    assert detail["step_id"] == "done"
    result = detail["result"]
    assert result is not None
    assert result["import_id"] == "ignored"  # verbatim from the stubbed report
    assert result["agents_imported"] == 3
    assert result["teams_provisioned"] == 3
    assert result["team_roles_granted"] == 14
    assert result["platform_roles_granted"] == 2
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_import_success_with_warnings_preserves_them_in_terminal_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app("admin-d")
    _stub_open_bundle(monkeypatch)
    report = MigrationReport(
        import_id="ignored",
        source_platform="kea",
        agents_imported=2,
        agents_gap=1,
        warnings=[
            "agent agent-9: no swift template for 'v2.custom' (GAP — add to "
            "KEA_TO_SWIFT_TEMPLATE in agent_map.py before cutover)"
        ],
    )
    _stub_run_import(monkeypatch, report)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            launch = await _post_import(
                client, label="with warnings", filename="snapshot.zip"
            )
            task = await _get_task(client, launch["task_id"])
    finally:
        app.dependency_overrides.clear()

    # A partial reconciliation must still be `succeeded` (no new TaskState) —
    # the tell is the non-empty `warnings` list, not a different state.
    assert task["state"] == "succeeded"
    result = task["detail"]["result"]
    assert result["agents_gap"] == 1
    assert len(result["warnings"]) == 1
    assert "v2.custom" in result["warnings"][0]


@pytest.mark.asyncio
async def test_import_exception_produces_failed_never_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app("admin-e")
    _stub_open_bundle(monkeypatch)
    _stub_run_import_raises(monkeypatch, "OpenFGA unreachable")

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            launch = await _post_import(
                client, label="will fail", filename="snapshot.zip"
            )
            task = await _get_task(client, launch["task_id"])
    finally:
        app.dependency_overrides.clear()

    assert task["state"] == "failed"
    assert task["state"] != "succeeded"
    assert task["error"] is not None
    assert "OpenFGA unreachable" in task["error"]
    # The canonical target must survive the failure — an honest failure still
    # tells the operator *what* failed, not just that something did.
    assert task["target"]["type"] == import_export_api.IMPORT_TARGET_TYPE
    assert task["target"]["label"] == "will fail"
