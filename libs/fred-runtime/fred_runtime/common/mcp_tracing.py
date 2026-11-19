# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Measure actual MCP HTTP transport, including streamed response lifetime."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx2
from fred_core.portable.observability import get_tracer
from fred_core.technical_tracing import (
    TechnicalSpan,
    TechnicalTracer,
    activate_span,
    trace_headers,
)


class _TracedStream(httpx2.AsyncByteStream):
    def __init__(self, stream: httpx2.AsyncByteStream, span: TechnicalSpan):
        self.stream = stream
        self.span = span
        self.ended = False

    def _end(self) -> None:
        if not self.ended:
            self.ended = True
            self.span.end()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.stream:
                yield chunk
        except asyncio.CancelledError:
            self.span.set_attribute("status", "cancelled")
            raise
        except BaseException:
            self.span.set_attribute("status", "error")
            raise
        finally:
            self._end()

    async def aclose(self) -> None:
        try:
            await self.stream.aclose()
        except BaseException:
            self.span.set_attribute("status", "error")
            raise
        finally:
            self._end()


class TracedMCPClient(httpx2.AsyncClient):
    async def _send_single_request(self, request: httpx2.Request) -> httpx2.Response:
        # This HTTPX seam is below auth/retries and above transport selection.
        # Let the client retain its proxy/NO_PROXY, TLS and pool configuration;
        # supplying an explicit transport would disable environment proxies.
        tracer = get_tracer()
        if not isinstance(tracer, TechnicalTracer):
            return await super()._send_single_request(request)
        span = tracer.open_span("mcp.http")
        try:
            with activate_span(span):
                request.headers.update(trace_headers())
                response = await super()._send_single_request(request)
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 400:
                span.set_attribute("status", "error")
            assert isinstance(response.stream, httpx2.AsyncByteStream)
            response.stream = _TracedStream(response.stream, span)
            return response
        except asyncio.CancelledError:
            span.set_attribute("status", "cancelled")
            span.end()
            raise
        except BaseException:
            span.set_attribute("status", "error")
            span.end()
            raise
