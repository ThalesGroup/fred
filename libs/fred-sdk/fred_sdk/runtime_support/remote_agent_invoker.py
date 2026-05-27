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
"""
Remote HTTP/SSE agent invoker for the v2 runtime port.

Why this module exists:
- remote agent pods stream RuntimeEvent payloads over HTTP/SSE
- graph nodes need a concrete AgentInvokerPort implementation that can
  consume those streams and return AgentInvocationResult

How to use it:
- create a RemoteSseAgentInvoker with the target endpoint URL
- inject it into RuntimeServices.agent_invoker
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Mapping

import httpx
from pydantic import TypeAdapter

from ..contracts.context import AgentInvocationRequest, AgentInvocationResult
from ..contracts.runtime import (
    AgentInvokerPort,
    AssistantDeltaRuntimeEvent,
    FinalRuntimeEvent,
    NodeErrorRuntimeEvent,
    RuntimeEvent,
)


@dataclass(frozen=True, slots=True)
class RemoteSseAgentInvokerConfig:
    """
    Configuration for RemoteSseAgentInvoker.

    Why this exists:
    - remote agent endpoints vary by deployment (agentic backend, worker pod)
    - timeouts and headers must be configurable without subclassing

    How to use it:
    - pass a full `endpoint_url` for the SSE stream
    - set timeouts to align with your streaming SLA

    Example:
    ```python
    config = RemoteSseAgentInvokerConfig(
        endpoint_url="https://agents.example.com/v2/execute/stream",
        connect_timeout_s=5.0,
        read_timeout_s=None,
    )
    ```
    """

    endpoint_url: str
    connect_timeout_s: float = 5.0
    read_timeout_s: float | None = None
    write_timeout_s: float = 30.0
    pool_timeout_s: float = 5.0
    headers: dict[str, str] = field(default_factory=dict)

    def build_timeout(self) -> httpx.Timeout:
        """
        Build a streaming-friendly httpx.Timeout.

        Why this exists:
        - SSE connections often run longer than default read timeouts
        - we want a single place to keep timeout semantics consistent

        How to use it:
        - call from RemoteSseAgentInvoker before opening the stream
        """

        return httpx.Timeout(
            connect=self.connect_timeout_s,
            read=self.read_timeout_s,
            write=self.write_timeout_s,
            pool=self.pool_timeout_s,
        )


@dataclass(frozen=True, slots=True)
class _SseEvent:
    """
    Parsed SSE event buffer.

    Why this exists:
    - SSE events arrive as line-based fields; we assemble them into one record
    - downstream parsing only needs `event` and `data`
    """

    event: str | None
    data: str


_RUNTIME_EVENT_ADAPTER = TypeAdapter(RuntimeEvent)


async def _iter_sse_events(lines: AsyncIterator[str]) -> AsyncIterator[_SseEvent]:
    """
    Parse an SSE byte/line stream into discrete events.

    Why this exists:
    - httpx yields raw lines, but SSE uses multi-line events separated by blanks
    - the invoker needs a small, dependency-free parser for streaming JSON

    How to use it:
    - feed it `response.aiter_lines()`
    - it yields `_SseEvent(event, data)` for each complete SSE event
    """

    event_name: str | None = None
    data_lines: list[str] = []

    async for line in lines:
        if line == "":
            if data_lines:
                yield _SseEvent(event=event_name, data="\n".join(data_lines))
            event_name = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]

        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    if data_lines:
        yield _SseEvent(event=event_name, data="\n".join(data_lines))


def _parse_runtime_event(payload: str) -> RuntimeEvent | None:
    """
    Decode an SSE JSON payload into a RuntimeEvent.

    Why this exists:
    - remote agent pods stream RuntimeEvent JSON; this adapter normalizes it

    How to use it:
    - pass the `data` field from `_SseEvent`
    - returns None when payload is not a RuntimeEvent-compatible JSON blob
    """

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return None
    try:
        return _RUNTIME_EVENT_ADAPTER.validate_python(raw)
    except Exception:
        return None


class RemoteSseAgentInvoker(AgentInvokerPort):
    """
    AgentInvokerPort implementation that consumes a remote SSE stream.

    Why this exists:
    - graph nodes can call agents that live in other pods/services
    - SSE keeps streaming over plain HTTP without WebSocket infrastructure

    How to use it:
    ```python
    invoker = RemoteSseAgentInvoker(
        config=RemoteSseAgentInvokerConfig(
            endpoint_url="https://agents.example.com/v2/execute/stream",
        )
    )
    services = RuntimeServices(agent_invoker=invoker)
    ```
    """

    def __init__(
        self,
        *,
        config: RemoteSseAgentInvokerConfig,
        header_provider: Callable[[AgentInvocationRequest], Mapping[str, str]]
        | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the remote SSE invoker.

        Why this exists:
        - callers often need to attach auth headers per request
        - sharing a client lets the platform reuse connection pools

        How to use it:
        - pass `header_provider` to inject auth headers using the request
        - pass `client` if you want to manage the AsyncClient lifecycle
        """

        self._config = config
        self._header_provider = header_provider
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        """
        Close any internally managed HTTP client.

        Why this exists:
        - RemoteSseAgentInvoker owns the AsyncClient when one is not provided

        How to use it:
        - call from application shutdown hooks when this invoker owns the client
        """

        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        """
        Invoke a remote agent via SSE and return the final result.

        Why this exists:
        - GraphNodeContext.invoke_agent requires a transport-agnostic invoker
        - SSE provides a lightweight streaming path for remote agents

        How to use it:
        - call through GraphNodeContext.invoke_agent
        - the invoker aggregates RuntimeEvent streams until FinalRuntimeEvent
        """

        payload: dict[str, object] = {
            "agent_id": request.agent_id,
            "message": request.message,
            "context": request.context.model_dump(),
        }
        if request.prior_turns:
            payload["invocation_turns"] = [t.model_dump() for t in request.prior_turns]
        headers = self._build_headers(request)
        timeout = self._config.build_timeout()

        client = self._client or httpx.AsyncClient(timeout=timeout)
        if self._client is None:
            self._client = client

        streamed_chunks: list[str] = []
        error_message: str | None = None

        try:
            async with client.stream(
                "POST",
                self._config.endpoint_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="ignore")
                    return AgentInvocationResult(
                        agent_id=request.agent_id,
                        content=f"Remote agent error {response.status_code}: {detail}",
                        is_error=True,
                    )

                async for event in _iter_sse_events(response.aiter_lines()):
                    if not event.data:
                        continue
                    runtime_event = _parse_runtime_event(event.data)
                    if runtime_event is None:
                        streamed_chunks.append(event.data)
                        continue

                    if isinstance(runtime_event, AssistantDeltaRuntimeEvent):
                        streamed_chunks.append(runtime_event.delta)
                    elif isinstance(runtime_event, NodeErrorRuntimeEvent):
                        error_message = runtime_event.error_message
                    elif isinstance(runtime_event, FinalRuntimeEvent):
                        return AgentInvocationResult(
                            agent_id=request.agent_id,
                            content=runtime_event.content,
                            sources=runtime_event.sources,
                            ui_parts=runtime_event.ui_parts,
                            is_error=False,
                        )

        except Exception as exc:
            return AgentInvocationResult(
                agent_id=request.agent_id,
                content=f"Remote agent invocation failed: {exc}",
                is_error=True,
            )
        finally:
            if self._owns_client:
                await client.aclose()
                if self._client is client:
                    self._client = None

        if error_message is not None:
            return AgentInvocationResult(
                agent_id=request.agent_id,
                content=error_message,
                is_error=True,
            )

        if streamed_chunks:
            return AgentInvocationResult(
                agent_id=request.agent_id,
                content="".join(streamed_chunks),
                is_error=True,
            )

        return AgentInvocationResult(
            agent_id=request.agent_id,
            content="Remote agent stream ended without a final event.",
            is_error=True,
        )

    def _build_headers(self, request: AgentInvocationRequest) -> dict[str, str]:
        """
        Build request headers for the SSE call.

        Why this exists:
        - callers may add auth headers per invocation via `header_provider`

        How to use it:
        - it is called internally by invoke(); override via `header_provider`
        """

        headers = dict(self._config.headers)
        headers.setdefault("Accept", "text/event-stream")
        headers.setdefault("Content-Type", "application/json")

        if self._header_provider is not None:
            headers.update(self._header_provider(request))

        return headers
