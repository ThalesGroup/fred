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
"""
Offline tests for the conversation history store integration in fred-runtime.

Why this file exists:
- ``_write_turn_history`` maps RuntimeEvent payloads to ChatMessage rows;
  the mapping must be verified without a running database
- ``GET /sessions/{session_id}/messages`` must return 503 when the pod has no
  history store configured, and [] for a session with no rows
- ``PostgresHistoryStore`` must satisfy ``HistoryStorePort`` structurally so
  that runtime injection is valid

All tests are offline — no external services required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.runtime import HistoryStorePort
from langchain_core.messages import AIMessage

from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app.agent_app import _write_turn_history
from fred_runtime.runtime_context import RuntimeConfig, RuntimeContext

from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel


@tool("noop.ping", description="Return pong.")
async def _noop_ping(ctx: ToolContext) -> str:
    """Return pong — used only to give the test agent a real authored tool."""
    return "pong"


class _PingAgent(ReActAgent):
    """
    Minimal authored agent used by history endpoint tests.

    Why this exists:
    - create_agent_app needs at least one agent in the registry; this provides
      a throwaway agent that never executes in these tests
    """

    agent_id: str = "test.history.ping"
    role: str = "Ping"
    description: str = "Test ping agent."
    system_prompt_template: str = "Ping."
    tools = (_noop_ping,)


def _build_config(tmp_path) -> AgentPodConfig:
    """Build a minimal offline pod config backed by SQLite."""
    return AgentPodConfig.model_validate(
        {
            "app": {
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
            },
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test",
                },
                "authorized_origins": [],
            },
            "ai": {"knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1"},
            "storage": {"postgres": {"sqlite_path": str(tmp_path / "hist.sqlite3")}},
            "platform": {"control_plane_url": None},
        }
    )


def _make_app(monkeypatch, tmp_path):
    """
    Create a test pod app with a scripted fake chat model.

    Why this helper exists:
    - history endpoint tests need a live FastAPI app so the lifespan wires
      the runtime context, but they do not need to exercise the chat model

    How to use it:
    - call before ``with TestClient(app) as client:``
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="pong")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _PingAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    return create_agent_app(registry=registry, config=_build_config(tmp_path))


# ---------------------------------------------------------------------------
# Test 1: _write_turn_history maps a ReAct turn to the correct ChatMessage rows
# ---------------------------------------------------------------------------


def test_write_turn_history_maps_react_turn_to_chat_messages() -> None:
    """
    _write_turn_history must produce four ChatMessage rows for a single ReAct
    turn that contains a user request, one tool call, one tool result, and a
    final assistant answer.

    Why this test exists:
    - the event-to-message mapping is the core logic of durable history; getting
      role, channel, rank, and part type wrong silently corrupts the history view
    - offline: history_store is an AsyncMock — no DB required

    How to use it:
    - run via ``make test`` in fred-runtime
    """
    from fred_core.history.history_schema import Channel, Role

    store = AsyncMock()
    store.next_rank = AsyncMock(return_value=0)
    store.save = AsyncMock()

    payloads = [
        {
            "kind": "tool_call",
            "call_id": "c1",
            "tool_name": "demo.echo",
            "arguments": {"text": "hi"},
        },
        {
            "kind": "tool_result",
            "call_id": "c1",
            "content": "echo:hi",
            "is_error": False,
        },
        {
            "kind": "final",
            "content": "Done.",
            "model_name": "gpt-4o",
            "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "finish_reason": "stop",
        },
    ]

    asyncio.run(
        _write_turn_history(
            session_id="s1",
            user_id="alice",
            request_message="hi",
            payloads=payloads,
            history_store=store,
        )
    )

    store.save.assert_awaited_once()
    messages = store.save.call_args.kwargs["messages"]

    assert len(messages) == 4, f"expected 4 messages, got {len(messages)}"

    # Row 0 — user message
    assert messages[0].role == Role.user
    assert messages[0].channel == Channel.final
    assert messages[0].parts[0].text == "hi"
    assert messages[0].rank == 0

    # Row 1 — tool call record
    assert messages[1].role == Role.assistant
    assert messages[1].channel == Channel.tool_call
    assert messages[1].parts[0].name == "demo.echo"
    assert messages[1].rank == 1

    # Row 2 — tool result record
    assert messages[2].role == Role.tool
    assert messages[2].channel == Channel.tool_result
    assert messages[2].parts[0].content == "echo:hi"
    assert messages[2].rank == 2

    # Row 3 — final assistant answer
    assert messages[3].role == Role.assistant
    assert messages[3].channel == Channel.final
    assert messages[3].parts[0].text == "Done."
    assert messages[3].metadata.model == "gpt-4o"
    assert messages[3].rank == 3


def test_write_turn_history_skips_save_when_no_content() -> None:
    """
    _write_turn_history must not call save() when there is no request message
    and no mappable payloads — avoids writing empty rows to the history table.

    Why this test exists:
    - status-only event sequences (e.g. a turn with only status events) must not
      produce ghost rows in the history store
    """
    store = AsyncMock()
    store.next_rank = AsyncMock(return_value=0)
    store.save = AsyncMock()

    asyncio.run(
        _write_turn_history(
            session_id="s1",
            user_id="alice",
            request_message=None,
            payloads=[],
            history_store=store,
        )
    )

    store.save.assert_not_awaited()


def test_write_turn_history_handles_awaiting_human_and_node_error() -> None:
    """
    _write_turn_history must map awaiting_human and node_error payloads to
    system-role ChatMessage rows with the correct channels.

    Why this test exists:
    - HITL pauses and node errors are distinct runtime events; they must be
      persisted so the history view reflects the full agent execution trace
    - awaiting_human now uses Channel.hitl_request and stores the full choices
      list (HitlRequestPart) rather than a flat system_note text
    """
    from fred_core.history.history_schema import Channel, HitlRequestPart, Role

    store = AsyncMock()
    store.next_rank = AsyncMock(return_value=5)
    store.save = AsyncMock()

    payloads = [
        {
            "kind": "awaiting_human",
            "request": {
                "question": "Approve deployment?",
                "stage": "approve",
                "title": "Confirm",
                "choices": [
                    {"id": "yes", "label": "Yes, deploy"},
                    {"id": "no", "label": "No, abort"},
                ],
            },
        },
        {
            "kind": "node_error",
            "node_id": "search",
            "error_message": "timeout",
            "routed_to": "fallback",
        },
        {
            "kind": "final",
            "content": "Handled gracefully.",
        },
    ]

    asyncio.run(
        _write_turn_history(
            session_id="s2",
            user_id="bob",
            request_message="deploy",
            payloads=payloads,
            history_store=store,
        )
    )

    store.save.assert_awaited_once()
    messages = store.save.call_args.kwargs["messages"]

    # user + awaiting_human + node_error + final = 4 rows
    assert len(messages) == 4

    assert messages[0].role == Role.user
    assert messages[0].rank == 5  # base_rank returned by next_rank mock

    # awaiting_human → hitl_request channel with full structured HitlRequestPart
    assert messages[1].role == Role.system
    assert messages[1].channel == Channel.hitl_request
    hitl_part = messages[1].parts[0]
    assert isinstance(hitl_part, HitlRequestPart)
    assert hitl_part.question == "Approve deployment?"
    assert len(hitl_part.choices) == 2
    assert hitl_part.choices[0].id == "yes"
    assert hitl_part.choices[1].label == "No, abort"

    assert messages[2].role == Role.system
    assert messages[2].channel == Channel.error
    assert "timeout" in messages[2].parts[0].text

    assert messages[3].role == Role.assistant
    assert messages[3].channel == Channel.final


# ---------------------------------------------------------------------------
# Test 2: HistoryStorePort protocol compliance
# ---------------------------------------------------------------------------


def test_postgres_history_store_satisfies_history_store_port() -> None:
    """
    PostgresHistoryStore must expose all methods declared by HistoryStorePort.

    Why this test exists:
    - ``HistoryStorePort`` is a ``Protocol``; structural compliance is verified
      here before any integration test exercises the real database
    - if the port evolves and the implementation is not updated, this test fails
      fast without requiring a live DB

    How to use it:
    - offline: inspects ``dir(PostgresHistoryStore)`` — no DB required
    """
    from fred_core.history.postgres_history_store import PostgresHistoryStore

    required = {"save", "get", "list_sessions", "delete_session"}

    # Implementation must have all required methods.
    impl_attrs = set(dir(PostgresHistoryStore))
    missing_from_impl = required - impl_attrs
    assert not missing_from_impl, (
        f"PostgresHistoryStore is missing HistoryStorePort methods: {missing_from_impl}"
    )

    # Port itself must declare all required methods.
    port_attrs = set(dir(HistoryStorePort))
    missing_from_port = required - port_attrs
    assert not missing_from_port, (
        f"HistoryStorePort is missing expected method declarations: {missing_from_port}"
    )


# ---------------------------------------------------------------------------
# Test 3: GET /sessions/{id}/messages returns 503 when no store configured
# ---------------------------------------------------------------------------


def test_get_session_messages_returns_503_when_history_store_not_configured(
    monkeypatch, tmp_path
) -> None:
    """
    GET /agents/sessions/{session_id}/messages must return HTTP 503 when the
    pod runtime has no history store configured.

    Why this test exists:
    - a pod without persistent storage must fail loudly rather than silently
      returning an empty list — 503 signals a configuration gap, not data absence

    How to use it:
    - offline: the runtime context is monkeypatched inside the live TestClient
      to present history_store=None to the endpoint handler
    """
    app = _make_app(monkeypatch, tmp_path)
    no_store_ctx = RuntimeContext(
        RuntimeConfig(knowledge_flow_url="http://localhost:8111/knowledge-flow/v1")
    )

    with TestClient(app) as client:
        # Replace the runtime context after lifespan so the endpoint sees
        # history_store=None.
        monkeypatch.setattr(
            agent_app_module, "get_runtime_context", lambda: no_store_ctx
        )
        response = client.get("/pod/v1/agents/sessions/session-abc/messages")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Test 4: GET /sessions/{id}/messages returns [] for an empty session
# ---------------------------------------------------------------------------


def test_get_session_messages_returns_empty_list_for_unknown_session(
    monkeypatch, tmp_path
) -> None:
    """
    GET /agents/sessions/{session_id}/messages must return an empty JSON array
    when the history store contains no rows for the given session.

    Why this test exists:
    - the UI must handle new or empty sessions without an error response
    - this verifies the endpoint serializes an empty list correctly (not null,
      not 404, not 503)

    How to use it:
    - offline: a mock history store returning [] is injected via a patched
      runtime context; no DB required
    """
    app = _make_app(monkeypatch, tmp_path)

    mock_store = AsyncMock()
    mock_store.get = AsyncMock(return_value=[])

    mock_ctx = RuntimeContext(
        RuntimeConfig(
            knowledge_flow_url="http://localhost:8111/knowledge-flow/v1",
            history_store=mock_store,
        )
    )

    with TestClient(app) as client:
        monkeypatch.setattr(agent_app_module, "get_runtime_context", lambda: mock_ctx)
        response = client.get("/pod/v1/agents/sessions/session-new/messages")

    assert response.status_code == 200
    assert response.json() == []
    mock_store.get.assert_awaited_once_with(session_id="session-new")
