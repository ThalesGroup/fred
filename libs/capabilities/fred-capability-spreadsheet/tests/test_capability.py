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

"""Registration, manifest and `create_spreadsheet` wiring with a fake workspace port."""

from __future__ import annotations

import asyncio
import io
import json
import threading
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import pytest
from fred_capability_spreadsheet import capability
from fred_capability_spreadsheet.capability import (
    PREVIEW_CONTENT_TYPE,
    TOOL_NAME,
    XLSX_CONTENT_TYPE,
    SpreadsheetCapability,
    SpreadsheetPreviewPart,
    _created_text,
)
from fred_capability_spreadsheet.store import MemoryWorkbookSpecStore, WorkbookRow
from fred_runtime.capabilities.assembly import build_capability_agent_block
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    TeamScopePolicy,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    LinkKind,
    LinkPart,
    PublishedArtifact,
)
from fred_sdk.contracts.runtime import RuntimeServices, WorkspaceFsPort
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openpyxl import load_workbook


class FakeWorkspace(WorkspaceFsPort):
    def __init__(self, fail: bool = False, fail_suffix: str | None = None) -> None:
        self.writes: list[tuple[str, bytes, str | None, str | None]] = []
        self.fail = fail
        self.fail_suffix = fail_suffix

    def bind(self, binding: BoundRuntimeContext) -> None:
        del binding

    async def write(self, path, content, *, content_type=None, title=None):
        if self.fail or (self.fail_suffix and path.endswith(self.fail_suffix)):
            raise OSError("storage down")
        self.writes.append((path, content, content_type, title))
        return PublishedArtifact(
            key=f"teams/t/{path}",
            file_name=path.rsplit("/", 1)[-1],
            size=len(content),
            href=f"https://fred.test/download/{path}",
            document_uid="doc-1",
            mime=content_type,
            title=title,
        )


def _ctx(
    workspace: WorkspaceFsPort | None,
    session_id: str | None = "s-1",
    instance_id: str | None = None,
):
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1", session_id=session_id, agent_instance_id=instance_id
        ),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(workspace_fs=workspace),
    )


def _tool(workspace: WorkspaceFsPort | None, session_id: str | None = "s-1"):
    (tool,) = SpreadsheetCapability().tools(_ctx(workspace, session_id))
    assert isinstance(tool, StructuredTool) and tool.coroutine is not None
    return tool.coroutine


ARGS = {
    "file_name": "Q3 budget",
    "sheets": [
        {
            "name": "Budget",
            "columns": [
                {"header": "Line"},
                {
                    "header": "Amount",
                    "type": "currency",
                    "currency": "EUR",
                    "total": "sum",
                },
            ],
            "rows": [["Rent", 1200], ["Travel", 350.5]],
        }
    ],
}


def test_registers_and_validates_clean():
    registry = CapabilityRegistry()
    registry.register(SpreadsheetCapability())
    registry.validate()
    assert "spreadsheet" in registry.ids()


def test_entry_point_is_declared():
    names = {ep.name: ep.value for ep in entry_points(group="fred.capabilities")}
    assert (
        names["spreadsheet"]
        == "fred_capability_spreadsheet.capability:SpreadsheetCapability"
    )


def test_manifest_is_admin_gated_graph_compatible_with_a_preview_pane():
    manifest = SpreadsheetCapability.manifest
    assert manifest.id == "spreadsheet"
    assert manifest.icon == "table_chart"
    assert manifest.team_scope == TeamScopePolicy.ADMIN_GATED
    assert manifest.execution_models == ("react", "graph")
    assert manifest.chat_parts == [SpreadsheetPreviewPart]
    assert [panel.widget for panel in manifest.side_panels] == ["spreadsheet_pane"]
    assert manifest.router is None
    assert manifest.tables == [WorkbookRow]
    assert manifest.config_fields == []
    location = Path(SpreadsheetCapability.migrations_location())
    assert (location / "env.py").is_file() and (location / "versions").is_dir()


def test_tool_schema_exposes_only_llm_arguments():
    schema = convert_to_openai_tool(
        SpreadsheetCapability().tools(_ctx(FakeWorkspace()))[0]
    )["function"]
    assert schema["name"] == TOOL_NAME
    assert set(schema["parameters"]["properties"]) == {
        "file_name",
        "sheets",
        "language",
        "changes",
    }
    # A new workbook sends sheets, a revision sends changes: neither is required.
    assert not schema["parameters"].get("required")
    assert "$defs" not in str(schema)
    assert "never paste a Markdown table" in schema["description"]
    assert "as JSON numbers" in schema["description"]
    assert "tell the user plainly" in schema["description"]
    assert "Never send a formula as a plain string" in schema["description"]
    assert "{formula: '=...'}" in schema["description"]
    assert "Never compute derived columns yourself" in schema["description"]
    assert "'compute'" not in str(schema["parameters"])
    assert 'Use IFERROR(...,"") when a divisor may be 0' in schema["description"]
    assert "null for it in rows" in schema["description"]
    assert "never add a column or a row" in schema["description"]
    assert "Call this tool once per file" in schema["description"]
    assert "If you are a sub-agent" in schema["description"]
    assert "that agent creates one workbook" in schema["description"]
    assert "Charts are not supported yet" in schema["description"]
    assert "charts_ignored" not in str(schema)
    assert "Not available: RAND, INDIRECT" in schema["description"]
    assert "TODAY" not in schema["description"]


def test_success_text_says_when_today_or_now_were_read():
    text = _created_text("a.xlsx", computed_at="2026-10-28")
    assert "computed at build time (2026-10-28)" in text
    assert text.endswith("reply now.")
    assert "build time" not in _created_text("a.xlsx")


def test_assembly_exposes_the_tool_only_to_the_parent():
    registry = CapabilityRegistry()
    registry.register(SpreadsheetCapability())
    block = build_capability_agent_block(
        registry, {"spreadsheet": _ctx(FakeWorkspace())}
    )
    assert [tool.name for tool in block.tools] == [TOOL_NAME]
    assert block.subagent_block is not None
    assert not block.subagent_block.tools


@pytest.mark.asyncio
async def test_writes_xlsx_and_preview_and_returns_the_preview_card():
    workspace = FakeWorkspace()
    content, artifact = await _tool(workspace)(**ARGS)

    assert content.endswith(
        "File created and shown to the user. Do not create it again; reply now."
    )
    assert artifact.is_error is False
    (path, data, content_type, title) = workspace.writes[0]
    assert path.startswith("spreadsheets/s-1/Q3 budget-") and path.endswith(".xlsx")
    assert content_type == XLSX_CONTENT_TYPE
    assert title == "Q3 budget.xlsx"
    ws = load_workbook(io.BytesIO(data))["Budget"]
    assert ws["B4"].value == "=SUM(B2:B3)"

    (preview_path, preview, preview_type, _) = workspace.writes[1]
    assert preview_path == path.removesuffix(".xlsx") + ".preview.json"
    assert preview_type == PREVIEW_CONTENT_TYPE
    assert json.loads(preview)["sheets"][0]["totals"] == ["Total", 1550.5]

    (part,) = artifact.ui_parts
    assert isinstance(part, SpreadsheetPreviewPart)
    assert part.type == "spreadsheet_preview"
    assert part.preview_id == f"teams/t/{path}"
    assert part.file_name == "Q3 budget.xlsx"
    assert "title" not in part.model_dump()
    assert part.xlsx_download_url == f"https://fred.test/download/{path}"
    assert part.preview_url == f"https://fred.test/download/{preview_path}"


@pytest.mark.asyncio
async def test_preview_upload_failure_falls_back_to_the_download_chip():
    workspace = FakeWorkspace(fail_suffix=".preview.json")
    _content, artifact = await _tool(workspace)(**ARGS)

    assert artifact.is_error is False
    (path, *_rest) = workspace.writes[0]
    (link,) = artifact.ui_parts
    assert isinstance(link, LinkPart)
    assert link.kind == LinkKind.download
    assert link.href == f"https://fred.test/download/{path}"
    assert link.file_name == "Q3 budget.xlsx"
    assert link.mime == XLSX_CONTENT_TYPE


@pytest.mark.asyncio
async def test_preview_build_failure_falls_back_to_the_download_chip(monkeypatch):
    def broken_preview(request):
        raise RuntimeError("boom")

    monkeypatch.setattr(capability, "build_preview", broken_preview)
    workspace = FakeWorkspace()
    _content, artifact = await _tool(workspace)(**ARGS)

    assert len(workspace.writes) == 1
    assert isinstance(artifact.ui_parts[0], LinkPart)


@pytest.mark.asyncio
async def test_language_sets_the_totals_label_in_file_and_preview():
    workspace = FakeWorkspace()
    await _tool(workspace)(**ARGS, language="en")
    ws = load_workbook(io.BytesIO(workspace.writes[0][1]))["Budget"]
    assert ws["A4"].value == "Total"
    args = {**ARGS, "sheets": [{**ARGS["sheets"][0]}]}
    args["sheets"][0]["columns"] = [
        {"header": "Line"},
        {"header": "Amount", "type": "number", "total": "average"},
    ]
    await _tool(workspace)(**args, language="en")
    assert json.loads(workspace.writes[3][1])["sheets"][0]["totals"][0] == "Average"
    await _tool(workspace)(**args)
    assert json.loads(workspace.writes[5][1])["sheets"][0]["totals"][0] == "Moyenne"


@pytest.mark.asyncio
async def test_file_name_with_hash_and_percent_is_stripped():
    workspace = FakeWorkspace()
    await _tool(workspace)(**{**ARGS, "file_name": "Q3 #2 50%"})
    assert workspace.writes[0][0].startswith("spreadsheets/s-1/Q3 2 50-")
    assert workspace.writes[0][3] == "Q3 2 50.xlsx"


@pytest.mark.asyncio
async def test_illegal_characters_never_escape_as_an_exception():
    workspace = FakeWorkspace()
    args = {**ARGS, "sheets": [{**ARGS["sheets"][0], "rows": [["Re\x0bnt", 1]]}]}
    _content, artifact = await _tool(workspace)(**args)
    assert artifact.is_error is False
    ws = load_workbook(io.BytesIO(workspace.writes[0][1]))["Budget"]
    assert ws["A2"].value == "Rent"


@pytest.mark.asyncio
async def test_path_without_session():
    workspace = FakeWorkspace()
    await _tool(workspace, session_id=None)(**ARGS)
    assert workspace.writes[0][0].startswith("spreadsheets/Q3 budget-")


@pytest.mark.asyncio
async def test_invalid_input_returns_error_and_writes_nothing():
    workspace = FakeWorkspace()
    args = {**ARGS, "sheets": [{**ARGS["sheets"][0], "rows": [["Rent"]]}]}
    content, artifact = await _tool(workspace)(**args)
    assert artifact.is_error is True
    assert "No file was written" in content
    assert "Sheet 'Budget', row 2" in content
    assert workspace.writes == []


@pytest.mark.asyncio
async def test_missing_workspace_port_is_an_error():
    content, artifact = await _tool(None)(**ARGS)
    assert artifact.is_error is True
    assert "not available" in content


@pytest.mark.asyncio
async def test_storage_failure_is_an_error():
    content, artifact = await _tool(FakeWorkspace(fail=True))(**ARGS)
    assert artifact.is_error is True
    assert "could not be stored" in content


@pytest.mark.asyncio
async def test_tool_call_through_langchain_keeps_the_artifact():
    workspace = FakeWorkspace()
    message = (
        await SpreadsheetCapability()
        .tools(_ctx(workspace))[0]
        .ainvoke({"type": "tool_call", "id": "call-1", "name": TOOL_NAME, "args": ARGS})
    )
    assert message.artifact.ui_parts[0].type == "spreadsheet_preview"


@pytest.mark.asyncio
async def test_concurrent_builds_are_bounded_and_fail_fast(monkeypatch):
    bound = capability.MAX_CONCURRENT_BUILDS
    entered = threading.Semaphore(0)
    release = threading.Event()

    def blocking_build(request):
        entered.release()
        assert release.wait(timeout=5)
        return b"xlsx"

    monkeypatch.setattr(capability, "build_workbook", blocking_build)
    workspace = FakeWorkspace()
    running = [asyncio.ensure_future(_tool(workspace)(**ARGS)) for _ in range(bound)]
    for _ in range(bound):
        assert await asyncio.to_thread(entered.acquire, timeout=5)

    content, artifact = await _tool(workspace)(**ARGS)
    assert artifact.is_error is True
    assert "busy" in content

    release.set()
    results = await asyncio.gather(*running)
    assert all(result[1].is_error is False for result in results)
    assert capability._active_builds == 0
    assert len(workspace.writes) == 2 * bound  # each file plus its preview


@pytest.mark.asyncio
async def test_agent_parallel_edits_are_explicitly_refused_then_retried(monkeypatch):
    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    store = MemoryWorkbookSpecStore()
    monkeypatch.setattr(capability, "get_workbook_spec_store", lambda: store)
    workspace = FakeWorkspace()
    (tool,) = SpreadsheetCapability().tools(_ctx(workspace, instance_id="agent-1"))
    edits = [
        {
            "changes": [
                {"op": "edit_cell", "sheet": "Budget", "cell": cell, "value": value}
            ]
        }
        for cell, value in [("B2", 999), ("B3", 888)]
    ]
    graph = create_agent(
        model=Model(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[{"id": "create", "name": TOOL_NAME, "args": ARGS}],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": str(i), "name": TOOL_NAME, "args": args}
                        for i, args in enumerate(edits)
                    ],
                ),
                AIMessage(content="done"),
            ]
        ),
        tools=[tool],
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Make both edits")]}
    )
    messages = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    accepted = [message for message in messages if not message.artifact.is_error]
    (refused,) = [message for message in messages if message.artifact.is_error]
    assert "another spreadsheet call is still running" in refused.content
    assert not refused.artifact.ui_parts
    assert [message.artifact.ui_parts[0].version for message in accepted] == [1, 2]
    retry = await tool.ainvoke(
        {
            "type": "tool_call",
            "id": "retry",
            "name": TOOL_NAME,
            "args": edits[int(refused.tool_call_id)],
        }
    )
    assert retry.artifact.ui_parts[0].version == 3
    rows = json.loads(store.rows[("s-1", "agent-1")].spec_json)["sheets"][0]["rows"]
    assert [row[1] for row in rows] == [999, 888]
    assert len(workspace.writes) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_cancelled_builds_hold_capacity_until_workers_finish(
    monkeypatch, worker_fails
):
    bound = capability.MAX_CONCURRENT_BUILDS
    entered = threading.Semaphore(0)
    release = threading.Event()
    original = capability._build_outputs
    loop = asyncio.get_running_loop()
    unhandled = []
    old_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda loop, context: unhandled.append(context))

    def blocking_build(request):
        entered.release()
        assert release.wait(timeout=5)
        if worker_fails:
            raise RuntimeError("worker failed after cancellation")
        return original(request)

    monkeypatch.setattr(capability, "_build_outputs", blocking_build)
    workspace = FakeWorkspace()
    tasks = [asyncio.ensure_future(_tool(workspace)(**ARGS)) for _ in range(bound)]
    try:
        for _ in range(bound):
            assert await asyncio.to_thread(entered.acquire, timeout=5)
        for task in tasks:
            task.cancel()
        assert all(
            isinstance(result, asyncio.CancelledError)
            for result in await asyncio.gather(*tasks, return_exceptions=True)
        )
        text, artifact = await _tool(workspace)(**ARGS)
        assert artifact.is_error and "busy" in text
        assert not workspace.writes
        monkeypatch.setattr(capability, "_build_outputs", original)
        release.set()
        async with asyncio.timeout(5):
            while True:
                text, artifact = await _tool(workspace)(**ARGS)
                if not artifact.is_error:
                    break
                assert "busy" in text
                await asyncio.sleep(0)
        assert len(workspace.writes) == 2
        assert not unhandled
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.set_exception_handler(old_handler)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["save", "upload", "preview"])
@pytest.mark.parametrize("has_base", [False, True])
async def test_cancellation_keeps_the_last_uploaded_base(monkeypatch, phase, has_base):
    entered = asyncio.Event()
    store = MemoryWorkbookSpecStore()
    monkeypatch.setattr(capability, "get_workbook_spec_store", lambda: store)
    workspace = FakeWorkspace()
    (tool,) = SpreadsheetCapability().tools(_ctx(workspace, instance_id="agent-1"))
    assert isinstance(tool, StructuredTool) and tool.coroutine is not None
    if has_base:
        await tool.coroutine(**ARGS)
    saved = capability._save_base
    write = workspace.write

    async def blocked_save(*args):
        await saved(*args)
        if not entered.is_set():
            entered.set()
            await asyncio.Event().wait()

    async def blocked_write(path, *args, **kwargs):
        if path.endswith(".preview.json") == (phase == "preview"):
            entered.set()
            await asyncio.Event().wait()
        return await write(path, *args, **kwargs)

    if phase == "save":
        monkeypatch.setattr(capability, "_save_base", blocked_save)
    else:
        monkeypatch.setattr(workspace, "write", blocked_write)
    changed = {
        **ARGS,
        "sheets": [{**ARGS["sheets"][0], "rows": [["Rent", 999], ["Travel", 350.5]]}],
    }
    task = asyncio.ensure_future(tool.coroutine(**changed))
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    monkeypatch.setattr(workspace, "write", write)
    base = await store.get("s-1", "agent-1")
    if not has_base and phase != "preview":
        assert base is None
        text, artifact = await tool.coroutine(
            changes=[{"op": "edit_cell", "sheet": "Budget", "cell": "B3", "value": 888}]
        )
        assert artifact.is_error and "No file" in text
    else:
        assert base is not None
        assert base.version == int(has_base) + int(phase == "preview")
        _, artifact = await tool.coroutine(
            changes=[{"op": "edit_cell", "sheet": "Budget", "cell": "B3", "value": 888}]
        )
        assert artifact.ui_parts[0].version == base.version + 1
        rows = json.loads(store.rows[("s-1", "agent-1")].spec_json)["sheets"][0]["rows"]
        assert [row[1] for row in rows] == [999 if phase == "preview" else 1200, 888]


@pytest.mark.asyncio
async def test_identical_repeat_call_in_a_turn_returns_the_first_result():
    workspace = FakeWorkspace()
    tool = _tool(workspace)
    first, _ = await tool(**ARGS)
    repeat, artifact = await tool(**{**ARGS, "file_name": "Q3 budget.xlsx"})

    assert repeat == first
    assert artifact.is_error is False and artifact.ui_parts == ()
    assert len(workspace.writes) == 2  # one file plus its preview


@pytest.mark.asyncio
async def test_changed_data_or_a_new_turn_creates_a_new_file():
    workspace = FakeWorkspace()
    tool = _tool(workspace)
    await tool(**ARGS)
    changed = {**ARGS, "sheets": [{**ARGS["sheets"][0], "rows": [["Rent", 1300]]}]}
    await tool(**changed)
    await _tool(workspace)(**ARGS)  # tools are rebuilt for every turn
    assert len(workspace.writes) == 6


@pytest.mark.asyncio
async def test_literal_derived_columns_keep_the_file_and_return_a_formula_note():
    args = {
        "file_name": "Budget",
        "sheets": [
            {
                "name": "Budget",
                "columns": [
                    {"header": "Line"},
                    {"header": "Budget", "type": "currency"},
                    {"header": "Actual", "type": "currency"},
                    {"header": "Gap", "type": "currency"},
                ],
                "rows": [["Rent", 1200, 1150, -50], ["Pay", 8000, 8400, 400]],
            }
        ],
    }
    workspace = FakeWorkspace()
    content, artifact = await _tool(workspace)(**args)

    assert artifact.is_error is False and len(workspace.writes) == 2
    assert "'Gap' -> formula '=C2-B2'" in content
    assert content.endswith(
        "If a note applies, you may send the fix as changes; otherwise reply now."
    )


@pytest.mark.asyncio
async def test_a_manual_total_row_keeps_the_file_and_returns_a_note():
    args = {
        "file_name": "Budget",
        "sheets": [
            {
                "name": "Budget",
                "columns": [
                    {"header": "Line"},
                    {"header": "Amount", "type": "currency", "total": "sum"},
                ],
                "rows": [["Rent", 1200], ["Pay", 8000], ["Total", None]],
            }
        ],
    }
    workspace = FakeWorkspace()
    content, artifact = await _tool(workspace)(**args)

    assert artifact.is_error is False and len(workspace.writes) == 2
    assert (
        "sheet 'Budget', row 4 ('Total') looks like a manual total next to the "
        "automatic totals row" in content
    )
    assert content.endswith(
        "If a note applies, you may send the fix as changes; otherwise reply now."
    )
    # An identical repeat returns the same text, notes included.
    tool = _tool(workspace)
    first, _ = await tool(**args)
    repeat, _ = await tool(**args)
    assert repeat == first == content


CHART_NOTE = (
    "Note: charts are not supported yet; the workbook was created without the "
    "chart. Tell the user."
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {**ARGS, "chart": {"type": "bar", "x": "Line", "y": "Amount"}},
        {**ARGS, "Charts": [{"type": "pie"}]},
        {**ARGS, "sheets": [{**ARGS["sheets"][0], "graph": {"type": "line"}}]},
    ],
    ids=["top-level-chart", "top-level-charts", "sheet-graph"],
)
async def test_chart_arguments_are_dropped_and_the_user_is_told(args):
    workspace = FakeWorkspace()
    message = (
        await SpreadsheetCapability()
        .tools(_ctx(workspace))[0]
        .ainvoke({"type": "tool_call", "id": "c-1", "name": TOOL_NAME, "args": args})
    )

    assert message.artifact.is_error is False and len(workspace.writes) == 2
    assert message.artifact.ui_parts[0].type == "spreadsheet_preview"
    assert CHART_NOTE in message.content
    assert message.content.endswith(
        "If a note applies, you may send the fix as changes; otherwise reply now."
    )


@pytest.mark.asyncio
async def test_no_chart_argument_means_no_chart_note():
    workspace = FakeWorkspace()
    message = (
        await SpreadsheetCapability()
        .tools(_ctx(workspace))[0]
        .ainvoke({"type": "tool_call", "id": "c-1", "name": TOOL_NAME, "args": ARGS})
    )

    assert "charts are not supported" not in message.content


def _stats_args(rows: list[list[Any]], columns: list[dict[str, Any]] | None = None):
    return {
        "file_name": "Ventes",
        "sheets": [
            {
                "name": "Ventes",
                "columns": columns
                or [
                    {"header": "Vendeur"},
                    {"header": "Janvier", "type": "currency", "total": "sum"},
                ],
                "rows": rows,
            }
        ],
    }


@pytest.mark.asyncio
async def test_a_stat_row_ending_the_data_is_noted_and_the_file_kept():
    rows = [["Alice", 100], ["Bruno", 200], ["Moyenne", 150]]
    content, artifact = await _tool(FakeWorkspace())(**_stats_args(rows))
    assert artifact.is_error is False
    assert (
        "column 'Janvier' has total sum and a 'Moyenne' data row: it is included "
        "in the total" in content
    )
    assert "drop total on these columns" in content and "(=SUM(B2:B3))" in content


@pytest.mark.asyncio
async def test_empty_stat_rows_are_noted():
    rows = [["Paris", 19.2], ["Lyon", 21.0], ["Minimum", None], ["Maximum", None]]
    columns = [{"header": "Ville"}, {"header": "Juin", "type": "number"}]
    content, artifact = await _tool(FakeWorkspace())(**_stats_args(rows, columns))
    assert artifact.is_error is False
    assert "the data rows 'Minimum', 'Maximum' are empty" in content
    assert "=MIN(B2:B3)" in content


@pytest.mark.asyncio
async def test_a_percent_average_total_is_noted():
    columns = [
        {"header": "Région"},
        {"header": "2025", "type": "number", "total": "sum"},
        {"header": "2026", "type": "number", "total": "sum"},
        {"header": "Évolution", "type": "percent", "formula": "=(C2-B2)/B2"},
    ]
    columns[3]["total"] = "average"
    rows = [["Nord", 100, 110, None], ["Sud", 200, 190, None]]
    content, artifact = await _tool(FakeWorkspace())(**_stats_args(rows, columns))
    assert artifact.is_error is False
    assert "column 'Évolution' averages row percentages" in content
    assert "=(C4-B4)/B4" in content


@pytest.mark.asyncio
async def test_near_misses_get_no_stat_note():
    rows = [["Alice", 100], ["Moyenne nationale", 150], ["Bruno", 200]]
    mid, _ = await _tool(FakeWorkspace())(**_stats_args(rows))
    rows = [["Alice", 100], ["Bruno", 200], ["Moyenne", 150]]
    columns = [
        {"header": "Vendeur"},
        {"header": "Janvier", "type": "currency"},
        {"header": "Part", "type": "percent", "formula": "=B2/SUM($B$2:$B$4)"},
    ]
    untotalled, _ = await _tool(FakeWorkspace())(**_stats_args(rows, columns))
    for content in (mid, untotalled):
        assert "data row: it is included" not in content
        assert "averages row percentages" not in content and "are empty" not in content


def test_a_note_lets_the_model_fix_or_reply_and_no_note_keeps_the_ending():
    noted = _created_text("a.xlsx", notes=["column 'X' averages row percentages."])
    assert noted.endswith(
        "If a note applies, you may send the fix as changes; otherwise reply now."
    )
    assert "Do not create it again" not in noted
    assert _created_text("a.xlsx").endswith(
        "File created and shown to the user. Do not create it again; reply now."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Moyenne par mois", "Total général", "Max:"])
async def test_a_stat_word_starting_a_trailing_row_is_noted(label):
    rows = [["Alice", 100], ["Bruno", 200], [label, 150]]
    content, artifact = await _tool(FakeWorkspace())(**_stats_args(rows))
    assert artifact.is_error is False
    assert f"a '{label}' data row: it is included in the total" in content


@pytest.mark.asyncio
async def test_a_stat_row_of_formula_cells_is_not_empty():
    rows = [
        ["Paris", 19.2],
        ["Lyon", 21.0],
        ["Moyenne", {"formula": "=AVERAGE(B2:B3)"}],
    ]
    columns = [{"header": "Ville"}, {"header": "Juin", "type": "number"}]
    content, artifact = await _tool(FakeWorkspace())(**_stats_args(rows, columns))
    assert artifact.is_error is False
    assert " Note: " not in content
    assert content.endswith("Do not create it again; reply now.")
