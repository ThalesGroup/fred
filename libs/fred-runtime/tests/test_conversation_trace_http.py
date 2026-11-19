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


import asyncio
from base64 import b64decode
from collections.abc import AsyncIterator
from gzip import compress
from pathlib import Path
from threading import Event
from time import monotonic
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import httpx2
import pytest
from fred_core.conversation_trace import (
    TRACE_HEADER_VALUE_BYTES,
    TRACE_HTTP_TURN_BYTES,
    TraceHttpCompleteness,
    TraceHttpFailureStage,
    TraceModelOutputState,
    TraceNormalizationStatus,
    TraceSseAvailability,
    TraceSseEnding,
    TraceSseKind,
    TraceToolOutcome,
    TraceToolSource,
)
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.model.http_capture import active_http_capture
from fred_core.model.streamed_tool_call_ids import AsyncToolCallIdTransport
from fred_runtime.app import (
    conversation_trace_artifacts,
    conversation_trace_sse,
)
from fred_runtime.app.config import GcsRuntimeFilesystemConfig
from fred_runtime.app.conversation_trace_artifacts import (
    DiscardedResponseDrains,
    HttpTurnBuffer,
    ModelHttpCapture,
    TraceHttpArtifactStore,
)
from fred_runtime.app.conversation_trace_model import (
    ModelSnapshotCallback,
    SnapshotWork,
)
from fred_runtime.app.conversation_trace_sse import RecordedSseLane, SseBudget
from fred_runtime.app.conversation_trace_storage import TraceObjectIO
from fred_runtime.runtime_support.tool_capture import active_tool_buffer, capture_tool
from fred_runtime.runtime_support.tool_capture_http import (
    kf_trace_request,
    kf_trace_response,
    mcp_trace_request,
    mcp_trace_response,
)
from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from requests import Request, Response, Session


class BodyStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_publication_stops_after_a_slow_issued_object_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    filesystem = LocalFilesystem(root=str(tmp_path))
    store = TraceHttpArtifactStore(filesystem)
    clock = [10.0]
    monkeypatch.setattr(conversation_trace_artifacts, "monotonic", lambda: clock[0])
    started = asyncio.Event()
    release = asyncio.Event()
    write = filesystem.write
    written: list[str] = []

    async def delayed_write(path: str, data: bytes | str) -> None:
        started.set()
        await release.wait()
        await write(path, data)
        written.append(path.rsplit("/", 1)[-1])

    monkeypatch.setattr(filesystem, "write", delayed_write)
    publication = asyncio.create_task(
        store.publish(
            "session",
            uuid4().hex,
            {"chunk-0": b"old", "chunk-1": b"never"},
            deadline=11.0,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    clock[0] = 12.0
    assert not publication.done()
    release.set()
    with pytest.raises(TimeoutError, match="trace write deadline"):
        await publication
    assert written == ["chunk-0"]


@pytest.mark.asyncio
async def test_twice_cancelled_object_put_retains_its_worker_slot() -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = Event()
    writes = []

    def put(path: str, _data: bytes) -> None:
        writes.append(path)
        if path == "late":
            loop.call_soon_threadsafe(started.set)
            if not release.wait(2):
                raise TimeoutError("test did not release its object write")

    backend = MagicMock()
    backend.write.side_effect = put
    storage = TraceObjectIO(backend, workers=1)
    try:
        late = asyncio.create_task(storage.write("late", b"old"))
        await asyncio.wait_for(started.wait(), 1)
        late.cancel()
        await asyncio.sleep(0)
        late.cancel()
        with pytest.raises(asyncio.CancelledError):
            await late
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(storage.write("aborted", b"new"), 0.02)
        release.set()
        await asyncio.wait_for(storage.write("next", b"new"), 1)
        assert writes == ["late", "next"]
    finally:
        release.set()
        await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("writing", [False, True])
async def test_gcs_object_io_limits_transport_and_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    writing: bool,
) -> None:
    monkeypatch.setattr(
        "google.auth.default", lambda: (AnonymousCredentials(), "trace-test")
    )
    calls = []

    def fail_request(_session, method, url, **kwargs):
        assert not calls
        calls.append((method, url))
        assert 0 < kwargs["timeout"][0] <= 1
        assert 0 < kwargs["timeout"][1] <= 2
        assert kwargs["allow_redirects"] is False
        response = Response()
        response.status_code = 503
        response.url = url
        response.request = Request(method, url).prepare()
        response._content = b"unavailable"
        return response

    monkeypatch.setattr(Session, "request", fail_request)
    storage = await TraceObjectIO.build(
        GcsRuntimeFilesystemConfig(bucket_name="fixture"),
        workers=2,
        operation_seconds=30 if writing else 5,
    )
    try:
        with pytest.raises(ServiceUnavailable):
            if writing:
                await storage.write("conversations/example", b"fictional content")
            else:
                await storage.read("conversation-traces/example")
    finally:
        await storage.close()
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("fragments", "output_state", "content"),
    [
        ([], TraceModelOutputState.ABSENT, None),
        (["partial ", "assistant"], TraceModelOutputState.PARTIAL, "partial assistant"),
        (["x" * (256 * 1024)], TraceModelOutputState.UNAVAILABLE, None),
    ],
)
@pytest.mark.asyncio
async def test_model_capture_distinguishes_absent_and_retained_partial_output(
    fragments: list[str], output_state: TraceModelOutputState, content: str | None
) -> None:
    buffer = HttpTurnBuffer()
    observer = ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    assert observer.record_model_call()
    callback = ModelSnapshotCallback(observer)
    run_id = uuid4()
    await callback.on_chat_model_start(
        {}, [[HumanMessage(content="synthetic")]], run_id=run_id
    )
    for fragment in fragments:
        callback.on_llm_new_token(
            fragment,
            chunk=ChatGenerationChunk(message=AIMessageChunk(content=fragment)),
            run_id=run_id,
        )
    # LangChain supplies synthetic error metadata even when the request has no output.
    await callback.on_llm_error(
        RuntimeError("synthetic"),
        run_id=run_id,
        response=LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            response_metadata={"body": "synthetic provider error"},
                        )
                    )
                ]
            ],
        ),
    )
    assert observer.snapshot is not None
    assert observer.snapshot.input is not None
    assert observer.snapshot.input.messages[0]["content"] == "synthetic"
    assert observer.snapshot.output_state == output_state
    if content is None:
        assert observer.snapshot.output is None
    else:
        assert observer.snapshot.output is not None
        assert observer.snapshot.output.messages[0]["content"] == content


@pytest.mark.asyncio
@pytest.mark.parametrize("content_encoding", ["gzip", None])
async def test_sse_frames_precede_normalization_and_survive_content_decoding(
    tmp_path: Path,
    content_encoding: str | None,
):
    first = (
        b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
        b'"id":"call-original","function":{"name":"echo","arguments":""}}]}}]}\r\n\r\n'
    )
    second = (
        b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
        b'"id":"null","function":{"arguments":"{}"}}]}}]}\r\n\r\n'
    )
    done = b"data: [DONE]\r\n\r\n"
    # The byte-identical placeholder before the first real ID stays unchanged.
    # Splitting the later blank line across chunks must still link its raw frame.
    raw = second + first + second + done
    encoded = compress(raw) if content_encoding else raw
    split = 17 if content_encoding else len(raw) - len(done) - 1
    headers = {
        "content-type": "text/event-stream",
        "x-request-id": "provider-correlation",
        "set-cookie": "private",
        "authorization": "private",
        "x-api-key": "private",
        "x-correlation-id": "x" * (TRACE_HEADER_VALUE_BYTES + 1),
    }
    if content_encoding:
        headers["content-encoding"] = content_encoding
    buffer = HttpTurnBuffer()
    buffer.start_stream(monotonic(), 3000)
    token = active_http_capture.set(
        ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    )
    try:
        async with httpx.AsyncClient(
            transport=AsyncToolCallIdTransport(
                httpx.MockTransport(
                    lambda _: httpx.Response(
                        200,
                        headers=headers,
                        stream=BodyStream([encoded[:split], encoded[split:]]),
                    )
                )
            ),
        ) as client:
            response = await client.post(
                "https://provider.example/v1/chat/completions", content=b"{}"
            )
    finally:
        active_http_capture.reset(token)
    assert b'"id":null' in response.content
    assert b'"id":"null"' in response.content
    (attempt,) = buffer.close()
    assert attempt.sse is not None
    assert b"".join(attempt.response_body.chunks) == encoded
    attempt.sse.prepare_provider()
    lane = attempt.sse.summary(stored=True)
    assert lane.ending == TraceSseEnding.COMPLETED
    assert lane.started_ms >= 3000
    assert [frame.kind for frame in lane.frames] == [
        TraceSseKind.TOOL,
        TraceSseKind.TOOL,
        TraceSseKind.TOOL,
        TraceSseKind.DONE,
    ]
    normalization = attempt.normalization(raw_stored=True)
    assert normalization.status == TraceNormalizationStatus.CORRECTED
    (rewrite,) = normalization.rewrites
    assert rewrite.tool_call_id == "call-original"
    assert rewrite.frame_index == 2
    assert attempt.normalization(raw_stored=False).rewrites[0].frame_index is None
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    await store.write_sse("session", attempt.sse, create_prefix=True)
    assert lane.headers_available
    assert "provider-correlation" not in lane.model_dump_json()
    assert (await store.read_sse_headers("session", lane.ref)).headers == {
        name: value[:TRACE_HEADER_VALUE_BYTES]
        for name, value in headers.items()
        if name not in {"set-cookie", "authorization", "x-api-key"}
    }
    raw_size = lane.raw_size
    assert raw_size == len(raw)
    assert raw_size is not None
    persisted_lane = await store.read_sse("session", lane.ref, 0, raw_size)
    assert b64decode(persisted_lane.data) == raw
    for frame, original in zip(lane.frames, [second, first, second, done], strict=True):
        assert frame.offset is not None
        persisted = await store.read_sse("session", lane.ref, frame.offset, frame.size)
        assert b64decode(persisted.data) == original


def test_partial_sse_keeps_exact_line_endings_and_separates_gap_from_lifetime():
    lane = RecordedSseLane(uuid4().hex, SseBudget(started=100.0), 0, headers_ms=0)
    lane.feed(b": keepalive\r\n\r", 100.125)
    lane.feed(b"\ndata: other\n", 100.25)
    lane.feed(b"\n", 100.5)
    lane.finish(220.5, TraceSseEnding.TRUNCATED)
    lane.prepare_provider()
    info = lane.summary(stored=True)
    assert info.end_ms == 120_500
    assert info.longest_gap == (500, 120_500)
    assert [frame.at_ms for frame in info.frames] == [125, 500]
    assert lane.raw == b": keepalive\r\n\r\ndata: other\n\n"


@pytest.mark.asyncio
async def test_transport_preserves_attempt_bytes_and_private_storage(tmp_path: Path):
    responses = [
        (400, b""),
        (500, b"\xffplain upstream body\n"),
        (200, b'{"choices":[]}'),
    ]
    attempts = iter(responses)
    request_body = (
        b'{"tools":[{"function":{"name":"echo","parameters":{"type":"object"}}}]}'
    )

    def handle(request: httpx.Request) -> httpx.Response:
        status, data = next(attempts)
        return httpx.Response(
            status,
            headers={
                "content-type": "application/octet-stream",
                "x-request-id": f"response-{status}",
                "set-cookie": "auth=redacted",
            },
            stream=BodyStream([data[:4], data[4:]]),
        )

    buffer = HttpTurnBuffer()
    observer = ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    token = active_http_capture.set(observer)
    try:
        async with httpx.AsyncClient(
            transport=AsyncToolCallIdTransport(httpx.MockTransport(handle))
        ) as client:
            for status, expected in responses:
                actual = await client.post(
                    "https://provider.example/chat/completions?api_key=fixture",
                    headers={
                        "authorization": "Bearer fixture",
                        "cookie": "secret=value",
                    },
                    content=request_body,
                )
                assert (actual.status_code, actual.content) == (status, expected)
    finally:
        active_http_capture.reset(token)
    artifact_store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    recorded = buffer.close()
    assert [item.number for item in recorded] == [1, 2, 3]
    assert len({item.ref for item in recorded}) == 3
    for item, (status, expected) in zip(recorded, responses, strict=True):
        await artifact_store.write("session-one", item)
        summary = item.summary("fixture-release", stored=True)
        assert summary.status == status
        assert summary.completeness == TraceHttpCompleteness.COMPLETE
        assert summary.upstream_id == f"response-{status}"
        assert summary.failure_stage == (
            TraceHttpFailureStage.HTTP_STATUS if status >= 400 else None
        )
        payload = await artifact_store.read("session-one", item.ref)
        assert payload.target == "https://provider.example/chat/completions"
        assert (
            payload.request_body
            and b64decode(payload.request_body.data) == request_body
        )
        assert (
            payload.response_body and b64decode(payload.response_body.data) == expected
        )
        assert "authorization" not in payload.request_headers
        assert "cookie" not in payload.request_headers
        assert "set-cookie" not in payload.response_headers

    await artifact_store.erase("session-one")
    with pytest.raises(FileNotFoundError):
        await artifact_store.read("session-one", recorded[0].ref)


@pytest.mark.asyncio
async def test_trace_budget_never_truncates_the_caller_response():
    raw_response = b"z" * (TRACE_HTTP_TURN_BYTES + 256)
    buffer = HttpTurnBuffer()
    token = active_http_capture.set(
        ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    )
    try:
        async with httpx.AsyncClient(
            transport=AsyncToolCallIdTransport(
                httpx.MockTransport(
                    lambda _: httpx.Response(500, stream=BodyStream([raw_response]))
                )
            ),
        ) as client:
            response = await client.post(
                "https://provider.example/chat/completions", content=b"test"
            )
    finally:
        active_http_capture.reset(token)
    assert response.content == raw_response
    (attempt,) = buffer.close()
    assert (
        attempt.request_body.size + attempt.response_body.size == TRACE_HTTP_TURN_BYTES
    )
    assert (
        attempt.summary(None, stored=True).completeness == TraceHttpCompleteness.PARTIAL
    )


@pytest.mark.asyncio
async def test_async_retry_discard_records_the_error_without_consuming_success():
    error = b"Retryable provider failure."
    retry_received = asyncio.Event()

    class DiscardedBody(httpx.AsyncByteStream):
        closes = 0

        async def __aiter__(self) -> AsyncIterator[bytes]:
            await retry_received.wait()
            yield error

        async def aclose(self) -> None:
            self.closes += 1

    discarded = DiscardedBody()
    buffer = HttpTurnBuffer(discarded_drains=DiscardedResponseDrains())
    token = active_http_capture.set(
        ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    )
    model = "https://provider.example/chat/completions"
    responses = iter(
        (
            httpx.Response(
                500, headers={"x-request-id": "retry-500"}, stream=discarded
            ),
            httpx.Response(200, stream=BodyStream([b"answer"])),
        )
    )
    try:
        async with httpx.AsyncClient(
            transport=AsyncToolCallIdTransport(
                httpx.MockTransport(lambda _: next(responses))
            ),
        ) as client:
            failed = await client.send(
                client.build_request("POST", model, content=b"{}"), stream=True
            )
            await failed.aclose()
            assert not discarded.closes
            completed = await client.send(
                client.build_request("POST", model, content=b"{}"), stream=True
            )
            assert buffer.attempts[-1].response_body.observed == 0
            assert await completed.aread() == b"answer"
            retry_received.set()
    finally:
        active_http_capture.reset(token)
    retry, success = buffer.close()
    await buffer.settle_discarded_bodies()
    assert discarded.closes == 1
    assert retry.response_body.chunks == [bytearray(error)]
    assert retry.summary(None, stored=True).upstream_id == "retry-500"
    assert (
        retry.summary(None, stored=True).completeness == TraceHttpCompleteness.COMPLETE
    )
    assert success.summary(None, stored=True).status == 200


@pytest.mark.asyncio
async def test_slow_discarded_error_is_partial_and_closes_transport():
    closed = asyncio.Event()

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"observed prefix"
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            closed.set()

    buffer = HttpTurnBuffer(discarded_drains=DiscardedResponseDrains())
    token = active_http_capture.set(
        ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    )
    try:
        async with httpx.AsyncClient(
            transport=AsyncToolCallIdTransport(
                httpx.MockTransport(lambda _: httpx.Response(502, stream=SlowBody()))
            ),
        ) as client:
            request = client.build_request(
                "POST", "https://provider.example", content=b"{}"
            )
            response = await client.send(request, stream=True)
            await asyncio.wait_for(response.aclose(), timeout=1)
            assert not closed.is_set()
    finally:
        active_http_capture.reset(token)
    (attempt,) = buffer.close()
    await buffer.settle_discarded_bodies()
    assert closed.is_set()
    assert attempt.response_body.chunks == [bytearray(b"observed prefix")]
    assert (
        attempt.summary(None, stored=True).completeness == TraceHttpCompleteness.PARTIAL
    )


@pytest.mark.asyncio
async def test_snapshot_worker_preserves_the_original_nested_model_and_tool_values():
    work = SnapshotWork()
    buffer = HttpTurnBuffer(snapshots=work)
    try:
        call = ModelHttpCapture(buffer, "call", "fixture")
        assert call.record_model_call()
        messages = [HumanMessage(content=[{"type": "text", "text": "original"}])]
        definitions = [{"function": {"name": "original"}}]
        await call.input_snapshot(messages, definitions)
        messages[0].content[0]["text"] = "changed"  # type: ignore[index]
        definitions[0]["function"]["name"] = "changed"

        assert call.snapshot is not None and call.snapshot.input is not None
        assert call.snapshot.input.messages[0]["content"] == [
            {"type": "text", "text": "original"}
        ]
        assert call.snapshot.input.tools == [{"function": {"name": "original"}}]

        tool = buffer.start_tool("test", "tool", TraceToolSource.MCP)
        assert tool is not None
        result = {"nested": ["original"]}
        await tool.retain_mcp_result(result)
        result["nested"][0] = "changed"
        await tool.finish(TraceToolOutcome.SUCCESS, {"converted": "replacement"})
        assert tool.evidence.output == {"nested": ["original"]}
    finally:
        work.close()


def test_provider_sse_index_cap_keeps_terminal_and_gap_without_full_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = conversation_trace_sse.provider_kind
    classified = []

    def counted(frame: bytearray) -> TraceSseKind:
        classified.append(bytes(frame))
        return original(frame)

    monkeypatch.setattr(conversation_trace_sse, "provider_kind", counted)
    lane = RecordedSseLane(uuid4().hex, SseBudget(started=100.0, frames=1), 0)
    text = b'data: {"choices":[{"delta":{"content":"fixture"}}]}\n\n'
    done = b'data: {"type":"response.completed","response":{"id":"example"}}\n\n'
    lane.feed(text, 101.0)
    lane.feed(text * 100, 102.0)
    lane.feed(done[:20], 200.0)
    lane.feed(done[20:], 201.0)
    lane.finish(202.0, TraceSseEnding.CLOSED)
    assert classified == []
    lane.prepare_provider()
    summary = lane.summary(stored=True)
    assert classified == [text, done]
    assert summary.frame_count == 102
    assert summary.longest_gap == (2000, 101_000)
    assert summary.ending == TraceSseEnding.COMPLETED
    assert len(summary.frames) == 1


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (
            b'{"type":"content_block_start","content_block":{"type":"text","text":""}}',
            TraceSseKind.TEXT,
        ),
        (
            b'{"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}',
            TraceSseKind.TEXT,
        ),
        (
            b'{"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"why"}}',
            TraceSseKind.REASONING,
        ),
        (
            b'{"type":"content_block_delta","delta":{"type":"signature_delta","signature":"x"}}',
            TraceSseKind.REASONING,
        ),
        (
            b'{"type":"content_block_start","content_block":{"type":"tool_use","name":"lookup","input":{}}}',
            TraceSseKind.TOOL,
        ),
        (
            b'{"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{}"}}',
            TraceSseKind.TOOL,
        ),
        (
            b'{"type":"message_delta","delta":{"stop_reason":"tool_use"}}',
            TraceSseKind.STATUS,
        ),
        (b'{"type":"message_stop"}', TraceSseKind.DONE),
        (b'{"type":"error","error":{"type":"overloaded_error"}}', TraceSseKind.ERROR),
        (
            b'{"choices":[{"delta":{"reasoning_content":"why"}}]}',
            TraceSseKind.REASONING,
        ),
        (
            b'{"choices":[{"delta":{"content":[{"type":"thinking","thinking":[{"type":"text","text":"why"}]}]}}]}',
            TraceSseKind.REASONING,
        ),
        (
            b'{"choices":[{"delta":{"content":[{"type":"text","text":"hi"}]}}]}',
            TraceSseKind.TEXT,
        ),
        (
            b'{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"{}"}}]}}]}',
            TraceSseKind.TOOL,
        ),
        (
            b'{"choices":[{"delta":{"tool_calls":[],"content":"hi"}}]}',
            TraceSseKind.TEXT,
        ),
        (b'{"choices":[{"finish_reason":"stop","delta":{}}]}', TraceSseKind.OTHER),
        (b'{"candidates":[{"finishReason":"STOP"}]}', TraceSseKind.DONE),
        (
            b'{"candidates":[{"finishReason":"FINISH_REASON_UNSPECIFIED"}]}',
            TraceSseKind.OTHER,
        ),
        (b'{"candidates":[{}, {"finishReason":"STOP"}]}', TraceSseKind.OTHER),
        (b'{"finishReason":"STOP"}', TraceSseKind.OTHER),
    ],
)
def test_provider_sse_classifies_supported_original_events(
    data: bytes, kind: TraceSseKind
) -> None:
    assert (
        conversation_trace_sse.provider_kind(bytearray(b"data: " + data + b"\r\n\r\n"))
        == kind
    )


def test_provider_sse_byte_cap_preserves_terminal_and_missing_raw_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = conversation_trace_sse.provider_kind
    classified: list[bytes] = []

    def counted(frame: bytearray) -> TraceSseKind:
        classified.append(bytes(frame))
        return original(frame)

    monkeypatch.setattr(conversation_trace_sse, "provider_kind", counted)
    text = b'data: {"choices":[{"delta":{"content":"fixture"}}]}\n\n'
    embedded = b'data: {"choices":[{"delta":{"content":"[DONE]"}}]}\n\n'
    terminal = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    budget = SseBudget(started=100.0, bytes=len(text))
    lane = RecordedSseLane(uuid4().hex, budget, 0)
    lane.feed(text * 200, 101.0)
    lane.feed(embedded, 102.0)
    lane.feed(terminal, 103.0)
    lane.finish(104.0, TraceSseEnding.CLOSED)

    assert classified == []
    lane.prepare_provider()
    summary = lane.summary(stored=False)
    assert classified == [text, embedded, terminal]
    assert lane.raw == text
    assert summary.ending == TraceSseEnding.COMPLETED
    assert summary.frames[-1].kind == TraceSseKind.DONE
    assert all(frame.offset is None for frame in summary.frames)
    assert summary.availability == TraceSseAvailability.PARTIAL


def test_provider_sse_cannot_infer_completion_from_unterminated_frame() -> None:
    lane = RecordedSseLane(uuid4().hex, SseBudget(started=100.0), 0)
    lane.feed(b"data: [DONE]\n", 101.0)
    lane.finish(102.0, TraceSseEnding.CLOSED)
    lane.prepare_provider()
    assert lane.ending == TraceSseEnding.CLOSED
    assert lane.gap == (1000, 2000)
    assert lane.partial


@pytest.mark.parametrize("retained", [True, False])
@pytest.mark.parametrize("clean_eof", [True, False])
@pytest.mark.parametrize(
    "reason", ["STOP", "MAX_TOKENS", "SAFETY", "MALFORMED_FUNCTION_CALL"]
)
def test_vertex_gemini_finish_preserves_bytes_timing_and_stream_end(
    retained: bool, clean_eof: bool, reason: str
) -> None:
    terminal = (
        'data: {"candidates":[{"finishReason" : "' + reason + '"}]}\r\n\r\n'
    ).encode()
    lane = RecordedSseLane(
        uuid4().hex, SseBudget(started=100.0, bytes=len(terminal) if retained else 0), 0
    )
    lane.feed(terminal[:-1], 101.0)
    lane.feed(terminal[-1:], 102.0)
    end = TraceSseEnding.CLOSED if clean_eof else TraceSseEnding.TIMEOUT
    lane.finish(103.0, end)
    lane.prepare_provider()
    summary = lane.summary(stored=True)
    assert summary.ending == (TraceSseEnding.COMPLETED if clean_eof else end)
    assert summary.last_event_ms == 1000
    assert summary.end_ms == 3000
    assert summary.frames[0].kind == TraceSseKind.DONE
    assert summary.frames[0].offset == (0 if retained else None)
    assert lane.raw == (terminal if retained else b"")
    assert summary.availability == (
        TraceSseAvailability.CAPTURED
        if retained and clean_eof
        else TraceSseAvailability.PARTIAL
    )


def test_vertex_gemini_unspecified_finish_is_not_terminal() -> None:
    lane = RecordedSseLane(uuid4().hex, SseBudget(started=100.0), 0)
    lane.feed(
        b'data: {"candidates":[{"finishReason":"FINISH_REASON_UNSPECIFIED"}]}\n\n',
        101.0,
    )
    lane.finish(102.0, TraceSseEnding.CLOSED)
    lane.prepare_provider()

    assert lane.ending == TraceSseEnding.CLOSED
    assert lane.frames[0].kind == TraceSseKind.OTHER


@pytest.mark.asyncio
async def test_remote_http_evidence_stays_with_overlapping_tools(tmp_path: Path):
    buffer = HttpTurnBuffer()
    shared = asyncio.Barrier(2)
    kf_error = b'{"detail":"Original Knowledge Flow response"}'
    mcp_result = b'{"jsonrpc":"2.0","id":3,"result":{"isError":true,"content":[]}}'

    class McpBodyStream(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield mcp_result[:20]
            yield mcp_result[20:]

    async def kf_handler(_request: httpx.Request) -> httpx.Response:
        await shared.wait()
        return httpx.Response(
            503,
            stream=BodyStream([kf_error[:12], kf_error[12:]]),
            headers={"x-correlation-id": "kf-request", "set-cookie": "secret=value"},
        )

    async def mcp_handler(_request: httpx2.Request) -> httpx2.Response:
        await shared.wait()
        return httpx2.Response(200, stream=McpBodyStream())

    async def kf_call() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(kf_handler),
            event_hooks={
                "request": [kf_trace_request],
                "response": [kf_trace_response],
            },
        ) as client:
            async with capture_tool(
                "search", "kf-call", TraceToolSource.NATIVE, {"top_k": 2}
            ) as tool:
                response = await client.post(
                    "https://kf.example/vector/search?credential=synthetic",
                    headers={"authorization": "Bearer synthetic"},
                )
                assert response.status_code == 503
                assert tool is not None
                await tool.finish(
                    TraceToolOutcome.ERROR, {"text": "Transformed tool error"}
                )

    async def mcp_call() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(mcp_handler),
            event_hooks={
                "request": [mcp_trace_request],
                "response": [mcp_trace_response],
            },
        ) as client:
            async with capture_tool(
                "lookup", "mcp-call", TraceToolSource.MCP, {"query": "example"}
            ) as tool:
                response = await client.post(
                    "https://mcp.example/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "lookup"},
                    },
                )
                assert response.status_code == 200
                assert tool is not None
                await tool.finish(TraceToolOutcome.ERROR, {"is_error": True})

    token = active_tool_buffer.set(buffer)
    try:
        async with asyncio.timeout(5):
            await asyncio.gather(kf_call(), mcp_call())
    finally:
        active_tool_buffer.reset(token)
    attempts = {item.call_id: item for item in buffer.close()}
    tools = {tool.call_id: tool for tool in buffer.tool_calls}
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    for call_id, raw, status, source in (
        ("kf-call", kf_error, 503, TraceToolSource.KNOWLEDGE_FLOW),
        ("mcp-call", mcp_result, 200, TraceToolSource.MCP),
    ):
        tool = tools[call_id]
        assert (tool.outcome, tool.source) == (TraceToolOutcome.ERROR, source)
        attempt = attempts[call_id]
        assert (attempt.tool_ref, attempt.status, attempt.number) == (
            tool.ref,
            status,
            1,
        )
        await store.write("session", attempt)
        evidence = await store.read("session", attempt.ref)
        assert evidence.response_body is not None
        assert b64decode(evidence.response_body.data) == raw
        assert "authorization" not in evidence.request_headers
        assert "set-cookie" not in evidence.response_headers
        assert "?" not in evidence.target

    kf_tool = tools["kf-call"]
    await store.write_tool("session", kf_tool.ref, kf_tool.evidence)
    saved = await store.read_tool("session", kf_tool.ref)
    assert saved.input == {"top_k": 2}
    assert saved.output == {"text": "Transformed tool error"}
