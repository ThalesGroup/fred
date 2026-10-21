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
    SandboxResult,
)


class FakeSandbox(SandboxExecutionPort):
    def __init__(self) -> None:
        self.requests = []
        self.error: str | None = None

    async def execute(self, request):
        self.requests.append(request)
        if self.error:
            raise SandboxError(self.error)
        return SandboxResult(exit_code=0, stdout="42\n", stderr="")


def context(port):
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="user"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(sandbox_execution=port),
    )


def test_capability_boot_and_tool_schema() -> None:
    registry = CapabilityRegistry()
    registry.register(CodeSandboxCapability())
    registry.validate()
    capability = registry.capability("code_sandbox")
    assert capability.manifest.team_scope is TeamScopePolicy.ADMIN_GATED
    assert capability.manifest.execution_models == ("react", "graph")
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
