from __future__ import annotations

import pytest

from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.mcp_utils import MCPConnectionError
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    MCPServerConfiguration,
    MCPServerRef,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext


class _FakeMcpConfig:
    def __init__(self, server: MCPServerConfiguration) -> None:
        self._server = server

    def get_server(self, server_id: str) -> MCPServerConfiguration | None:
        if server_id == self._server.id:
            return self._server
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.get_tools_calls = 0

    async def get_tools(self):
        self.get_tools_calls += 1
        return []


class _FakeAgent:
    def __init__(self, server_id: str) -> None:
        self.runtime_context = RuntimeContext(
            session_id="session-1",
            user_id="user-1",
            language="en",
        )
        self._tuning = AgentTuning(
            role="test-agent",
            description="Test agent",
            mcp_servers=[MCPServerRef(id=server_id)],
        )

    def get_agent_tunings(self) -> AgentTuning:
        return self._tuning

    def get_id(self) -> str:
        return "agent-1"

    def refresh_user_access_token(self) -> str:
        return "token"


def _server(server_id: str = "mcp-test") -> MCPServerConfiguration:
    return MCPServerConfiguration(
        id=server_id,
        name="Test MCP",
        transport="streamable_http",
        url="http://localhost:8111/test",
    )


@pytest.mark.asyncio
async def test_mcp_runtime_retries_transient_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server()
    attempts = 0
    delays: list[float] = []
    client = _FakeClient()

    monkeypatch.setattr(
        "agentic_backend.common.mcp_runtime.get_mcp_configuration",
        lambda: _FakeMcpConfig(server),
    )

    async def _fake_connect(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise MCPConnectionError("temporary failure", [ConnectionError("boom")])
        return client

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        "agentic_backend.common.mcp_runtime.get_connected_mcp_client_for_agent",
        _fake_connect,
    )
    monkeypatch.setattr("agentic_backend.common.mcp_runtime.asyncio.sleep", _fake_sleep)

    runtime = MCPRuntime(agent=_FakeAgent(server.id))

    await runtime.init()

    assert attempts == 3
    assert delays == [0.5, 1.0]
    assert runtime.toolkit is not None
    assert client.get_tools_calls == 1

    await runtime.aclose()


@pytest.mark.asyncio
async def test_mcp_runtime_does_not_retry_non_retryable_init_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server()
    attempts = 0
    delays: list[float] = []

    monkeypatch.setattr(
        "agentic_backend.common.mcp_runtime.get_mcp_configuration",
        lambda: _FakeMcpConfig(server),
    )

    async def _fake_connect(**kwargs):
        nonlocal attempts
        attempts += 1
        raise ValueError("bad MCP configuration")

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        "agentic_backend.common.mcp_runtime.get_connected_mcp_client_for_agent",
        _fake_connect,
    )
    monkeypatch.setattr("agentic_backend.common.mcp_runtime.asyncio.sleep", _fake_sleep)

    runtime = MCPRuntime(agent=_FakeAgent(server.id))

    with pytest.raises(ValueError, match="bad MCP configuration"):
        await runtime.init()

    assert attempts == 1
    assert delays == []
