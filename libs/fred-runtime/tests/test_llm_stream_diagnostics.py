# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Offline HTTP framing faults through the real SDK and Fred middleware."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from fred_core.kpi import BaseKPIWriter
from fred_core.model.diagnostics import active_model_http, observe_async_model_response
from fred_runtime.app.execution_diagnostics import report_execution_error
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from fred_runtime.runtime_support.llm_diagnostics import (
    LlmObservation,
    LlmProgressCallback,
    classify_error,
    failed_calls,
)
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models._client_utils import StreamChunkTimeoutError
from pydantic import SecretStr

pytestmark = [pytest.mark.asyncio, pytest.mark.allow_hosts(["127.0.0.1"])]


@asynccontextmanager
async def stream_server(mode: str):
    tasks: set[asyncio.Task] = set()
    requests: list[dict] = []
    first_sent = asyncio.Event()

    async def serve(reader, writer):
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = next(
                int(line.split(b":", 1)[1])
                for line in headers.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            body = json.loads(await reader.readexactly(length))
            requests.append(body)
            selected = mode
            delta: dict[str, Any] = {"role": "assistant", "content": "synthetic-answer"}
            if mode == "tool_fragments":
                delta = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call",
                            "type": "function",
                            "function": {"name": "write", "arguments": '{"text":"'},
                        }
                    ],
                }
                selected = "success"
            if mode == "deep":
                messages = body["messages"]
                last = messages[-1]
                if last.get("role") == "user" and last.get("content") == "delegate":
                    delta = {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": i,
                                "id": f"child-{i}",
                                "type": "function",
                                "function": {
                                    "name": "task",
                                    "arguments": json.dumps(
                                        {
                                            "description": name,
                                            "subagent_type": "general-purpose",
                                        }
                                    ),
                                },
                            }
                            for i, name in enumerate(("good", "bad"))
                        ],
                    }
                    selected = "success"
                elif last.get("content") == "bad":
                    selected = "stall"
                else:
                    selected = "success"
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\nx-request-id: synthetic-upstream-1\r\nConnection: close\r\n\r\n"
            )
            await writer.drain()
            if selected == "no_first":
                await asyncio.sleep(2)
                return

            async def event(value):
                data = ("data: " + json.dumps(value) + "\n\n").encode()
                writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                await writer.drain()

            await event(
                {
                    "id": "synthetic",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "test-model",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                }
            )
            if mode == "tool_fragments":
                for fragment in ("x" * 20000, '"}'):
                    await event(
                        {
                            "id": "synthetic",
                            "object": "chat.completion.chunk",
                            "created": 0,
                            "model": "test-model",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": 0,
                                                "function": {"arguments": fragment},
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )
            first_sent.set()
            if selected == "stall":
                await asyncio.sleep(2)
            elif selected == "success":
                await event(
                    {
                        "id": "synthetic",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "test-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": "tool_calls"
                                if "tool_calls" in delta
                                else "stop",
                            }
                        ],
                    }
                )
                data = b"data: [DONE]\n\n"
                writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n0\r\n\r\n")
                await writer.drain()
            # truncated deliberately omits the terminating HTTP chunk.
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with httpx.AsyncClient(
        event_hooks={"response": [observe_async_model_response]}
    ) as client:
        model = ChatOpenAI(
            model="test-model",
            api_key=SecretStr("synthetic-key"),
            base_url=f"http://127.0.0.1:{port}/v1",
            http_async_client=client,
            streaming=True,
            max_retries=0,
            timeout=1,
            stream_chunk_timeout=0.1,
            http_socket_options=(),
        )
        try:
            yield model, requests, first_sent
        finally:
            server.close()
            await server.wait_closed()
            remaining = list(tasks)
            for task in remaining:
                task.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)
            model.root_client.close()


def middleware(kpi=None, role="root"):
    binding = cast(
        BoundRuntimeContext,
        SimpleNamespace(
            portable_context=SimpleNamespace(agent_id="test", agent_name="test")
        ),
    )
    return TracingKpiMiddleware(tracer=None, kpi=kpi, binding=binding, role=role)


async def invoke(model, telemetry, text="synthetic-request"):
    request = ModelRequest(
        model=model, messages=[HumanMessage(content=text)], state={"messages": []}
    )

    async def handler(req):
        return ModelResponse(result=[await req.model.ainvoke(req.messages)])

    return await telemetry.awrap_model_call(request, handler)


def terminal_records(caplog):
    return [
        r for r in caplog.records if r.msg == "event=llm_call_completed diagnostics=%s"
    ]


@pytest.mark.parametrize(
    ("mode", "code", "chunks"),
    [
        ("success", "none", 3),
        ("no_first", "stream_idle_timeout", 0),
        ("stall", "stream_idle_timeout", 1),
        ("truncated", "remote_protocol_error", 1),
    ],
)
async def test_real_stream_faults(mode, code, chunks, caplog):
    caplog.set_level(logging.INFO)
    kpi = Mock(spec=BaseKPIWriter)
    async with stream_server(mode) as (model, requests, _):
        if mode == "success":
            response = await invoke(model, middleware(kpi))
            assert response.result[0].content == "synthetic-answer"
        else:
            expected = (
                httpx.RemoteProtocolError
                if mode == "truncated"
                else StreamChunkTimeoutError
            )
            with pytest.raises(expected) as caught:
                await invoke(model, middleware(kpi))
            message = report_execution_error(
                logging.getLogger("test.support"), caught.value, "execution"
            )
            support = next(r for r in caplog.records if hasattr(r, "error_ref"))
            assert support.error_ref in message
            assert (
                support.llm_failures[0]["llm_call_id"]
                == terminal_records(caplog)[0].llm_call_id
            )
        assert len(requests) == 1
        assert model.callbacks is None
    terminal = terminal_records(caplog)
    assert len(terminal) == 1
    assert terminal[0].error_code == code
    assert terminal[0].observed_chunks == chunks
    assert hasattr(terminal[0], "first_chunk_ms") == bool(chunks)
    if mode == "stall":
        assert terminal[0].sdk_chunks_received == 1
        assert terminal[0].terminal_silence_ms >= 80
    if mode == "no_first":
        assert terminal[0].stage == "before_first_chunk"
    assert kpi.gauge.call_args.args == ("llm.active_calls", 0)
    assert active_model_http.get() is None


@pytest.mark.parametrize("mode", ["no_first", "stall"])
async def test_cancellation_is_not_provider_failure(mode, caplog):
    caplog.set_level(logging.INFO)
    kpi = Mock(spec=BaseKPIWriter)
    async with stream_server(mode) as (model, requests, first):
        task = asyncio.create_task(invoke(model, middleware(kpi)))
        if mode == "stall":
            await asyncio.wait_for(first.wait(), 1)
        else:
            while not requests:
                await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    terminal = terminal_records(caplog)
    assert len(terminal) == 1
    assert terminal[0].status == terminal[0].error_code == "cancelled"
    assert kpi.gauge.call_args.args == ("llm.active_calls", 0)


async def test_callback_composition_and_broken_sinks(caplog):
    class Counter(BaseCallbackHandler):
        run_inline = True
        count = 0

        def on_llm_new_token(self, token, **kwargs):
            self.count += 1

    callback = Counter()
    kpi = Mock(spec=BaseKPIWriter)
    kpi.emit.side_effect = RuntimeError("synthetic-sink-failure")
    kpi.gauge.side_effect = RuntimeError("synthetic-sink-failure")
    kpi.count.side_effect = RuntimeError("synthetic-sink-failure")
    async with stream_server("success") as (model, _, _):
        model.callbacks = [callback]
        response = await invoke(model, middleware(kpi))
        assert response.result[0].content == "synthetic-answer"
        assert callback.count == 3
        assert model.callbacks == [callback]
    async with stream_server("truncated") as (model, _, _):
        with pytest.raises(httpx.RemoteProtocolError):
            await invoke(model, middleware(kpi))


async def test_native_deep_children_are_isolated(caplog):
    from deepagents.backends import StateBackend
    from fred_runtime.deep.deep_runtime import _create_compiled_deep_agent

    caplog.set_level(logging.INFO)
    kpi = Mock(spec=BaseKPIWriter)
    async with stream_server("deep") as (model, requests, _):
        graph = _create_compiled_deep_agent(
            model=model,
            tools=[],
            system_prompt="Synthetic test",
            checkpointer=None,
            middleware=[middleware(kpi)],
            subagent_middleware=[middleware(kpi, "child")],
            backend=StateBackend(),
            permissions=[],
        )
        with pytest.raises(StreamChunkTimeoutError) as caught:
            await graph.ainvoke({"messages": [HumanMessage(content="delegate")]})
        calls, truncated = failed_calls(caught.value)
        assert not truncated
        assert len(calls) == 1
        assert calls[0]["llm_role"] == "child"
        assert len(requests) == 3
    terminals = terminal_records(caplog)
    assert len(terminals) == 3
    assert len({r.llm_call_id for r in terminals}) == 3
    children = [r for r in terminals if r.llm_role == "child"]
    assert sorted(r.observed_chunks for r in children) == [1, 3]
    assert sorted(r.error_code for r in children) == ["none", "stream_idle_timeout"]
    assert all(r.parent_run_id for r in children)
    assert calls[0]["llm_call_id"] == next(
        r.llm_call_id for r in children if r.status == "error"
    )
    child_counts = [
        c.args[1]
        for c in kpi.gauge.call_args_list
        if c.kwargs["dims"]["llm_role"] == "child"
    ]
    assert max(child_counts) == 2
    assert child_counts[-1] == 0


async def test_progress_cost_and_no_content_retention():
    observation = LlmObservation(model="test", role="root", streaming=True)
    callback = LlmProgressCallback(observation)
    for _ in range(10000):
        callback.on_llm_new_token("synthetic-private-content", chunk=object())
    assert observation.chunks == 10000
    assert "synthetic-private-content" not in repr(vars(observation))
    assert len(vars(observation)) == 11


async def test_nested_timeout_and_bounded_failure_walk():
    exc = StreamChunkTimeoutError(0.1, chunks_received=3)
    exc.__cause__ = asyncio.CancelledError()
    assert classify_error(exc)["error_code"] == "stream_idle_timeout"
    group = ExceptionGroup("synthetic", [ValueError("synthetic") for _ in range(30)])
    assert failed_calls(group) == ([], True)


@pytest.mark.parametrize("delegated", [False, True])
async def test_diagnostics_remain_content_free(delegated, caplog):
    from fred_core.security.delegation import DelegationConfig
    from fred_runtime.common.outbound_credentials import (
        DelegationRuntime,
        set_delegation_runtime,
    )

    caplog.set_level(logging.INFO)
    set_delegation_runtime(
        DelegationRuntime(config=DelegationConfig(act_for_people=delegated))
    )
    try:
        async with stream_server("truncated") as (model, _, _):
            with pytest.raises(httpx.RemoteProtocolError) as caught:
                await invoke(model, middleware(), text="private-prompt-canary")
            report_execution_error(
                logging.getLogger("test.support"), caught.value, "execution"
            )
        records = [
            r
            for r in caplog.records
            if r.name.startswith("fred_runtime") or r.name == "test.support"
        ]
        output = repr([vars(r) for r in records])
        for secret in (
            "private-prompt-canary",
            "synthetic-answer",
            "synthetic-key",
            "127.0.0.1",
        ):
            assert secret not in output
        terminal = terminal_records(caplog)[0]
        assert hasattr(terminal, "x_request_id") == (not delegated)
    finally:
        set_delegation_runtime(None)


async def test_existing_retry_produces_distinct_attempts(monkeypatch, caplog):
    from fred_runtime.react.middleware.rate_limit_retry import RateLimitRetryMiddleware
    from openai import RateLimitError

    caplog.set_level(logging.INFO)
    tracer = middleware()
    retry = RateLimitRetryMiddleware(kpi=None, binding=tracer._binding)
    monkeypatch.setattr(retry, "_delay_for", lambda *_: 0)
    attempts = 0
    async with stream_server("success") as (model, requests, _):
        request = ModelRequest(
            model=model, messages=[HumanMessage(content="test")], state={"messages": []}
        )

        async def model_handler(req):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RateLimitError(
                    "private-provider-message",
                    response=httpx.Response(
                        429, request=httpx.Request("POST", "https://synthetic.invalid")
                    ),
                    body=None,
                )
            return ModelResponse(result=[await req.model.ainvoke(req.messages)])

        async def wrapped(req):
            return await tracer.awrap_model_call(req, model_handler)

        await retry.awrap_model_call(request, wrapped)
        assert len(requests) == 1
    records = terminal_records(caplog)
    assert [r.error_code for r in records] == ["rate_limited", "none"]
    assert len({r.llm_call_id for r in records}) == 2
    assert "private-provider-message" not in caplog.text


async def test_stateful_custom_model_is_not_cloned():
    from conftest import ToolFriendlyFakeChatModel
    from langchain_core.messages import AIMessage

    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="first"), AIMessage(content="second")]
    )
    telemetry = middleware()
    first = await invoke(model, telemetry)
    second = await invoke(model, telemetry)
    assert first.result[0].content == "first"
    assert second.result[0].content == "second"


async def test_implicit_graph_streaming_before_first_chunk(caplog):
    from langchain.agents import create_agent

    caplog.set_level(logging.INFO)
    async with stream_server("no_first") as (model, requests, _):
        model.streaming = False
        model.__pydantic_fields_set__.discard("streaming")
        graph = create_agent(model, middleware=[middleware()])
        with pytest.raises(StreamChunkTimeoutError):
            async for _ in graph.astream(
                {"messages": [HumanMessage(content="test")]},
                stream_mode=["messages", "updates"],
            ):
                pass
        assert requests[0]["stream"] is True
    assert terminal_records(caplog)[0].stage == "before_first_chunk"


@pytest.mark.parametrize(
    ("disabled", "tools", "stream_kw", "expected"),
    [
        (True, False, None, False),
        ("tool_calling", True, None, False),
        ("tool_calling", False, None, True),
        (False, False, False, False),
    ],
)
async def test_explicit_stream_selection(disabled, tools, stream_kw, expected):
    from fred_runtime.runtime_support.llm_diagnostics import streaming_selection

    model = SimpleNamespace(
        disable_streaming=disabled, streaming=True, model_fields_set={"streaming"}
    )
    settings = {} if stream_kw is None else {"stream": stream_kw}
    assert streaming_selection(model, settings, has_tools=tools) is expected


async def test_guarded_tool_fragments_through_real_stream_and_middleware(monkeypatch):
    from fred_core.model.tool_call_chunks import install_tool_fragment_guard
    from langchain_core.messages import ai

    monkeypatch.setattr(ai, "parse_partial_json", getattr(ai, "parse_partial_json"))
    install_tool_fragment_guard()
    async with stream_server("tool_fragments") as (model, requests, _):
        response = await invoke(model, middleware())
        message = response.result[0]
        assert message.tool_calls == [
            {
                "name": "write",
                "args": {"text": "x" * 20000},
                "id": "call",
                "type": "tool_call",
            }
        ]
        assert message.invalid_tool_calls == []
        assert len(requests) == 1


@pytest.mark.parametrize("outcome", ["ok", "error", "cancelled"])
async def test_timings_exclude_telemetry_outside_handler(outcome, monkeypatch, caplog):
    from fred_core.model import diagnostics as http_diagnostics
    from fred_runtime.react.middleware import tracing_kpi
    from fred_runtime.runtime_support import llm_diagnostics
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import AIMessage

    caplog.set_level(logging.INFO)
    clock = SimpleNamespace(now=100.0)
    time_source = SimpleNamespace(monotonic=lambda: clock.now)
    for module in (http_diagnostics, llm_diagnostics, tracing_kpi):
        monkeypatch.setattr(module, "time", time_source)
    observation = LlmObservation(model="test", role="root", streaming=True)
    observation.http.started = clock.now
    monkeypatch.setattr(tracing_kpi, "LlmObservation", lambda **kwargs: observation)

    def slow_sizing(*args, **kwargs):
        clock.now += 100
        return {}

    def slow_response_log(*args):
        clock.now += 1000

    original_classify = tracing_kpi.classify_error

    def slow_classify(exc):
        clock.now += 1000
        return original_classify(exc)

    monkeypatch.setattr(tracing_kpi, "model_request_char_sizes", slow_sizing)
    monkeypatch.setattr(tracing_kpi, "classify_error", slow_classify)
    kpi = Mock(spec=BaseKPIWriter)
    telemetry = middleware(kpi)
    monkeypatch.setattr(telemetry, "_log_model_response", slow_response_log)
    request = ModelRequest(
        model=FakeListChatModel(responses=["ok"]), messages=[], state={"messages": []}
    )
    failure = (
        ValueError("synthetic") if outcome == "error" else asyncio.CancelledError()
    )

    async def handler(req):
        clock.now += 2
        http_diagnostics.observe_model_response(httpx.Response(200))
        clock.now += 1
        observation.chunk()
        clock.now += 4
        observation.chunk()
        clock.now += 2
        if outcome != "ok":
            raise failure
        return ModelResponse(result=[AIMessage(content="ok")])

    if outcome == "ok":
        await telemetry.awrap_model_call(request, handler)
    else:
        with pytest.raises(type(failure)):
            await telemetry.awrap_model_call(request, handler)
        snapshots, _ = failed_calls(failure)
        assert snapshots[0]["elapsed_ms"] == 9000
        assert snapshots[0]["terminal_silence_ms"] == 2000
    terminal = terminal_records(caplog)[0]
    assert terminal.status == outcome
    assert terminal.elapsed_ms == 9000
    assert terminal.response_headers_ms == 2000
    assert terminal.first_chunk_ms == 3000
    assert terminal.max_chunk_gap_ms == 4000
    assert terminal.terminal_silence_ms == 2000
    measurements = {
        c.kwargs["name"]: c.kwargs["value"] for c in kpi.emit.call_args_list
    }
    assert measurements == {
        "llm.call_latency_ms": 9000,
        "llm.first_chunk_ms": 3000,
        "llm.max_chunk_gap_ms": 4000,
        "llm.terminal_silence_ms": 2000,
    }
