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
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol
from weakref import WeakMethod

import httpx

if TYPE_CHECKING:
    import httpx2
else:
    try:
        import httpx2
    except ImportError:
        # Older Anthropic versions use HTTPX and need no separate backend.
        httpx2 = httpx

HttpRequest = httpx.Request | httpx2.Request
HttpResponse = httpx.Response | httpx2.Response


class HttpAttempt(Protocol):
    @property
    def remaining_budget(self) -> int: ...

    def headers(self, response: HttpResponse) -> None: ...
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
    def begin(self, request: HttpRequest) -> HttpAttempt | None: ...


active_http_capture: ContextVar[HttpCapture | None] = ContextVar(
    "active_conversation_http_capture", default=None
)


def start_http_attempt(request: HttpRequest) -> HttpAttempt | None:
    capture = active_http_capture.get()
    if capture is not None:
        with suppress(Exception):
            return capture.begin(request)
    return None


def observe_http_response(
    response: HttpResponse,
    attempt: HttpAttempt,
    *,
    asynchronous: bool,
    capture_sse: bool = False,
) -> None:
    attempt.headers(response)
    capture_sse = capture_sse and is_sse_response(response)
    if capture_sse:
        attempt.normalization_started(enabled=False)
    if response.is_stream_consumed:
        attempt.chunk(response.content)
        attempt.sse_chunk(response.content)
        attempt.finish_sse()
        attempt.finish(body_complete=True)
    elif asynchronous and isinstance(
        response.stream, (httpx.AsyncByteStream, httpx2.AsyncByteStream)
    ):
        stream_type = (
            _AsyncObservedStream
            if isinstance(response, httpx.Response)
            else _AsyncObservedStream2
        )
        stream = stream_type(
            response.stream,
            attempt,
            capture_discarded_error=response.status_code >= 400,
            capture_sse=capture_sse,
        )
        setattr(response, "stream", stream)
        if capture_sse:
            response.aiter_bytes = _observe_async_sse(response.aiter_bytes, stream)
    elif isinstance(response.stream, (httpx.SyncByteStream, httpx2.SyncByteStream)):
        sync_stream_type = (
            _ObservedStream
            if isinstance(response, httpx.Response)
            else _ObservedStream2
        )
        stream_sync = sync_stream_type(
            response.stream, attempt, capture_sse=capture_sse
        )
        setattr(response, "stream", stream_sync)
        if capture_sse:
            response.iter_bytes = _observe_sse(response.iter_bytes, stream_sync)
    else:
        attempt.finish(body_complete=False)


def is_sse_response(response: HttpResponse) -> bool:
    return (
        response.is_success
        and response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "text/event-stream"
    )


def _observe_sse(
    iter_bytes: Callable[..., Iterator[bytes]], stream: _ObservedStream
) -> Callable[..., Iterator[bytes]]:
    original = WeakMethod(iter_bytes)

    def observe(chunk_size: int | None = None) -> Iterator[bytes]:
        iterator = original()
        assert iterator is not None
        stream.reading_sse = True
        try:
            for data in iterator(chunk_size):
                stream.attempt.sse_chunk(data)
                yield data
        except Exception as exc:
            stream.attempt.finish_sse(exc)
            raise
        finally:
            stream.attempt.finish_sse()

    return observe


def _observe_async_sse(
    iter_bytes: Callable[..., AsyncIterator[bytes]], stream: _AsyncObservedStream
) -> Callable[..., AsyncGenerator[bytes, None]]:
    original = WeakMethod(iter_bytes)

    async def observe(chunk_size: int | None = None) -> AsyncGenerator[bytes, None]:
        iterator = original()
        assert iterator is not None
        stream.reading_sse = True
        try:
            async for data in iterator(chunk_size):
                stream.attempt.sse_chunk(data)
                yield data
        except Exception as exc:
            stream.attempt.finish_sse(exc)
            raise
        finally:
            stream.attempt.finish_sse()

    return observe


class _ObservedStream(httpx.SyncByteStream):
    def __init__(
        self,
        stream: httpx.SyncByteStream | httpx2.SyncByteStream,
        attempt: HttpAttempt,
        *,
        capture_sse: bool,
    ) -> None:
        self.stream = stream
        self.attempt = attempt
        self.capture_sse = capture_sse
        self.reading_sse = False
        self.body_complete = False

    def __iter__(self) -> Iterator[bytes]:
        try:
            for data in self.stream:
                self.attempt.chunk(data)
                yield data
        except Exception as exc:
            self.attempt.finish(body_complete=False, failed=True, error=exc)
            raise
        else:
            self.body_complete = True
            self.attempt.finish(body_complete=True)

    def close(self) -> None:
        try:
            self.stream.close()
        finally:
            self.attempt.finish(body_complete=False)
            if self.capture_sse and not (self.reading_sse and self.body_complete):
                self.attempt.finish_sse()


class _AsyncObservedStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: httpx.AsyncByteStream | httpx2.AsyncByteStream,
        attempt: HttpAttempt,
        *,
        capture_discarded_error: bool,
        capture_sse: bool,
    ) -> None:
        self.stream = stream
        self.attempt = attempt
        self.capture_discarded_error = capture_discarded_error
        self.capture_sse = capture_sse
        self.entered = False
        self.reading_sse = False
        self.body_complete = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.entered = True
        try:
            async for data in self.stream:
                self.attempt.chunk(data)
                yield data
        except Exception as exc:
            self.attempt.finish(body_complete=False, failed=True, error=exc)
            raise
        else:
            self.body_complete = True
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
                if self.capture_sse and not (self.reading_sse and self.body_complete):
                    self.attempt.finish_sse()

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


class _ObservedStream2(_ObservedStream, httpx2.SyncByteStream):
    pass


class _AsyncObservedStream2(_AsyncObservedStream, httpx2.AsyncByteStream):
    pass


def observe_httpx_client(
    client: httpx.Client | httpx.AsyncClient | httpx2.Client | httpx2.AsyncClient,
) -> None:
    """Observe SDK-owned clients without replacing their selected transports."""
    # HTTPX event hooks lack a transport-error hook. This boundary runs after
    # auth/request hooks, once per send, and before any response body is read.
    if isinstance(client, (httpx.AsyncClient, httpx2.AsyncClient)):
        send = client._send_single_request
        if not getattr(send, "_fred_observed", False):
            observed = _observe_async_send(send)
            setattr(observed, "_fred_observed", True)
            setattr(client, "_send_single_request", observed)
    else:
        send_sync = client._send_single_request
        if not getattr(send_sync, "_fred_observed", False):
            observed_sync = _observe_send(send_sync)
            setattr(observed_sync, "_fred_observed", True)
            setattr(client, "_send_single_request", observed_sync)


def _observe_send(
    send: Callable[..., HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    original = WeakMethod(send)

    def observe(request: HttpRequest) -> HttpResponse:
        attempt = start_http_attempt(request)
        sender = original()
        assert sender is not None
        try:
            response = sender(request)
        except Exception as exc:
            if attempt is not None:
                attempt.finish(body_complete=False, failed=True, error=exc)
            raise
        if attempt is not None:
            with suppress(Exception):
                observe_http_response(
                    response, attempt, asynchronous=False, capture_sse=True
                )
        return response

    return observe


def _observe_async_send(
    send: Callable[..., Awaitable[HttpResponse]],
) -> Callable[[HttpRequest], Awaitable[HttpResponse]]:
    original = WeakMethod(send)

    async def observe(request: HttpRequest) -> HttpResponse:
        attempt = start_http_attempt(request)
        sender = original()
        assert sender is not None
        try:
            response = await sender(request)
        except Exception as exc:
            if attempt is not None:
                attempt.finish(body_complete=False, failed=True, error=exc)
            raise
        if attempt is not None:
            with suppress(Exception):
                observe_http_response(
                    response, attempt, asynchronous=True, capture_sse=True
                )
        return response

    return observe
