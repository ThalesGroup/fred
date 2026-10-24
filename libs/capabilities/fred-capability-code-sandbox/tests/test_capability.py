import json

import pytest
from fred_capability_code_sandbox.capability import CodeSandboxCapability
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
    assert [tool.name for tool in tools] == ["execute_code"]
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
