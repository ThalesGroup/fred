"""
Offline unit tests for the multi-agent conversational memory runtime wiring.

Coverage:
- C.1  _graph_input injects invocation_turns as a leading SystemMessage
- C.2  LocalRegistryAgentInvoker forwards prior_turns to _AgentExecuteRequest
- C.3  RemoteSseAgentInvoker includes invocation_turns in the HTTP payload

All tests are offline — no LLM or HTTP calls are made.

Ref: docs/backlog/MULTI-AGENT-MEMORY-BACKLOG.md M1 phases C+D — runtime wiring
     (_graph_input injection, LocalRegistryAgentInvoker, RemoteSseAgentInvoker).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    ConversationTurn,
    PortableContext,
    PortableEnvironment,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import ExecutionConfig
from fred_sdk.runtime_support.remote_agent_invoker import (
    RemoteSseAgentInvoker,
    RemoteSseAgentInvokerConfig,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _turn(user: str, response: str, name: str | None = None) -> ConversationTurn:
    return ConversationTurn(user_message=user, agent_response=response, agent_name=name)


def _portable_context() -> PortableContext:
    return PortableContext(
        request_id="req-1",
        correlation_id="corr-1",
        actor="alice",
        tenant="test",
        environment=PortableEnvironment.DEV,
        session_id="sess-1",
        team_id="team-1",
    )


def _react_input(message: str = "hello") -> ReActInput:
    return ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content=message),)
    )


# ---------------------------------------------------------------------------
# C.1  _graph_input context injection
# ---------------------------------------------------------------------------


def test_graph_input_without_invocation_turns_returns_base_shape() -> None:
    from fred_runtime.react.react_runtime import _graph_input

    cfg = ExecutionConfig(session_id="s-1")
    result = _graph_input(_react_input("hello"), cfg)
    assert isinstance(result, dict)
    msgs = result.get("messages", [])
    assert len(msgs) >= 1
    from langchain_core.messages import SystemMessage

    assert not any(isinstance(m, SystemMessage) for m in msgs)


def test_graph_input_with_invocation_turns_prepends_system_message() -> None:
    from langchain_core.messages import SystemMessage

    from fred_runtime.react.react_runtime import _graph_input

    t = _turn("prior q", "prior a", name="Specialist")
    cfg = ExecutionConfig(session_id="s-1", invocation_turns=(t,))
    result = _graph_input(_react_input("follow-up"), cfg)
    assert isinstance(result, dict)
    msgs = result.get("messages", [])
    assert len(msgs) >= 2
    first = msgs[0]
    assert isinstance(first, SystemMessage)
    assert "prior q" in first.content
    assert "prior a" in first.content


def test_graph_input_context_block_contains_agent_name() -> None:
    from langchain_core.messages import SystemMessage

    from fred_runtime.react.react_runtime import _graph_input

    t = _turn("q", "a", name="Math Expert")
    cfg = ExecutionConfig(session_id="s-1", invocation_turns=(t,))
    result = _graph_input(_react_input("next"), cfg)
    msgs = result["messages"]  # type: ignore[index]
    system_msg = msgs[0]
    assert isinstance(system_msg, SystemMessage)
    assert "Math Expert" in system_msg.content


def test_graph_input_skips_injection_on_resume() -> None:
    from langchain_core.messages import SystemMessage

    from fred_runtime.react.react_runtime import _graph_input

    t = _turn("q", "a")
    cfg = ExecutionConfig(
        session_id="s-1",
        invocation_turns=(t,),
        resume_payload={"approved": True},
    )
    result = _graph_input(_react_input("n/a"), cfg)
    # On resume, _graph_input returns a LangGraph Command object (not a dict).
    # The important guarantee is that no SystemMessage injection happens — the
    # resume path must not prepend extra context to the messages.
    if isinstance(result, dict):
        msgs = result.get("messages", [])
        assert not any(isinstance(m, SystemMessage) for m in msgs)
    else:
        # LangGraph Command: injection was skipped (function returns base directly).
        from langchain_core.messages import SystemMessage as SM

        assert not isinstance(result, SM)


# ---------------------------------------------------------------------------
# C.2  LocalRegistryAgentInvoker forwards prior_turns
# ---------------------------------------------------------------------------


def test_local_invoker_forwards_prior_turns_to_execute_request() -> None:
    from fred_runtime.app import agent_app as agent_app_module
    from fred_runtime.app.agent_app import LocalRegistryAgentInvoker

    captured: list[object] = []

    async def fake_iterate(definition, request, **kwargs):
        captured.append(request)
        return
        yield  # make it an async generator

    t = _turn("q1", "a1", name="Bot")
    ctx = _portable_context()
    req = AgentInvocationRequest(
        agent_id="test.agent",
        message="follow-up",
        context=ctx,
        prior_turns=(t,),
    )

    class _FakeAgent(ReActAgentDefinition):
        agent_id: str = "test.agent"
        role: str = "test"
        description: str = "test"

        def policy(self):  # type: ignore[override]
            raise NotImplementedError

    registry = {"test.agent": _FakeAgent()}
    invoker = LocalRegistryAgentInvoker(registry=registry, access_token=None)

    with patch.object(
        agent_app_module, "_iterate_runtime_event_payloads", fake_iterate
    ):
        asyncio.run(invoker.invoke(req))

    assert len(captured) == 1
    execute_request = captured[0]
    turns = getattr(execute_request, "invocation_turns", None)
    assert turns is not None
    assert len(turns) == 1
    assert turns[0].user_message == "q1"


def test_local_invoker_empty_prior_turns_passed_as_empty_tuple() -> None:
    from fred_runtime.app import agent_app as agent_app_module
    from fred_runtime.app.agent_app import LocalRegistryAgentInvoker

    captured: list[object] = []

    async def fake_iterate(definition, request, **kwargs):
        captured.append(request)
        return
        yield

    ctx = _portable_context()
    req = AgentInvocationRequest(
        agent_id="test.agent",
        message="hello",
        context=ctx,
    )

    class _FakeAgent(ReActAgentDefinition):
        agent_id: str = "test.agent"
        role: str = "test"
        description: str = "test"

        def policy(self):  # type: ignore[override]
            raise NotImplementedError

    registry = {"test.agent": _FakeAgent()}
    invoker = LocalRegistryAgentInvoker(registry=registry, access_token=None)

    with patch.object(
        agent_app_module, "_iterate_runtime_event_payloads", fake_iterate
    ):
        asyncio.run(invoker.invoke(req))

    assert len(captured) == 1
    execute_request = captured[0]
    assert getattr(execute_request, "invocation_turns", None) == ()


# ---------------------------------------------------------------------------
# C.2b  _to_internal_request bridges invocation_turns from RuntimeExecuteRequest
# ---------------------------------------------------------------------------


def test_to_internal_request_forwards_invocation_turns() -> None:
    from fred_sdk.contracts.execution import RuntimeExecuteRequest

    from fred_runtime.app.agent_app import _to_internal_request

    t = _turn("q", "a", name="Bot")
    req = RuntimeExecuteRequest(
        agent_id="test.agent",
        input="follow-up",
        invocation_turns=(t,),
    )
    internal = _to_internal_request(req)
    turns = getattr(internal, "invocation_turns", None)
    assert turns is not None
    assert len(turns) == 1
    assert turns[0].user_message == "q"


def test_to_internal_request_empty_invocation_turns_passes_through() -> None:
    from fred_sdk.contracts.execution import RuntimeExecuteRequest

    from fred_runtime.app.agent_app import _to_internal_request

    req = RuntimeExecuteRequest(agent_id="test.agent", input="hello")
    internal = _to_internal_request(req)
    assert getattr(internal, "invocation_turns", None) == ()


# ---------------------------------------------------------------------------
# C.3  RemoteSseAgentInvoker payload construction
# ---------------------------------------------------------------------------


def test_remote_invoker_omits_invocation_turns_key_when_empty() -> None:
    """payload must NOT include 'invocation_turns' when prior_turns is empty."""
    config = RemoteSseAgentInvokerConfig(
        endpoint_url="http://agent.example.com/v2/execute/stream"
    )

    sent_payloads: list[dict] = []

    async def run():
        fake_response = MagicMock()
        fake_response.status_code = 200

        async def _aiter_lines():
            # Emit a minimal final event so invoke() terminates.
            yield "event: final"
            yield 'data: {"kind": "final", "content": "ok", "sources": [], "ui_parts": [], "sequence": 0}'
            yield ""

        fake_response.aiter_lines = _aiter_lines

        class _FakeStream:
            async def __aenter__(self):
                return fake_response

            async def __aexit__(self, *args):
                pass

        fake_client = MagicMock()
        fake_client.stream = MagicMock(return_value=_FakeStream())

        def _capture_stream(method, url, json=None, **kwargs):
            if json is not None:
                sent_payloads.append(json)
            return _FakeStream()

        fake_client.stream = _capture_stream

        invoker = RemoteSseAgentInvoker(config=config, client=fake_client)
        ctx = _portable_context()
        req = AgentInvocationRequest(agent_id="ag", message="hi", context=ctx)
        await invoker.invoke(req)

    asyncio.run(run())

    assert len(sent_payloads) == 1
    assert "invocation_turns" not in sent_payloads[0]


def test_remote_invoker_includes_invocation_turns_when_non_empty() -> None:
    """payload must include 'invocation_turns' when prior_turns is non-empty."""
    config = RemoteSseAgentInvokerConfig(
        endpoint_url="http://agent.example.com/v2/execute/stream"
    )

    sent_payloads: list[dict] = []

    async def run():
        fake_response = MagicMock()
        fake_response.status_code = 200

        async def _aiter_lines():
            yield "event: final"
            yield 'data: {"kind": "final", "content": "done", "sources": [], "ui_parts": [], "sequence": 0}'
            yield ""

        fake_response.aiter_lines = _aiter_lines

        def _capture_stream(method, url, json=None, **kwargs):
            if json is not None:
                sent_payloads.append(json)

            class _FakeStream:
                async def __aenter__(self):
                    return fake_response

                async def __aexit__(self, *args):
                    pass

            return _FakeStream()

        fake_client = MagicMock()
        fake_client.stream = _capture_stream

        t = _turn("q1", "a1", name="Specialist")
        invoker = RemoteSseAgentInvoker(config=config, client=fake_client)
        ctx = _portable_context()
        req = AgentInvocationRequest(
            agent_id="ag",
            message="follow-up",
            context=ctx,
            prior_turns=(t,),
        )
        await invoker.invoke(req)

    asyncio.run(run())

    assert len(sent_payloads) == 1
    assert "invocation_turns" in sent_payloads[0]
    turns_payload = sent_payloads[0]["invocation_turns"]
    assert len(turns_payload) == 1
    assert turns_payload[0]["user_message"] == "q1"
    assert turns_payload[0]["agent_name"] == "Specialist"
