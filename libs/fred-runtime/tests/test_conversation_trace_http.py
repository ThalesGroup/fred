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
from time import monotonic
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
    TraceSseEnding,
    TraceSseKind,
    TraceToolOutcome,
    TraceToolSource,
)
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.model.http_capture import active_http_capture
from fred_core.model.streamed_tool_call_ids import AsyncToolCallIdTransport
from fred_runtime.app import conversation_trace_artifacts
from fred_runtime.app.conversation_trace_artifacts import (
    HttpTurnBuffer,
    ModelHttpCapture,
    TraceHttpArtifactStore,
)
from fred_runtime.app.conversation_trace_model import ModelSnapshotCallback
from fred_runtime.app.conversation_trace_sse import RecordedSseLane, SseBudget
from fred_runtime.runtime_support.tool_capture import active_tool_buffer, capture_tool
from fred_runtime.runtime_support.tool_capture_http import (
    kf_trace_request,
    kf_trace_response,
    mcp_trace_request,
    mcp_trace_response,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult


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


@pytest.mark.parametrize(
    ("fragments", "output_state", "content"),
    [
        ([], TraceModelOutputState.ABSENT, None),
        (["partial ", "assistant"], TraceModelOutputState.PARTIAL, "partial assistant"),
        (["x" * (256 * 1024)], TraceModelOutputState.UNAVAILABLE, None),
    ],
)
def test_model_capture_distinguishes_absent_and_retained_partial_output(
    fragments: list[str], output_state: TraceModelOutputState, content: str | None
) -> None:
    buffer = HttpTurnBuffer()
    observer = ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    assert observer.record_model_call()
    callback = ModelSnapshotCallback(observer)
    run_id = uuid4()
    callback.on_chat_model_start(
        {}, [[HumanMessage(content="synthetic")]], run_id=run_id
    )
    for fragment in fragments:
        callback.on_llm_new_token(
            fragment,
            chunk=ChatGenerationChunk(message=AIMessageChunk(content=fragment)),
            run_id=run_id,
        )
    # LangChain supplies synthetic error metadata even when the request has no output.
    callback.on_llm_error(
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
    buffer = HttpTurnBuffer()
    token = active_http_capture.set(
        ModelHttpCapture(buffer, uuid4().hex, "model-fixture")
    )
    model = "https://provider.example/chat/completions"
    responses = iter(
        (
            httpx.Response(500, stream=BodyStream([error])),
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
            completed = await client.send(
                client.build_request("POST", model, content=b"{}"), stream=True
            )
            assert buffer.attempts[-1].response_body.observed == 0
            assert await completed.aread() == b"answer"
    finally:
        active_http_capture.reset(token)
    retry, success = buffer.close()
    assert retry.response_body.chunks == [bytearray(error)]
    assert (
        retry.summary(None, stored=True).completeness == TraceHttpCompleteness.COMPLETE
    )
    assert success.summary(None, stored=True).status == 200


@pytest.mark.asyncio
async def test_slow_discarded_error_is_partial_and_does_not_delay_retry_indefinitely():
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"observed prefix"
            await asyncio.Event().wait()

    buffer = HttpTurnBuffer()
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
    finally:
        active_http_capture.reset(token)
    (attempt,) = buffer.close()
    assert attempt.response_body.chunks == [bytearray(b"observed prefix")]
    assert (
        attempt.summary(None, stored=True).completeness == TraceHttpCompleteness.PARTIAL
    )


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
            with capture_tool(
                "search", "kf-call", TraceToolSource.NATIVE, {"top_k": 2}
            ) as tool:
                response = await client.post(
                    "https://kf.example/vector/search?credential=synthetic",
                    headers={"authorization": "Bearer synthetic"},
                )
                assert response.status_code == 503
                assert tool is not None
                tool.finish(TraceToolOutcome.ERROR, {"text": "Transformed tool error"})

    async def mcp_call() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(mcp_handler),
            event_hooks={
                "request": [mcp_trace_request],
                "response": [mcp_trace_response],
            },
        ) as client:
            with capture_tool(
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
                tool.finish(TraceToolOutcome.ERROR, {"is_error": True})

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
