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

import pytest
from fred_capability_spreadsheet import capability
from fred_capability_spreadsheet.capability import (
    PREVIEW_CONTENT_TYPE,
    TOOL_NAME,
    XLSX_CONTENT_TYPE,
    SpreadsheetCapability,
    SpreadsheetPreviewPart,
)
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


def _ctx(workspace: WorkspaceFsPort | None, session_id: str | None = "s-1"):
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id=session_id),
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
    assert manifest.tables == []
    assert manifest.config_fields == []
    assert SpreadsheetCapability.migrations_location() is None


def test_tool_schema_exposes_only_llm_arguments():
    schema = convert_to_openai_tool(
        SpreadsheetCapability().tools(_ctx(FakeWorkspace()))[0]
    )["function"]
    assert schema["name"] == TOOL_NAME
    assert set(schema["parameters"]["properties"]) == {
        "file_name",
        "sheets",
        "language",
    }
    assert schema["parameters"]["required"] == ["file_name", "sheets"]
    assert "$defs" not in str(schema)
    assert "never paste a Markdown table" in schema["description"]
    assert "as JSON numbers" in schema["description"]
    assert "tell the user plainly" in schema["description"]
    assert "No formulas" in schema["description"]
    assert "Never compute derived columns yourself" in schema["description"]
    assert "share_of_total" in schema["description"]
    assert "A division by zero leaves the cell empty" in schema["description"]
    assert "send null for it in rows" in schema["description"]
    assert "Call this tool once per file" in schema["description"]
    assert "If you are a sub-agent" in schema["description"]
    assert "that agent creates one workbook" in schema["description"]


def test_graph_assembly_exposes_the_tool():
    registry = CapabilityRegistry()
    registry.register(SpreadsheetCapability())
    block = build_capability_agent_block(
        registry, {"spreadsheet": _ctx(FakeWorkspace())}
    )
    assert [tool.name for tool in block.tools] == [TOOL_NAME]


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
    tool = _tool(workspace)
    running = [asyncio.ensure_future(tool(**ARGS)) for _ in range(bound)]
    for _ in range(bound):
        assert await asyncio.to_thread(entered.acquire, timeout=5)

    content, artifact = await tool(**ARGS)
    assert artifact.is_error is True
    assert "busy" in content

    release.set()
    results = await asyncio.gather(*running)
    assert all(result[1].is_error is False for result in results)
    assert capability._active_builds == 0
    assert len(workspace.writes) == 2 * bound  # each file plus its preview


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
async def test_literal_derived_columns_keep_the_file_and_return_a_compute_note():
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
    assert (
        "'Gap' -> compute {op: 'subtract', left: 'Actual', right: 'Budget'}" in content
    )
    assert content.endswith("Do not create it again; reply now.")
