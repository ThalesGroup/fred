# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Passively bind remote client exchanges to the authorized tool invocation."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING, cast

import httpx
import httpx2
from fred_core.conversation_trace import TraceToolSource
from fred_core.model.http_capture import observe_http_response

from fred_runtime.runtime_support.tool_capture import active_tool_capture

if TYPE_CHECKING:
    from fred_runtime.app.conversation_trace_artifacts import RecordedHttpAttempt

_ATTEMPT = "fred_conversation_tool_http_attempt"
_MCP_METHOD = re.compile(rb'^[^{]*\{[^{}]{0,256}?"method"\s*:\s*"tools/call"')


def _begin(request: httpx.Request | httpx2.Request, source: TraceToolSource) -> None:
    tool = active_tool_capture.get()
    if tool is None:
        return
    tool.source = source
    tool.http_count += 1
    attempt = tool.buffer.begin_http(
        request,
        call_id=tool.call_id or tool.ref,
        number=tool.http_count,
        tool_ref=tool.ref,
    )
    if attempt is not None:
        request.extensions[_ATTEMPT] = attempt


async def kf_trace_request(request: httpx.Request) -> None:
    with suppress(Exception):
        _begin(request, TraceToolSource.KNOWLEDGE_FLOW)


async def kf_trace_response(response: httpx.Response) -> None:
    attempt = cast(
        "RecordedHttpAttempt | None", response.request.extensions.pop(_ATTEMPT, None)
    )
    if attempt is not None:
        with suppress(Exception):
            observe_http_response(response, attempt, asynchronous=True)


async def mcp_trace_request(request: httpx2.Request) -> None:
    if active_tool_capture.get() is None:
        return
    with suppress(Exception):
        # A tool scope may also open the session or query its schema. Retain the
        # call exchange and an explicitly resumed call, excluding the handshake.
        is_tool_post = request.method == "POST" and _MCP_METHOD.match(
            request.content[:512]
        )
        is_resume = request.method == "GET" and "last-event-id" in request.headers
        if is_tool_post or is_resume:
            _begin(request, TraceToolSource.MCP)


async def mcp_trace_response(response: httpx2.Response) -> None:
    attempt = cast(
        "RecordedHttpAttempt | None", response.request.extensions.pop(_ATTEMPT, None)
    )
    if attempt is not None:
        with suppress(Exception):
            attempt.headers(response)
            if response.is_stream_consumed:
                attempt.chunk(response.content)
                attempt.finish(body_complete=True)
            elif isinstance(response.stream, httpx2.AsyncByteStream):
                response.stream = _McpObservedStream(response.stream, attempt)
            else:
                attempt.finish(body_complete=False)


class _McpObservedStream(httpx2.AsyncByteStream):
    def __init__(
        self, stream: httpx2.AsyncByteStream, attempt: RecordedHttpAttempt
    ) -> None:
        self.stream = stream
        self.attempt = attempt

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.stream:
                self.attempt.chunk(chunk)
                yield chunk
        except Exception:
            self.attempt.finish(body_complete=False, failed=True)
            raise
        else:
            self.attempt.finish(body_complete=True)

    async def aclose(self) -> None:
        try:
            await self.stream.aclose()
        finally:
            self.attempt.finish(body_complete=False)
