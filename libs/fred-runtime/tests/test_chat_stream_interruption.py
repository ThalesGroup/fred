# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from types import SimpleNamespace
from typing import TypedDict, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fred_core.conversation_trace import TraceOutcome
from fred_core.history.history_schema import TraceFailureCategory
from fred_core.logs.context import bind_operation_context
from fred_core.logs.http import RequestLoggingMiddleware
from fred_core.logs.processors import ContextSnapshotFilter, output_formatter
from fred_runtime.app import agent_app
from fred_runtime.app.agent_app import (
    _AgentExecuteRequest,
    _ManagedChatStream,
    _RunStreamingResponse,
    _stream,
    _stream_finisher,
)
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.conversation_trace import (
    ConversationTraceClient,
    ManagedTurnCapture,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from starlette.requests import ClientDisconnect
from starlette.types import Message, Receive, Scope, Send

pytestmark = pytest.mark.asyncio


def _scope(path: str, spec_version: str = "2.3") -> Scope:
    return {
        "type": "http",
        "asgi": {"spec_version": spec_version},
        "method": "POST",
        "path": path,
    }


async def test_interruption_log_uses_request_context_and_skips_delivered_terminal(
    caplog,
) -> None:
    formatter = output_formatter("fred-agents", None, json_output=True, colors=False)
    log_context = ContextSnapshotFilter()
    caplog.handler.addFilter(log_context)
    caplog.set_level("INFO")

    async def request(
        label: str,
        *,
        cancel: bool = False,
        terminal: bool = False,
        fail_send: bool = False,
        cancel_during_disconnect: bool = False,
    ):
        started = asyncio.Event()
        disconnected = asyncio.Event()
        cancel_producer = asyncio.Event()
        headers: dict[bytes, bytes] = {}

        async def handler(scope: Scope, receive: Receive, send: Send) -> None:
            bind_operation_context(session_id=f"session-{label}", exchange_id=label)
            chat = _ManagedChatStream()

            async def frames() -> AsyncGenerator[str, None]:
                if terminal:
                    chat.terminal_pending = True
                    yield 'data: {"kind":"final","content":"private-answer"}\n\n'
                started.set()
                await cancel_producer.wait()
                raise asyncio.CancelledError()

            stream = frames()
            await _RunStreamingResponse(
                stream, background=_stream_finisher(stream, None), chat=chat
            )(scope, receive, send)

        async def receive() -> Message:
            await disconnected.wait()
            if cancel_during_disconnect:
                cancel_producer.set()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers.update(message["headers"])
            elif fail_send:
                raise OSError("private-transport-error")

        app = RequestLoggingMiddleware(handler)
        if fail_send:
            with pytest.raises(ClientDisconnect):
                await app(_scope("/stream", "2.4"), receive, send)
            return label, headers

        task = asyncio.create_task(app(_scope("/stream"), receive, send))
        await started.wait()
        if cancel:
            task.cancel("private-exception")
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            disconnected.set()
            if cancel_during_disconnect:
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await task
        return label, headers

    try:
        async with asyncio.timeout(5):
            references = dict(
                await asyncio.gather(
                    request("lost"),
                    request("cancelled", cancel=True),
                    request("done", terminal=True),
                    request("send_failed", terminal=True, fail_send=True),
                    request("lost_on_cancel", cancel_during_disconnect=True),
                )
            )
        events = [
            json.loads(formatter.format(record))
            for record in caplog.records
            if record.getMessage() == "event=chat_stream_interrupted"
        ]
    finally:
        caplog.handler.removeFilter(log_context)

    assert len(events) == 4
    by_exchange = {event["exchange_id"]: event for event in events}
    assert set(by_exchange) == {"lost", "cancelled", "send_failed", "lost_on_cancel"}
    assert by_exchange["lost"]["reason"] == "downstream_disconnect"
    assert by_exchange["cancelled"]["reason"] == "cancelled"
    assert by_exchange["send_failed"]["reason"] == "downstream_disconnect"
    assert by_exchange["lost_on_cancel"]["reason"] == "downstream_disconnect"
    for label, event in by_exchange.items():
        assert event["session_id"] == f"session-{label}"
        assert event["request_id"] == references[label][b"x-request-id"].decode()
        assert (
            event["correlation_id"] == references[label][b"x-correlation-id"].decode()
        )
        assert "private" not in json.dumps(event)


async def test_disconnect_after_completed_response_does_not_log_interruption(
    caplog,
) -> None:
    ended = asyncio.Event()
    caplog.set_level("INFO")

    async def frames() -> AsyncGenerator[str, None]:
        yield 'data: {"kind":"status"}\n\n'

    async def receive() -> Message:
        await ended.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and not message["more_body"]:
            ended.set()

    stream = frames()
    response = _RunStreamingResponse(
        stream, background=_stream_finisher(stream, None), chat=_ManagedChatStream()
    )
    await response(_scope("/stream"), receive, send)
    assert not any(
        record.getMessage() == "event=chat_stream_interrupted"
        for record in caplog.records
    )


@pytest.mark.parametrize("ending", ["disconnect", "cancelled", "after_final"])
async def test_capture_finalizes_only_confirmed_preterminal_disconnect(
    monkeypatch, ending
) -> None:
    segment_id = uuid4()
    started = asyncio.Event()
    client = MagicMock(spec=ConversationTraceClient)
    client.artifacts = None
    capture = ManagedTurnCapture("capture", client, segment_id=segment_id)
    client.admit = AsyncMock(return_value=capture)
    container = MagicMock(spec=PodApplicationContext)
    container.conversation_trace_client = client
    monkeypatch.setattr(
        agent_app,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(history_store=None, checkpointer=None)
        ),
    )

    async def payloads(*args, **kwargs) -> AsyncGenerator[dict[str, str], None]:
        if ending == "after_final":
            yield {"kind": "final"}
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(agent_app, "_iterate_runtime_event_payloads", payloads)
    chat = _ManagedChatStream(trace_segment_id=segment_id)
    stream = _stream(
        MagicMock(spec=ReActAgentDefinition),
        _AgentExecuteRequest(
            agent_instance_id="instance",
            message="Hello",
            context={"session_id": "session", "user_id": "owner"},
        ),
        container=container,
        exchange_id="exchange",
        chat_stream=chat,
    )
    response = _RunStreamingResponse(
        stream, background=_stream_finisher(stream, None), chat=chat
    )

    async def receive() -> Message:
        await started.wait()
        if ending == "cancelled":
            await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        pass

    async with asyncio.timeout(5):
        task = asyncio.create_task(response(_scope("/stream"), receive, send))
        if ending == "cancelled":
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task

    assert client.admit.await_args.kwargs["segment_id"] == segment_id
    client.submit_facts.assert_called_once()
    result = client.submit_facts.call_args.args[1]
    assert result.segment_id == segment_id
    assert result.outcome == (
        TraceOutcome.COMPLETED if ending == "after_final" else TraceOutcome.UNKNOWN
    )
    assert result.failure_category == (
        TraceFailureCategory.STREAM_INTERRUPTED if ending == "disconnect" else None
    )


class _GraphState(TypedDict):
    text: str


@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.parametrize(
    "phase", ["before_headers", "between_fragments", "blocked_send"]
)
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_chat_disconnect_releases_only_its_provider_connection(
    phase: str, spec_version: str
) -> None:
    provider_ready = asyncio.Event()
    provider_saw_eof = asyncio.Event()
    model_cancelled = asyncio.Event()
    writer_blocked = asyncio.Event()
    other_started = asyncio.Event()
    release_other = asyncio.Event()
    tasks: set[asyncio.Task[None]] = set()

    async def provider(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            if headers.split(b" ", 2)[1] == b"/other":
                other_started.set()
                await release_other.wait()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                await writer.drain()
                return
            if phase == "before_headers":
                provider_ready.set()
            else:
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                    b"Transfer-Encoding: chunked\r\n\r\n4\r\npart\r\n"
                )
                await writer.drain()
            if await reader.read(1) == b"":
                provider_saw_eof.set()
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(provider, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with (
            server,
            httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", trust_env=False
            ) as client,
            asyncio.timeout(5),
            asyncio.TaskGroup() as group,
        ):

            async def call_model(state: _GraphState) -> _GraphState:
                try:
                    async with client.stream("POST", "/model") as response:
                        async for piece in response.aiter_raw():
                            provider_ready.set()
                            get_stream_writer()(piece.decode())
                except asyncio.CancelledError:
                    model_cancelled.set()
                    raise
                return state

            graph = (
                StateGraph(_GraphState)
                .add_node("model", call_model)
                .add_edge(START, "model")
                .add_edge("model", END)
                .compile()
            )

            async def frames() -> AsyncGenerator[str, None]:
                async with aclosing(
                    cast(
                        AsyncGenerator[object, None],
                        graph.astream({"text": "start"}, stream_mode="custom"),
                    )
                ) as events:
                    async for event in events:
                        yield f"data: {event}\n\n"

            async def receive() -> Message:
                await provider_ready.wait()
                await other_started.wait()
                if phase == "blocked_send":
                    await writer_blocked.wait()
                return {"type": "http.disconnect"}

            async def send(message: Message) -> None:
                if phase == "blocked_send" and message.get("body"):
                    writer_blocked.set()
                    await asyncio.Event().wait()

            stream = frames()
            other = group.create_task(client.get("/other"))
            response = _RunStreamingResponse(
                stream,
                background=_stream_finisher(stream, None),
                chat=_ManagedChatStream(),
            )
            try:
                await response(_scope("/stream", spec_version), receive, send)
                assert model_cancelled.is_set()
                await provider_saw_eof.wait()
                assert not other.done()
            finally:
                release_other.set()
            assert (await other).text == "OK"
    finally:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
