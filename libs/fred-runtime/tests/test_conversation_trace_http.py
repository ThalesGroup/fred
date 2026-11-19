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
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fred_core.conversation_trace import (
    TRACE_HTTP_TURN_BYTES,
    TraceHttpCompleteness,
    TraceHttpFailureStage,
)
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.model.http_capture import active_http_capture
from fred_core.model.streamed_tool_call_ids import AsyncToolCallIdTransport
from fred_runtime.app.conversation_trace_artifacts import (
    HttpTurnBuffer,
    ModelHttpCapture,
    TraceHttpArtifactStore,
)


class BodyStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


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
