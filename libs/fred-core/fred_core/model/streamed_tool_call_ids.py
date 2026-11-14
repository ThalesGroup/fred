# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Keep a streamed Chat Completions tool call attached to its original ID."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterator

import httpx

NORMALIZE_TOOL_CALL_IDS_SETTING = "normalize_streamed_tool_call_ids"
SKIP_TOOL_CALL_ID_NORMALIZATION_HEADER = "X-Fred-Skip-Tool-Call-Id-Normalization"
_SKIP_NORMALIZATION_EXTENSION = "fred.skip_tool_call_id_normalization"
_MAX_EVENT_BYTES = 256 * 1024
_MAX_CALL_INDEXES = 1024
_LINE_END = re.compile(rb"\r\n?|\n")


class _ToolCallEvents:
    def __init__(self) -> None:
        self._known_calls: set[tuple[int, int]] = set()
        self._frame = bytearray()
        self._oversized = False
        self._line_has_data = False
        self._pending_lf = False
        self._started = False

    def feed(self, chunk: bytes) -> Iterator[bytes]:
        if not chunk:
            return
        start = 0
        if self._pending_lf and chunk.startswith(b"\n"):
            if self._line_has_data or self._frame:
                yield from self._append(b"\n")
            else:
                yield b"\n"
            start = 1
        self._pending_lf = False

        for match in _LINE_END.finditer(chunk, start):
            blank_line = match.start() == start and not self._line_has_data
            yield from self._append(chunk[start : match.end()])
            self._line_has_data = False
            self._pending_lf = match.end() == len(chunk) and match[0] == b"\r"
            start = match.end()
            if blank_line:
                if self._frame:
                    frame = bytes(self._frame)
                    self._frame.clear()
                    yield self._normalize(frame)
                self._oversized = False
        if start < len(chunk):
            self._line_has_data = True
            yield from self._append(chunk[start:])

    def finish(self) -> Iterator[bytes]:
        if self._frame:
            yield bytes(self._frame)
            self._frame.clear()

    def _append(self, part: bytes) -> Iterator[bytes]:
        if self._oversized:
            yield part
        elif len(self._frame) + len(part) > _MAX_EVENT_BYTES:
            self._oversized = True
            self._known_calls.clear()
            yield from self.finish()
            yield part
        else:
            self._frame.extend(part)

    def _normalize(self, frame: bytes) -> bytes:
        first_frame = not self._started
        self._started = True
        if b"tool_calls" not in frame and b"\\u" not in frame:
            return frame
        lines = frame.splitlines(keepends=True)
        if first_frame and lines[0].startswith(b"\xef\xbb\xbf"):
            # Preserve the original bytes when forwarding a stream with a BOM.
            return frame
        data_lines = [
            index
            for index, line in enumerate(lines)
            if line.startswith(b"data:") or line.rstrip(b"\r\n") == b"data"
        ]
        if not data_lines:
            return frame
        data = b"\n".join(
            lines[index][5:].removeprefix(b" ").rstrip(b"\r\n") for index in data_lines
        )
        try:
            event = json.loads(data)
        except (ValueError, RecursionError):
            self._known_calls.clear()
            return frame

        if not self._normalize_calls(event):
            return frame
        try:
            payload = json.dumps(
                event, ensure_ascii=True, separators=(",", ":")
            ).encode()
        except (ValueError, RecursionError):
            self._known_calls.clear()
            return frame
        last = data_lines[-1]
        line = lines[last]
        ending = line[len(line.rstrip(b"\r\n")) :]
        lines[last] = b"data: " + payload + ending
        for index in data_lines[:-1]:
            # Keep a line between neighboring fields, even with mixed CR/LF.
            lines[index] = b":" + lines[index][len(lines[index].rstrip(b"\r\n")) :]
        return b"".join(lines)

    def _normalize_calls(self, event: object) -> bool:
        choices = event.get("choices") if isinstance(event, dict) else None
        if not isinstance(choices, list):
            return False
        changed = False
        for choice in choices:
            if not isinstance(choice, dict) or type(choice.get("index")) is not int:
                continue
            delta = choice.get("delta")
            calls = delta.get("tool_calls") if isinstance(delta, dict) else None
            if not isinstance(calls, list):
                continue
            prior_calls = (
                self._known_calls.copy() if len(calls) > 1 else self._known_calls
            )
            for call in calls:
                if not isinstance(call, dict) or type(call.get("index")) is not int:
                    continue
                key = (choice["index"], call["index"])
                call_id = call.get("id")
                function = call.get("function")
                if call_id == "null":
                    if (
                        key in prior_calls
                        and isinstance(function, dict)
                        and function.get("name") in (None, "")
                        and isinstance(function.get("arguments"), str)
                    ):
                        call["id"] = None
                        changed = True
                    else:
                        self._known_calls.discard(key)
                elif isinstance(call_id, str) and call_id:
                    if len(self._known_calls) < _MAX_CALL_INDEXES:
                        self._known_calls.add(key)
        return changed


def _should_normalize(request: httpx.Request) -> bool:
    # Move the SDK's per-model opt-out to an extension carried across redirects.
    if request.headers.pop(SKIP_TOOL_CALL_ID_NORMALIZATION_HEADER, None) is not None:
        request.extensions[_SKIP_NORMALIZATION_EXTENSION] = True
    return (
        request.method == "POST"
        and request.url.path.rstrip("/").endswith("/chat/completions")
        and not request.extensions.get(_SKIP_NORMALIZATION_EXTENSION)
    )


def _is_streamed_success(response: httpx.Response) -> bool:
    return (
        response.is_success
        and not response.is_stream_consumed
        and response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "text/event-stream"
    )


def _stream_response(
    request: httpx.Request,
    upstream: httpx.Response,
    stream: httpx.SyncByteStream | httpx.AsyncByteStream,
) -> httpx.Response:
    upstream.request = request
    headers = httpx.Headers(upstream.headers)
    headers.pop("content-encoding", None)
    headers.pop("content-length", None)
    return httpx.Response(
        upstream.status_code,
        headers=headers,
        stream=stream,
        extensions=upstream.extensions,
    )


class _NormalizedStream(httpx.SyncByteStream):
    def __init__(self, upstream: httpx.Response) -> None:
        self._upstream = upstream

    def __iter__(self) -> Iterator[bytes]:
        events = _ToolCallEvents()
        try:
            for chunk in self._upstream.iter_bytes():
                yield from events.feed(chunk)
            yield from events.finish()
        finally:
            self.close()

    def close(self) -> None:
        self._upstream.close()


class _AsyncNormalizedStream(httpx.AsyncByteStream):
    def __init__(self, upstream: httpx.Response) -> None:
        self._upstream = upstream
        self._iterator = self._iterate(upstream)

    def __aiter__(self) -> AsyncIterator[bytes]:
        # The SDK can resume at [DONE] to drain an HTTP/1.1 connection.
        return self._iterator

    @staticmethod
    async def _iterate(upstream: httpx.Response) -> AsyncIterator[bytes]:
        events = _ToolCallEvents()
        try:
            async for chunk in upstream.aiter_bytes():
                for frame in events.feed(chunk):
                    yield frame
            for frame in events.finish():
                yield frame
        finally:
            await upstream.aclose()

    async def aclose(self) -> None:
        # HTTPX's default transport shields pool cleanup from cancellation.
        await self._upstream.aclose()


class ToolCallIdTransport(httpx.BaseTransport):
    def __init__(self, upstream: httpx.BaseTransport) -> None:
        self._upstream = upstream

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        normalize = _should_normalize(request)
        response = self._upstream.handle_request(request)
        if normalize and _is_streamed_success(response):
            return _stream_response(request, response, _NormalizedStream(response))
        return response

    def close(self) -> None:
        self._upstream.close()


class AsyncToolCallIdTransport(httpx.AsyncBaseTransport):
    def __init__(self, upstream: httpx.AsyncBaseTransport) -> None:
        self._upstream = upstream

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        normalize = _should_normalize(request)
        response = await self._upstream.handle_async_request(request)
        if normalize and _is_streamed_success(response):
            return _stream_response(request, response, _AsyncNormalizedStream(response))
        return response

    async def aclose(self) -> None:
        await self._upstream.aclose()
