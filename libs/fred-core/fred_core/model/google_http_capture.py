# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Observe GenAI's existing HTTPX and aiohttp clients."""

from __future__ import annotations

from collections.abc import Awaitable
from contextlib import suppress
from contextvars import ContextVar
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakMethod

import aiohttp
import httpx
from aiohttp.tracing import (
    TraceRequestEndParams,
    TraceRequestExceptionParams,
    TraceRequestHeadersSentParams,
    TraceRequestRedirectParams,
)
from fred_core.model.http_capture import (
    HttpAttempt,
    active_http_capture,
    is_sse_response,
    observe_httpx_client,
    start_http_attempt,
)

if TYPE_CHECKING:
    from google.genai import Client

_genai_request_body: ContextVar[bytes | None] = ContextVar(
    "genai_request_body", default=None
)


def observe_google_genai(client: Client) -> None:
    # LangChain constructs HttpOptions internally. Injecting replacement clients
    # would disable the SDK's aiohttp or mTLS selection and ownership rules.
    api = client._api_client
    observe_httpx_client(api._httpx_client)
    observe_httpx_client(api._async_httpx_client)
    original = WeakMethod(api._get_aiohttp_session)

    async def get_session() -> Any:
        get = original()
        assert get is not None
        session = await get()
        if active_http_capture.get() is not None and isinstance(
            session, aiohttp.ClientSession
        ):
            _observe_session(session)
        return session

    api._get_aiohttp_session = get_session


def _observe_session(session: aiohttp.ClientSession) -> None:
    if _TRACE in session.trace_configs:
        return
    original = WeakMethod(session._request)

    async def request(method: str, url: Any, **kwargs: Any) -> aiohttp.ClientResponse:
        send = original()
        assert send is not None
        if active_http_capture.get() is None:
            return await send(method, url, **kwargs)
        # GenAI serializes chat requests to bytes before calling the session.
        data = kwargs.get("data")
        token = _genai_request_body.set(data if isinstance(data, bytes) else b"")
        try:
            return await send(method, url, **kwargs)
        finally:
            _genai_request_body.reset(token)

    session._request = request  # type: ignore[method-assign]
    session.trace_configs.append(_TRACE)


class _Observation(SimpleNamespace):
    def __init__(self, *, trace_request_ctx: Any) -> None:
        self.body = _genai_request_body.get()
        self.attempt: HttpAttempt | None = None
        self.redirected_response: aiohttp.ClientResponse | None = None

    def begin(
        self, params: TraceRequestHeadersSentParams | TraceRequestExceptionParams
    ) -> HttpAttempt | None:
        headers = [
            (name.encode(), value.encode()) for name, value in params.headers.items()
        ]
        body = b"" if params.method in {"GET", "HEAD"} else self.body
        return start_http_attempt(
            httpx.Request(params.method, str(params.url), headers=headers, content=body)
        )


async def _on_headers_sent(
    _session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: TraceRequestHeadersSentParams,
) -> None:
    if not isinstance(ctx, _Observation) or ctx.body is None:
        return
    with suppress(Exception):
        if ctx.attempt is not None:
            # aiohttp can retry a stale pooled connection internally.
            ctx.attempt.finish(body_complete=False, failed=True)
        ctx.attempt = ctx.begin(params)


async def _on_redirect(
    _session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: TraceRequestRedirectParams,
) -> None:
    if not isinstance(ctx, _Observation):
        return
    with suppress(Exception):
        attempt = ctx.attempt
        if attempt is not None:
            response = params.response
            attempt.headers(
                httpx.Response(response.status, headers=response.raw_headers)
            )
            attempt.finish(body_complete=False)
            ctx.attempt = None
            ctx.redirected_response = response


async def _on_response(
    _session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: TraceRequestEndParams,
) -> None:
    if not isinstance(ctx, _Observation) or ctx.redirected_response is params.response:
        return
    with suppress(Exception):
        attempt = ctx.attempt
        if attempt is not None:
            _observe_response(params.response, attempt)


async def _on_exception(
    _session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: TraceRequestExceptionParams,
) -> None:
    if not isinstance(ctx, _Observation) or ctx.body is None:
        return
    with suppress(Exception):
        attempt = ctx.attempt or ctx.begin(params)
        if attempt is not None:
            attempt.finish(
                body_complete=False,
                failed=True,
                error=params.exception
                if isinstance(params.exception, Exception)
                else None,
            )


def _observe_response(response: aiohttp.ClientResponse, attempt: HttpAttempt) -> None:
    headers = httpx.Response(response.status, headers=response.raw_headers)
    attempt.headers(headers)
    sse = is_sse_response(headers)
    if sse:
        attempt.normalization_started(enabled=False)
    content = response.content
    if content.at_eof():
        if sse:
            attempt.finish_sse()
        attempt.finish(body_complete=True)
    else:
        # aiohttp's response-chunk hook only fires for ClientResponse.read().
        # GenAI's streaming parser consumes raw lines directly from the reader.
        response.content = cast(
            "aiohttp.StreamReader", _ObservedContent(content, attempt, sse)
        )


class _ObservedContent:
    def __init__(
        self, reader: aiohttp.StreamReader, attempt: HttpAttempt, sse: bool
    ) -> None:
        self._reader = reader
        self._attempt = attempt
        self._sse = sse

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)

    async def read(self, n: int = -1) -> bytes:
        return await self._observe(self._reader.read(n))

    async def readline(self, **kwargs: Any) -> bytes:
        return await self._observe(self._reader.readline(**kwargs))

    async def _observe(self, read: Awaitable[bytes]) -> bytes:
        try:
            data = await read
        except Exception as exc:
            self._finish(complete=False, error=exc)
            raise
        self._attempt.chunk(data)
        if self._sse:
            self._attempt.sse_chunk(data)
        if self._reader.at_eof():
            self._finish(complete=True)
        return data

    def set_exception(self, exc: BaseException, *args: Any) -> None:
        # ClientResponse.release() closes its reader even after a successful read.
        self._finish(complete=self._reader.at_eof())
        self._reader.set_exception(exc, *args)

    def _finish(self, *, complete: bool, error: Exception | None = None) -> None:
        if self._sse:
            self._attempt.finish_sse(error)
        self._attempt.finish(
            body_complete=complete, failed=error is not None, error=error
        )


_TRACE = aiohttp.TraceConfig(trace_config_ctx_factory=_Observation)
_TRACE.on_request_headers_sent.append(_on_headers_sent)
_TRACE.on_request_redirect.append(_on_redirect)
_TRACE.on_request_end.append(_on_response)
_TRACE.on_request_exception.append(_on_exception)
_TRACE.freeze()
