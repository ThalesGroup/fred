import json
import subprocess
import sys

import pytest
from fred_capability_code_sandbox.capability import CodeSandboxCapability
from fred_capability_code_sandbox.file_search import (
    SearchFilesRequest,
    build_search_program,
)
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    TeamScopePolicy,
)
from fred_sdk.contracts.runtime import RuntimeServices
from fred_sdk.contracts.sandbox import (
    SandboxError,
    SandboxExecutionPort,
    SandboxInputPort,
    SandboxResult,
    SandboxSessionIdentity,
)


class FakeSandbox(SandboxExecutionPort):
    def __init__(self) -> None:
        self.requests = []
        self.sessions = []
        self.error: str | None = None

    async def execute(self, request, session: SandboxSessionIdentity | None = None):
        self.requests.append(request)
        self.sessions.append(session)
        if self.error:
            raise SandboxError(self.error)
        return SandboxResult(exit_code=0, stdout="42\n", stderr="")


class FakeInputs(SandboxInputPort):
    def __init__(self):
        self.calls = []

    async def prepare_view(self, session):
        self.calls.append(("prepare", session))

    async def bind_corpus(self, document_uid, session):
        self.calls.append(("corpus", document_uid, session))
        return f"/inputs/corpus/{document_uid}/report.txt"

    async def bind_attachment(self, attachment_id, session):
        self.calls.append(("attachment", attachment_id, session))
        return f"/inputs/attachments/{attachment_id}/sheet.xlsx"


def context(port, session_id=None, team_id=None, inputs=None):
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="user", session_id=session_id, team_id=team_id
        ),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(sandbox_execution=port, sandbox_inputs=inputs),
    )


def test_capability_boot_and_tool_schema() -> None:
    registry = CapabilityRegistry()
    registry.register(CodeSandboxCapability())
    registry.validate()
    capability = registry.capability("code_sandbox")
    assert capability.manifest.team_scope is TeamScopePolicy.ADMIN_GATED
    assert capability.manifest.execution_models == ("react", "graph")
    assert [control.widget for control in capability.chat_controls(EmptyModel())] == [
        "attach_files"
    ]
    tool = capability.tools(context(FakeSandbox()))[0]
    assert set(tool.args_schema.model_json_schema()["properties"]) == {
        "language",
        "code",
    }
    with pytest.raises(RuntimeError, match="configured execution broker"):
        capability.tools(context(None))


@pytest.mark.asyncio
async def test_tool_executes_and_reports_bounded_error() -> None:
    port = FakeSandbox()
    tool = CodeSandboxCapability().tools(context(port))[0]
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "execute_code",
            "id": "call-1",
            "args": {"language": "python", "code": "print(42)"},
        }
    )
    assert json.loads(result.content)["stdout"] == "42\n"
    assert not result.artifact.is_error
    assert port.requests[0].language == "python"
    assert port.sessions[0] is None
    port.error = "runtime_unavailable"
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "execute_code",
            "id": "call-2",
            "args": {"language": "bash", "code": "echo hi"},
        }
    )
    assert result.artifact.is_error
    assert json.loads(result.content) == {"error_code": "runtime_unavailable"}


@pytest.mark.asyncio
async def test_tool_binds_conversation_without_exposing_it_to_model() -> None:
    port = FakeSandbox()
    tool = CodeSandboxCapability().tools(context(port, session_id="chat-1"))[0]
    await tool.ainvoke({"language": "bash", "code": "echo ok"})
    assert port.sessions[0] == SandboxSessionIdentity(
        user_id="user", session_id="chat-1"
    )
    assert set(tool.args_schema.model_fields) == {"language", "code"}


@pytest.mark.asyncio
async def test_execution_prepares_the_trusted_conversation_view() -> None:
    port = FakeSandbox()
    inputs = FakeInputs()
    tools = CodeSandboxCapability().tools(
        context(port, session_id="chat-1", team_id="team-1", inputs=inputs)
    )
    assert [tool.name for tool in tools] == ["execute_code", "search_files"]
    await tools[0].ainvoke({"language": "bash", "code": "ls /inputs"})
    assert inputs.calls == [
        (
            "prepare",
            SandboxSessionIdentity(
                user_id="user", session_id="chat-1", team_id="team-1"
            ),
        )
    ]
    assert len(port.requests) == 1


@pytest.mark.asyncio
async def test_search_uses_the_same_conversation_view_and_broker() -> None:
    port = FakeSandbox()
    inputs = FakeInputs()
    tools = CodeSandboxCapability().tools(
        context(port, session_id="chat-1", team_id="team-1", inputs=inputs)
    )
    result = await tools[1].ainvoke(
        {
            "type": "tool_call",
            "name": "search_files",
            "id": "search-1",
            "args": {
                "scope": "inputs",
                "file_glob": "*.md",
                "query": "annual-revenue",
            },
        }
    )
    assert not result.artifact.is_error
    assert result.artifact.tool_ref == "code_sandbox.search_files"
    assert port.requests[0].language == "python"
    assert "annual-revenue" in port.requests[0].code
    assert inputs.calls[0][0] == "prepare"
    assert port.sessions[0].session_id == "chat-1"


def test_search_program_filters_and_bounds_results(tmp_path) -> None:
    (tmp_path / "report.md").write_text(
        "irrelevant\n" * 900 + "Annual_Revenue: 42\n", encoding="utf-8"
    )
    (tmp_path / "ignored.md").write_text("no match\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("annual revenue secret\n", encoding="utf-8")
    (tmp_path / "link.md").symlink_to(outside)
    request = SearchFilesRequest(file_glob="*.md", query="annual-revenue")
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    found = json.loads(completed.stdout)
    assert found["matches"] == [
        {"path": str(tmp_path / "report.md"), "line": 901, "text": "Annual_Revenue: 42"}
    ]
    assert "irrelevant" not in completed.stdout
    assert "secret" not in completed.stdout


def test_search_program_lists_matching_paths_without_file_contents(tmp_path) -> None:
    for index in range(60):
        (tmp_path / f"sheet-{index:02}.csv").write_text("private\n", encoding="utf-8")
    request = SearchFilesRequest(file_glob="*.csv")
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    found = json.loads(completed.stdout)
    assert len(found["paths"]) == 50
    assert found["truncated"] is True
    assert "private" not in completed.stdout


def test_search_query_is_literal_and_cannot_run_python(tmp_path) -> None:
    marker = tmp_path / "unexpected"
    query = f"x'); open({str(marker)!r}, 'w').close(); #"
    (tmp_path / "note.md").write_text(query + "\n", encoding="utf-8")
    request = SearchFilesRequest(query=query)
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert json.loads(completed.stdout)["matches"]
    assert not marker.exists()


def test_narrow_glob_reaches_files_after_unrelated_entries(tmp_path) -> None:
    for index in range(1200):
        (tmp_path / f"a-{index:04}.txt").write_text("unrelated\n", encoding="utf-8")
    (tmp_path / "z-target.md").write_text("TARGET: found\n", encoding="utf-8")
    request = SearchFilesRequest(file_glob="*.md", query="target")
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    found = json.loads(completed.stdout)
    assert len(found["matches"]) == 1
    assert found["matches"][0]["text"] == "TARGET: found"
    assert found["truncated"] is False


def test_long_line_excerpt_contains_match_across_read_chunks(tmp_path) -> None:
    (tmp_path / "long.md").write_text(
        "a" * 4090 + "Annual_Revenue: 42\n", encoding="utf-8"
    )
    request = SearchFilesRequest(file_glob="*.md", query="annual-revenue")
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    found = json.loads(completed.stdout)
    assert len(found["matches"]) == 1
    assert "Annual_Revenue" in found["matches"][0]["text"]
    assert len(found["matches"][0]["text"]) <= 240


def test_search_glob_prefix_cannot_follow_an_escaping_symlink(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret value\n", encoding="utf-8")
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    request = SearchFilesRequest(file_glob="link/*.md", query="secret")
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    found = json.loads(completed.stdout)
    assert found["matches"] == []
    assert "secret value" not in completed.stdout


def test_search_preserves_utf8_split_across_read_chunks(tmp_path) -> None:
    (tmp_path / "unicode.md").write_text("a" * 4092 + "café value\n", encoding="utf-8")
    request = SearchFilesRequest(file_glob="*.md", query="café")
    completed = subprocess.run(
        [sys.executable, "-c", build_search_program(request, root=str(tmp_path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    found = json.loads(completed.stdout)
    assert len(found["matches"]) == 1
    assert "café value" in found["matches"][0]["text"]
