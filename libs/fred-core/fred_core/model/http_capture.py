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


"""Passively observe one provider transport attempt without consuming its stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextvars import ContextVar
from typing import Protocol

import httpx


class HttpAttempt(Protocol):
    @property
    def remaining_budget(self) -> int: ...

    def headers(self, response: httpx.Response) -> None: ...
    def chunk(self, data: bytes) -> None: ...
    def finish(
        self,
        *,
        body_complete: bool,
        failed: bool = False,
        error: Exception | None = None,
    ) -> None: ...
    def sse_chunk(self, data: bytes) -> None: ...
    def finish_sse(self, error: Exception | None = None) -> None: ...
    def normalization_started(self, *, enabled: bool) -> None: ...
    def normalization_rewrites(
        self, frame_index: int, changes: list[tuple[int, int, str]]
    ) -> None: ...


class HttpCapture(Protocol):
    def begin(self, request: httpx.Request) -> HttpAttempt | None: ...


active_http_capture: ContextVar[HttpCapture | None] = ContextVar(
    "active_conversation_http_capture", default=None
)


def start_http_attempt(request: httpx.Request) -> HttpAttempt | None:
    capture = active_http_capture.get()
    return capture.begin(request) if capture is not None else None


def observe_http_response(
    response: httpx.Response, attempt: HttpAttempt, *, asynchronous: bool
) -> None:
    attempt.headers(response)
    if response.is_stream_consumed:
        attempt.chunk(response.content)
        attempt.sse_chunk(response.content)
        attempt.finish_sse()
        attempt.finish(body_complete=True)
    elif asynchronous and isinstance(response.stream, httpx.AsyncByteStream):
        response.stream = _AsyncObservedStream(
            response.stream,
            attempt,
            capture_discarded_error=response.status_code >= 400,
        )
    elif isinstance(response.stream, httpx.SyncByteStream):
        response.stream = _ObservedStream(response.stream, attempt)
    else:
        attempt.finish(body_complete=False)


class _ObservedStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, attempt: HttpAttempt) -> None:
        self.stream = stream
        self.attempt = attempt

    def __iter__(self) -> Iterator[bytes]:
        try:
            for data in self.stream:
                self.attempt.chunk(data)
                yield data
        except Exception:
            self.attempt.finish(body_complete=False, failed=True)
            raise
        else:
            self.attempt.finish(body_complete=True)

    def close(self) -> None:
        try:
            self.stream.close()
        finally:
            self.attempt.finish(body_complete=False)


class _AsyncObservedStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        attempt: HttpAttempt,
        *,
        capture_discarded_error: bool,
    ) -> None:
        self.stream = stream
        self.attempt = attempt
        self.capture_discarded_error = capture_discarded_error
        self.entered = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.entered = True
        try:
            async for data in self.stream:
                self.attempt.chunk(data)
                yield data
        except Exception:
            self.attempt.finish(body_complete=False, failed=True)
            raise
        else:
            self.attempt.finish(body_complete=True)

    async def aclose(self) -> None:
        try:
            if self.capture_discarded_error and not self.entered:
                await self._read_discarded_error()
        finally:
            try:
                await self.stream.aclose()
            finally:
                self.attempt.finish(body_complete=False)

    async def _read_discarded_error(self) -> None:
        # The async OpenAI SDK closes retryable responses without reading them.
        # A small deadline keeps evidence collection off the successful stream path.
        budget = self.attempt.remaining_budget
        if budget <= 0:
            return
        try:
            async with asyncio.timeout(0.15):
                async for data in self:
                    budget -= len(data)
                    if budget < 0:
                        break
        except Exception:
            # The SDK is discarding this body. A diagnostic read cannot fail its retry.
            self.attempt.finish(body_complete=False, failed=True)
