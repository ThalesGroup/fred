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
import pytest_asyncio
from fred_core.conversation_trace import (
    TRACE_HEADER_VALUE_BYTES,
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
from fred_runtime.app.conversation_trace_blocks import (
    TRACE_BLOCK_BYTES,
    TRACE_BLOCK_FILE,
    TRACE_CRITICAL_TAIL_BYTES,
    TraceBlockRef,
    TraceBlockWriter,
)
from fred_runtime.app.conversation_trace_model import (
    ModelSnapshotCallback,
    SnapshotWork,
)
from fred_runtime.app.conversation_trace_sse import (
    RecordedSseLane,
    SseClock,
    SsePageData,
)
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
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from requests import Request, Response, Session


class BodyStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


@pytest_asyncio.fixture
async def trace_storage(
    tmp_path: Path,
) -> AsyncIterator[tuple[TraceHttpArtifactStore, TraceBlockWriter]]:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        await store.publish("session", ref.id, {TRACE_BLOCK_FILE: data})

    writer = TraceBlockWriter(publish)
    try:
        yield store, writer
    finally:
        await writer.finish()


async def read_sse_pages(
    store: TraceHttpArtifactStore, lane: RecordedSseLane
) -> list[SsePageData]:
    await store.publish("session", lane.ref, store.sse_files(lane))
    manifest = await store.read_sse_page_manifest("session", lane.ref)
    return [
        SsePageData.model_validate_json(
            await store.read_block_ranges("session", ranges)
        )
        for ranges in manifest.pages
    ]


@pytest.mark.asyncio
async def test_artifact_store_rejects_uncompressed_payloads(tmp_path: Path) -> None:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    ref = uuid4().hex
    await store.publish(
        "session",
        ref,
        {
            "manifest.json": (
                b'{"version":1,"method":"GET","target":"https://example.com",'
                b'"request_headers":{},"response_headers":{},"response":null,'
                b'"request":{"chunks":0,"size":0,"complete":true}}'
            ),
            "model-v1.json": b'{"output_state":"absent","normalization":[]}',
            "tool-v1.json": b'{"input":{"old":true},"partial":false}',
        },
    )
    with pytest.raises(ValueError):
        await store.read("session", ref)
    with pytest.raises(ValueError):
        await store.read_model("session", ref)
    with pytest.raises(ValueError):
        await store.read_tool("session", ref)


@pytest.mark.asyncio
async def test_durable_sse_body_pages_share_truncated_provider_bytes(
    tmp_path: Path,
) -> None:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    session = "session"

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        await store.publish(session, ref.id, {TRACE_BLOCK_FILE: data})

    writer = TraceBlockWriter(publish)
    buffer = HttpTurnBuffer(block_writer=writer)
    request = httpx.Request("POST", "https://example.com/chat", content=b"{}")
    attempt = buffer.begin_http(request, call_id="call", number=1)
    assert attempt is not None
    attempt.headers(
        httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream", "Content-Encoding": "gzip"},
        )
    )
    body = (b"data: " + b"x" * 5000 + b"\r\n\r\n") * 450 + b'data: {"token": "\xc3'
    wire_body = compress(body)
    attempt.chunk(wire_body)
    attempt.sse_chunk(body)
    failure = httpx.RemoteProtocolError("incomplete chunked read")
    attempt.finish_sse(failure)
    attempt.finish(body_complete=False, failed=True, error=failure)
    buffer.close()
    drained = await writer.finish()
    buffer.mark_failed_blocks(drained.failed_blocks)
    assert not drained.failed_blocks and drained.dropped_bytes == 0
    assert attempt.summary(None, stored=True).response_bytes == len(wire_body)
    files = store.http_files(attempt)
    assert not any(
        name.startswith("response-") and "-index-" not in name for name in files
    )
    await store.publish(session, attempt.ref, files)

    received = bytearray()
    offset: int | None = 0
    while offset is not None:
        exchange = await store.read(session, attempt.ref, response_offset=offset)
        page = exchange.response_body
        assert page is not None and page.offset == offset
        assert not page.complete and page.decoded and page.total_bytes == len(body)
        page_data = b64decode(page.data)
        assert 0 < len(page_data) <= TRACE_BLOCK_BYTES
        received.extend(page_data)
        offset = page.next_offset
    assert received == body
    assert (
        await store.read_body_range(session, attempt.ref, len(body) - 8, 8) == body[-8:]
    )


@pytest.mark.asyncio
async def test_durable_snapshots_use_blocks_and_preserve_tool_correlations(
    tmp_path: Path,
) -> None:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    session = "session"

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        await store.publish(session, ref.id, {TRACE_BLOCK_FILE: data})

    writer = TraceBlockWriter(publish)
    buffer = HttpTurnBuffer(block_writer=writer)
    requesting = ModelHttpCapture(buffer, "requesting", "test")
    assert requesting.record_model_call()
    await requesting.input_snapshot([HumanMessage(content="test")], ())
    await requesting.output_snapshot(
        [
            AIMessage(
                content="", tool_calls=[{"name": "query", "args": {}, "id": "query1"}]
            )
        ],
        partial=False,
        had_chunks=False,
        partial_chunks=(),
    )

    tool = buffer.start_tool("query", "query1", TraceToolSource.NATIVE)
    assert tool is not None
    tool_input = {"name": "report", "query": "x" * 40_000}
    await tool.retain("input", tool_input)
    await tool.finish(TraceToolOutcome.SUCCESS, {"rows": [1, 2]})

    receiving = ModelHttpCapture(buffer, "receiving", "test")
    assert receiving.record_model_call()
    tool_result = "Rows: 1, 2" + "x" * TRACE_BLOCK_BYTES
    model_inputs: list[BaseMessage] = [
        ToolMessage(content=tool_result, tool_call_id="query1")
    ]
    model_inputs.extend(HumanMessage(content="follow-up") for _ in range(256))
    definitions = [{"name": f"tool{index}"} for index in range(33)]
    await receiving.input_snapshot(model_inputs, definitions)
    for index in range(65):
        later_tool = buffer.start_tool("query", f"later{index}", TraceToolSource.NATIVE)
        assert later_tool is not None
        await later_tool.retain("input", {"query": "x" * 10_000})
        snapshot = ModelHttpCapture(buffer, f"later-model{index}", "test")
        assert snapshot.record_model_call()
        await snapshot.input_snapshot([HumanMessage(content="a" * 10_000)], ())

    assert not buffer.incomplete
    buffer.close()
    drain = await writer.finish()
    assert not drain.failed_blocks and drain.dropped_bytes == 0
    buffer.mark_failed_blocks(drain.failed_blocks)
    links = tool.model_links(buffer.model_calls, before=float("inf"))
    assert [(link.call_id, link.relation) for link in links] == [
        ("requesting", "requested"),
        ("receiving", "received"),
    ]

    call = receiving.snapshot
    assert call is not None and call.input is not None
    assert call.input.messages == [{"tool_call_id": "query1"}]
    await store.publish(session, call.ref, store.model_files(call, call.evidence([])))
    await store.publish(session, tool.ref, store.tool_files(tool))
    model_evidence = await store.read_model(session, call.ref)
    assert model_evidence.input is not None
    assert model_evidence.input.messages[0]["content"] == tool_result
    assert len(model_evidence.input.messages) == 257
    assert len(model_evidence.input.tools) == 33
    tool_evidence = await store.read_tool(session, tool.ref)
    assert tool_evidence.input == tool_input
    assert tool_evidence.output == {"rows": [1, 2]}
    assert tool_evidence.model_result == model_evidence.input.messages[0]


@pytest.mark.asyncio
async def test_http_offsets_cross_missing_blocks_without_renumbering(
    tmp_path: Path,
) -> None:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    session = "session"
    published = 0

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        nonlocal published
        published += 1
        if published == 2:
            raise TimeoutError("storage stalled")
        await store.publish(session, ref.id, {TRACE_BLOCK_FILE: data})

    writer = TraceBlockWriter(publish, block_bytes=4)
    buffer = HttpTurnBuffer(block_writer=writer)
    attempt = buffer.begin_http(
        httpx.Request("POST", "https://example.com/chat", content=b""),
        call_id="test",
        number=1,
    )
    assert attempt is not None
    attempt.headers(httpx.Response(200))
    attempt.chunk(b"headlosttail")
    attempt.finish(body_complete=True)
    drain = await writer.finish()
    buffer.mark_failed_blocks(drain.failed_blocks)
    assert buffer.incomplete and len(drain.failed_blocks) == 1
    await store.publish(session, attempt.ref, store.http_files(attempt))

    early = (await store.read(session, attempt.ref)).response_body
    assert early is not None and not early.complete
    assert (early.offset, early.next_offset, early.total_bytes) == (0, 8, 12)
    assert b64decode(early.data) == b"head"
    assert early.next_offset is not None
    late = (
        await store.read(session, attempt.ref, response_offset=early.next_offset)
    ).response_body
    assert late is not None and late.offset == 8 and late.next_offset is None
    assert b64decode(late.data) == b"tail"
    with pytest.raises(FileNotFoundError, match="range is unavailable"):
        await store.read_body_range(session, attempt.ref, 2, 8)
    assert await store.read_body_range(session, attempt.ref, 8, 4) == b"tail"


@pytest.mark.asyncio
async def test_interrupted_provider_keeps_latest_tail_when_writer_is_full(
    tmp_path: Path,
) -> None:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    session = "session"
    started = asyncio.Event()
    resume = asyncio.Event()

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        started.set()
        await resume.wait()
        await store.publish(session, ref.id, {TRACE_BLOCK_FILE: data})

    writer = TraceBlockWriter(publish, queue_bytes=TRACE_BLOCK_BYTES)
    buffer = HttpTurnBuffer(block_writer=writer)
    attempt = buffer.begin_http(
        httpx.Request("POST", "https://example.com/chat", content=b""),
        call_id="test",
        number=1,
    )
    assert attempt is not None
    attempt.headers(httpx.Response(200, headers={"Content-Type": "text/event-stream"}))
    head = b"x" * TRACE_BLOCK_BYTES
    attempt.chunk(head)
    attempt.sse_chunk(head)
    await asyncio.wait_for(started.wait(), timeout=1)
    assert writer.remaining_capacity == 0

    rejected = b"lost" * TRACE_CRITICAL_TAIL_BYTES + b"\n\ndata: cut\xc3"
    attempt.chunk(rejected)
    attempt.sse_chunk(rejected)
    failure = httpx.RemoteProtocolError("incomplete chunked read")
    attempt.finish_sse(failure)
    attempt.finish(body_complete=False, failed=True, error=failure)
    resume.set()
    drain = await writer.finish()
    buffer.mark_failed_blocks(drain.failed_blocks)
    assert drain.dropped_bytes >= len(rejected) - TRACE_CRITICAL_TAIL_BYTES
    assert not drain.failed_blocks
    await store.publish(session, attempt.ref, store.http_files(attempt))
    tail_start = len(head) + len(rejected) - TRACE_CRITICAL_TAIL_BYTES
    early = (await store.read(session, attempt.ref)).response_body
    assert early is not None and early.next_offset == tail_start
    assert b64decode(early.data) == head
    assert (
        await store.read_body_range(
            session, attempt.ref, tail_start, TRACE_CRITICAL_TAIL_BYTES
        )
        == rejected[-TRACE_CRITICAL_TAIL_BYTES:]
    )


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
    fragments: list[str],
    output_state: TraceModelOutputState,
    content: str | None,
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
) -> None:
    store, writer = trace_storage
    buffer = HttpTurnBuffer(block_writer=writer)
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
    call = observer.snapshot
    await writer.finish()
    await store.publish("session", call.ref, store.model_files(call, call.evidence([])))
    saved = await store.read_model("session", call.ref)
    assert saved.input is not None
    assert saved.input.messages[0]["content"] == "synthetic"
    assert saved.output_state == output_state
    if content is None:
        assert saved.output is None
    else:
        assert saved.output is not None
        assert saved.output.messages[0]["content"] == content


@pytest.mark.asyncio
@pytest.mark.parametrize("content_encoding", ["gzip", None])
async def test_sse_frames_precede_normalization_and_survive_content_decoding(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
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
    store, writer = trace_storage
    buffer = HttpTurnBuffer(block_writer=writer)
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
    assert attempt.response_body.observed == len(encoded)
    attempt.sse.prepare_provider()
    lane = attempt.sse.summary(stored=True)
    assert lane.ending == TraceSseEnding.COMPLETED
    assert lane.started_ms >= 3000
    normalization = attempt.normalization(raw_stored=True)
    assert normalization.status == TraceNormalizationStatus.CORRECTED
    (rewrite,) = normalization.rewrites
    assert rewrite.tool_call_id == "call-original"
    assert rewrite.frame_index == 2
    assert attempt.normalization(raw_stored=False).rewrites[0].frame_index is None
    await writer.finish()
    await store.publish("session", attempt.ref, store.http_files(attempt))
    (page,) = await read_sse_pages(store, attempt.sse)
    assert lane.headers_available
    assert "provider-correlation" not in lane.model_dump_json()
    assert (await store.read_sse_headers("session", lane.ref)).headers == {
        name: value[:TRACE_HEADER_VALUE_BYTES]
        for name, value in headers.items()
        if name not in {"set-cookie", "authorization", "x-api-key"}
    }
    evidence = await store.read("session", attempt.ref)
    assert evidence.response_body is not None
    assert evidence.response_body.decoded == bool(content_encoding)
    assert b64decode(evidence.response_body.data) == raw
    for frame, original in zip(page.frames, [second, first, second, done], strict=True):
        assert frame.offset is not None
        assert (
            await store.read_body_range("session", lane.ref, frame.offset, frame.size)
            == original
        )
    assert page.frames[-1].kind == TraceSseKind.DONE


@pytest.mark.asyncio
async def test_partial_sse_keeps_exact_line_endings_and_separates_gap_from_lifetime(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
    store, writer = trace_storage
    lane = RecordedSseLane(
        uuid4().hex, SseClock(started=100.0), 0, writer, headers_ms=0
    )
    lane.feed(b": keepalive\r\n\r", 100.125)
    lane.feed(b"\ndata: other\n", 100.25)
    lane.feed(b"\n", 100.5)
    lane.finish(220.5, TraceSseEnding.TRUNCATED)
    lane.prepare_provider()
    info = lane.summary(stored=True)
    await writer.finish()
    (page,) = await read_sse_pages(store, lane)
    assert info.end_ms == 120_500
    assert info.longest_gap == (500, 120_500)
    assert [frame.at_ms for frame in page.frames] == [125, 500]
    first_size = len(b": keepalive\r\n\r\n")
    second_size = len(b"data: other\n\n")
    assert [(frame.offset, frame.size) for frame in page.frames] == [
        (0, first_size),
        (first_size, second_size),
    ]


@pytest.mark.asyncio
async def test_transport_preserves_attempt_bytes_and_private_storage(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
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

    artifact_store, writer = trace_storage
    buffer = HttpTurnBuffer(block_writer=writer)
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
    recorded = buffer.close()
    await writer.finish()
    assert [item.number for item in recorded] == [1, 2, 3]
    assert len({item.ref for item in recorded}) == 3
    for item, (status, expected) in zip(recorded, responses, strict=True):
        await artifact_store.write("session", item)
        summary = item.summary("fixture-release", stored=True)
        assert summary.status == status
        assert summary.completeness == TraceHttpCompleteness.COMPLETE
        assert summary.upstream_id == f"response-{status}"
        assert summary.failure_stage == (
            TraceHttpFailureStage.HTTP_STATUS if status >= 400 else None
        )
        payload = await artifact_store.read("session", item.ref)
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

    await artifact_store.erase("session")
    with pytest.raises(FileNotFoundError):
        await artifact_store.read("session", recorded[0].ref)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "headers", "bearer_replay"),
    [
        ("", {"Authorization": "Bearer fixture"}, True),
        ("?api-version=fixture", {"Authorization": "Bearer fixture"}, False),
        (
            "",
            {
                "Authorization": "Bearer fixture",
                "TrustNest-Apim-Subscription-Key": "fixture",
            },
            False,
        ),
        ("", {"api-key": "fixture"}, False),
        ("", {"Authorization": "Bearer fixture", "Host": "other.example"}, False),
    ],
)
async def test_http_evidence_records_bearer_replay_without_credentials(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
    query: str,
    headers: dict[str, str],
    bearer_replay: bool,
):
    target = "https://provider.example/proxy%2Fprod/v1/chat/completions"
    request = httpx.Request("POST", target + query, headers=headers, json={})
    store, writer = trace_storage
    attempt = HttpTurnBuffer(block_writer=writer).begin_http(
        request, call_id="call", number=1
    )
    assert attempt is not None
    await writer.finish()
    await store.write("session", attempt)

    evidence = await store.read("session", attempt.ref)
    assert evidence.target == target
    assert evidence.bearer_replay is bearer_replay
    assert set(evidence.request_headers) == {"content-type", "content-length"}


@pytest.mark.asyncio
async def test_trace_budget_never_truncates_the_caller_response(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
    _, writer = trace_storage
    raw_response = b"z" * (writer.value_capacity + 1)
    buffer = HttpTurnBuffer(block_writer=writer)
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
    assert attempt.response_body.size == 0
    assert attempt.response_body.observed == len(raw_response)
    assert (
        attempt.summary(None, stored=True).completeness == TraceHttpCompleteness.PARTIAL
    )


@pytest.mark.asyncio
async def test_async_retry_discard_records_the_error_without_consuming_success(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
    store, writer = trace_storage
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
    buffer = HttpTurnBuffer(
        block_writer=writer, discarded_drains=DiscardedResponseDrains()
    )
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
    await writer.finish()
    await store.write("session", retry)
    payload = await store.read("session", retry.ref)
    assert payload.response_body is not None
    assert b64decode(payload.response_body.data) == error
    assert retry.summary(None, stored=True).upstream_id == "retry-500"
    assert (
        retry.summary(None, stored=True).completeness == TraceHttpCompleteness.COMPLETE
    )
    assert success.summary(None, stored=True).status == 200


@pytest.mark.asyncio
async def test_slow_discarded_error_is_partial_and_closes_transport(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
    store, writer = trace_storage
    closed = asyncio.Event()

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"observed prefix"
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            closed.set()

    buffer = HttpTurnBuffer(
        block_writer=writer, discarded_drains=DiscardedResponseDrains()
    )
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
    await writer.finish()
    await store.write("session", attempt)
    payload = await store.read("session", attempt.ref)
    assert payload.response_body is not None
    assert b64decode(payload.response_body.data) == b"observed prefix"
    assert (
        attempt.summary(None, stored=True).completeness == TraceHttpCompleteness.PARTIAL
    )


@pytest.mark.asyncio
async def test_snapshot_worker_preserves_the_original_nested_model_and_tool_values(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
    store, writer = trace_storage
    work = SnapshotWork()
    buffer = HttpTurnBuffer(block_writer=writer, snapshots=work)
    try:
        call = ModelHttpCapture(buffer, "call", "fixture")
        assert call.record_model_call()
        messages = [HumanMessage(content=[{"type": "text", "text": "original"}])]
        definitions = [{"function": {"name": "original"}}]
        await call.input_snapshot(messages, definitions)
        messages[0].content[0]["text"] = "changed"  # type: ignore[index]
        definitions[0]["function"]["name"] = "changed"

        tool = buffer.start_tool("test", "tool", TraceToolSource.MCP)
        assert tool is not None
        result = {"nested": ["original"]}
        await tool.retain_mcp_result(result)
        result["nested"][0] = "changed"
        await tool.finish(TraceToolOutcome.SUCCESS, {"converted": "replacement"})
        await writer.finish()
        snapshot = call.snapshot
        assert snapshot is not None
        await store.publish(
            "session", snapshot.ref, store.model_files(snapshot, snapshot.evidence([]))
        )
        saved = await store.read_model("session", snapshot.ref)
        assert saved.input is not None
        assert saved.input.messages[0]["content"] == [
            {"type": "text", "text": "original"}
        ]
        assert saved.input.tools == [{"function": {"name": "original"}}]

        await store.publish("session", tool.ref, store.tool_files(tool))
        assert (await store.read_tool("session", tool.ref)).output == {
            "nested": ["original"]
        }
    finally:
        work.close()


@pytest.mark.asyncio
async def test_provider_sse_pages_keep_terminal_and_gap_without_full_classification(
    monkeypatch: pytest.MonkeyPatch,
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
) -> None:
    store, writer = trace_storage
    original = conversation_trace_sse.provider_kind
    classified = []

    def counted(frame: bytearray) -> TraceSseKind:
        classified.append(bytes(frame))
        return original(frame)

    monkeypatch.setattr(conversation_trace_sse, "provider_kind", counted)
    lane = RecordedSseLane(uuid4().hex, SseClock(started=100.0), 0, writer)
    text = b'data: {"choices":[{"delta":{"content":"fixture"}}]}\n\n'
    done = b'data: {"type":"response.completed","response":{"id":"example"}}\n\n'
    lane.feed(text, 101.0)
    lane.feed(text * 100, 102.0)
    lane.feed(done[:20], 200.0)
    lane.feed(done[20:], 201.0)
    lane.finish(202.0, TraceSseEnding.CLOSED)
    lane.prepare_provider()
    summary = lane.summary(stored=True)
    assert classified == [done]
    assert summary.frame_count == 102
    assert summary.longest_gap == (2000, 101_000)
    assert summary.ending == TraceSseEnding.COMPLETED
    await writer.finish()
    (page,) = await read_sse_pages(store, lane)
    assert len(page.frames) == summary.frame_count


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


@pytest.mark.asyncio
async def test_provider_sse_detects_terminal_when_pages_are_unavailable(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
) -> None:
    _, writer = trace_storage
    text = b'data: {"choices":[{"delta":{"content":"[DONE]"}}]}\n\n'
    terminal = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    lane = RecordedSseLane(uuid4().hex, SseClock(started=100.0), 0, writer)
    lane.feed(text, 101.0)
    lane.feed(terminal, 103.0)
    lane.finish(104.0, TraceSseEnding.CLOSED)
    lane.prepare_provider()
    summary = lane.summary(stored=False)
    assert summary.ending == TraceSseEnding.COMPLETED
    assert summary.page_starts_ms == []
    assert summary.availability == TraceSseAvailability.PARTIAL


@pytest.mark.asyncio
async def test_provider_sse_cannot_infer_completion_from_unterminated_frame(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
) -> None:
    _, writer = trace_storage
    lane = RecordedSseLane(uuid4().hex, SseClock(started=100.0), 0, writer)
    lane.feed(b"data: [DONE]\n", 101.0)
    lane.finish(102.0, TraceSseEnding.CLOSED)
    lane.prepare_provider()
    assert lane.ending == TraceSseEnding.CLOSED
    assert lane.gap == (1000, 2000)
    assert lane.partial


@pytest.mark.asyncio
@pytest.mark.parametrize("clean_eof", [True, False])
@pytest.mark.parametrize(
    "reason", ["STOP", "MAX_TOKENS", "SAFETY", "MALFORMED_FUNCTION_CALL"]
)
async def test_vertex_gemini_finish_preserves_bytes_timing_and_stream_end(
    clean_eof: bool,
    reason: str,
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
) -> None:
    store, writer = trace_storage
    terminal = (
        'data: {"candidates":[{"finishReason" : "' + reason + '"}]}\r\n\r\n'
    ).encode()
    lane = RecordedSseLane(uuid4().hex, SseClock(started=100.0), 0, writer)
    lane.feed(terminal[:-1], 101.0)
    lane.feed(terminal[-1:], 102.0)
    end = TraceSseEnding.CLOSED if clean_eof else TraceSseEnding.TIMEOUT
    lane.finish(103.0, end)
    lane.prepare_provider()
    summary = lane.summary(stored=True)
    assert summary.ending == (TraceSseEnding.COMPLETED if clean_eof else end)
    assert summary.last_event_ms == 1000
    assert summary.end_ms == 3000
    await writer.finish()
    (page,) = await read_sse_pages(store, lane)
    assert page.frames[0].kind == TraceSseKind.DONE
    assert (page.frames[0].offset, page.frames[0].size) == (0, len(terminal))
    assert summary.availability == (
        TraceSseAvailability.CAPTURED if clean_eof else TraceSseAvailability.PARTIAL
    )


@pytest.mark.asyncio
async def test_vertex_gemini_unspecified_finish_is_not_terminal(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
) -> None:
    store, writer = trace_storage
    lane = RecordedSseLane(uuid4().hex, SseClock(started=100.0), 0, writer)
    lane.feed(
        b'data: {"candidates":[{"finishReason":"FINISH_REASON_UNSPECIFIED"}]}\n\n',
        101.0,
    )
    lane.finish(102.0, TraceSseEnding.CLOSED)
    lane.prepare_provider()

    assert lane.ending == TraceSseEnding.CLOSED
    await writer.finish()
    (page,) = await read_sse_pages(store, lane)
    assert page.frames[0].kind == TraceSseKind.OTHER


@pytest.mark.asyncio
async def test_remote_http_evidence_stays_with_overlapping_tools(
    trace_storage: tuple[TraceHttpArtifactStore, TraceBlockWriter],
):
    store, writer = trace_storage
    buffer = HttpTurnBuffer(block_writer=writer)
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
    await writer.finish()
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
    await store.publish("session", kf_tool.ref, store.tool_files(kf_tool))
    saved = await store.read_tool("session", kf_tool.ref)
    assert saved.input == {"top_k": 2}
    assert saved.output == {"text": "Transformed tool error"}
