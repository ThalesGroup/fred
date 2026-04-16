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
Drop-in replacement for V2SessionAgent that executes in a remote pod.

Why this module exists:
- agentic-backend's orchestrator calls `agent.astream_updates()` regardless of
  whether the agent runs locally or in a remote pod
- this class satisfies that interface by opening an SSE connection to the pod,
  reading RuntimeEvent frames, and translating them into the same legacy event
  format that the local V2SessionAgent produces
- no LangGraph state, no local runtime, no checkpointer — the pod is stateless

How to use it:
- instantiate from AgentFactory when AgentSettings.remote_endpoint_url is set
- wire as a drop-in replacement for V2SessionAgent in the existing cache

Example:
    agent = RemoteV2SessionAgent(
        agent_id="rags.sample.echo",
        name="RAGS Sample Echo",
        binding=binding,
        endpoint_url="http://rags-v2:8000/api/v1/agents/execute/stream",
    )
    async for event in agent.astream_updates(state, stream_mode=["messages", "updates"]):
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.runnables import RunnableConfig

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    FinalRuntimeEvent,
    NodeErrorRuntimeEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from fred_sdk.runtime_support.remote_agent_invoker import (
    _iter_sse_events,
    _parse_runtime_event,
)

logger = logging.getLogger(__name__)


class RemoteV2SessionAgent:
    """
    V2SessionAgent-compatible adapter for agents running in a remote pod.

    Satisfies the same duck-type interface as V2SessionAgent so that
    AgentFactory, AgentCache, and SessionOrchestrator require no changes
    beyond the factory short-circuit that instantiates this class.

    Thread-safety:
    - one instance is created per (session_id, agent_id) cache entry
    - `rebind()` updates the binding for multi-turn token/context refresh
    - the httpx client is created fresh per `astream_updates()` call;
      no shared mutable state across concurrent calls
    """

    def __init__(
        self,
        *,
        agent_id: str,
        name: str | None,
        binding: BoundRuntimeContext,
        endpoint_url: str,
        token_provider: Callable[[], str] | None = None,
        connect_timeout_s: float = 5.0,
        read_timeout_s: float | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._name = name
        self._binding = binding
        self._endpoint_url = endpoint_url
        self._token_provider = token_provider
        self._connect_timeout_s = connect_timeout_s
        self._read_timeout_s = read_timeout_s

    # ------------------------------------------------------------------
    # V2SessionAgent interface
    # ------------------------------------------------------------------

    def get_id(self) -> str:
        return self._agent_id

    @property
    def binding(self) -> BoundRuntimeContext:
        return self._binding

    @property
    def streaming_memory(self):
        """Remote agents have no local checkpointer."""
        return None

    def rebind(self, binding: BoundRuntimeContext) -> None:
        """
        Refresh binding on multi-turn reuse (token refresh, context update).

        Why: agentic-backend rebinds cached agents on every request to
        propagate updated auth tokens and session context.
        """
        self._binding = binding

    async def astream_updates(
        self,
        state: Any,
        *,
        config: RunnableConfig | None = None,
        stream_mode: Any = "updates",
        **kwargs: Any,
    ):
        """
        Stream legacy chat events by proxying execution to the remote pod.

        The latest human message is extracted from `state["messages"]` and
        forwarded to the pod's SSE endpoint. Incoming RuntimeEvent frames are
        translated to the same legacy event format that V2SessionAgent produces,
        so the orchestrator's streaming pipeline is unaffected.
        """
        message = _latest_human_text(state)
        if not message:
            logger.warning(
                "[RemoteV2SessionAgent] No human message found in state for agent=%s",
                self._agent_id,
            )
            return

        ctx = self._binding.runtime_context
        portable = self._binding.portable_context

        payload = {
            "agent_id": self._agent_id,
            "message": message,
            "context": {
                "session_id": ctx.session_id or portable.session_id,
                "user_id": ctx.user_id or portable.user_id,
                "correlation_id": portable.correlation_id,
                "tenant": portable.tenant,
                "language": ctx.language,
            },
        }

        requested_modes = _requested_stream_modes(stream_mode)
        timeout = httpx.Timeout(
            connect=self._connect_timeout_s,
            read=self._read_timeout_s,
            write=30.0,
            pool=self._connect_timeout_s,
        )

        logger.debug(
            "[RemoteV2SessionAgent] streaming agent=%s url=%s session=%s",
            self._agent_id,
            self._endpoint_url,
            ctx.session_id,
        )

        headers: dict[str, str] = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        # Prefer the user's JWT from the binding (forwarded from agentic-backend).
        # Fall back to token_provider (M2M or other) when no user token is present
        # (e.g. system/scheduled calls without a user context).
        token: str | None = ctx.access_token or None
        if not token and self._token_provider is not None:
            try:
                token = self._token_provider()
            except Exception:
                logger.warning(
                    "[RemoteV2SessionAgent] Failed to obtain token for agent=%s — sending unauthenticated",
                    self._agent_id,
                    exc_info=True,
                )
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                self._endpoint_url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="ignore")
                    logger.error(
                        "[RemoteV2SessionAgent] pod returned %d: %s",
                        response.status_code,
                        detail,
                    )
                    yield {
                        "agent": {
                            "messages": [
                                AIMessage(
                                    content=f"Remote agent error {response.status_code}: {detail}"
                                )
                            ]
                        }
                    }
                    return

                async for sse_event in _iter_sse_events(response.aiter_lines()):
                    if not sse_event.data:
                        continue
                    runtime_event = _parse_runtime_event(sse_event.data)
                    if runtime_event is None:
                        continue
                    for legacy_event in _to_legacy_events(
                        runtime_event, requested_modes=requested_modes
                    ):
                        yield legacy_event

    async def aclose(self) -> None:
        """No persistent resources to close for remote agents."""
        pass


# ------------------------------------------------------------------
# Event translation — RuntimeEvent → legacy astream_updates format
# (mirrors _legacy_events_from_runtime_event in session_agent.py)
# ------------------------------------------------------------------


def _to_legacy_events(event: Any, *, requested_modes: frozenset[str]) -> list[object]:
    if isinstance(event, AssistantDeltaRuntimeEvent):
        if "messages" not in requested_modes:
            return []
        return [
            (
                "messages",
                (
                    AIMessageChunk(content=event.delta),
                    {"langgraph_node": "agent"},
                ),
            )
        ]

    if isinstance(event, AwaitingHumanRuntimeEvent):
        if "updates" not in requested_modes:
            return []
        payload = event.request.model_dump(mode="json", exclude_none=True)
        payload.pop("choices", None) if payload.get("choices") == [] else None
        payload.pop("metadata", None) if payload.get("metadata") == {} else None
        return [{"__interrupt__": {"value": payload}}]

    if "updates" not in requested_modes:
        return []

    if isinstance(event, ToolCallRuntimeEvent):
        return [
            {
                "agent": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "id": event.call_id,
                                    "name": event.tool_name,
                                    "args": event.arguments,
                                }
                            ],
                        )
                    ]
                }
            }
        ]

    if isinstance(event, ToolResultRuntimeEvent):
        response_metadata: dict[str, object] = {}
        if event.sources:
            response_metadata["sources"] = [
                s.model_dump(mode="json") for s in event.sources
            ]
        if event.is_error:
            response_metadata["ok"] = False
        additional_kwargs: dict[str, object] = {}
        if event.ui_parts:
            additional_kwargs["fred_parts"] = [
                p.model_dump(mode="json")
                for p in event.ui_parts  # type: ignore[union-attr]
            ]
        return [
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content=event.content,
                            tool_call_id=event.call_id,
                            name=event.tool_name,
                            additional_kwargs=additional_kwargs,
                            response_metadata=response_metadata,
                        )
                    ]
                }
            }
        ]

    if isinstance(event, FinalRuntimeEvent):
        response_metadata = {}
        if event.sources:
            response_metadata["sources"] = [
                s.model_dump(mode="json") for s in event.sources
            ]
        if event.model_name:
            response_metadata["model_name"] = event.model_name
        if event.token_usage is not None:
            response_metadata["token_usage"] = dict(event.token_usage)
        if event.finish_reason is not None:
            response_metadata["finish_reason"] = event.finish_reason
        additional_kwargs = {}
        if event.ui_parts:
            additional_kwargs["fred_parts"] = [
                p.model_dump(mode="json")
                for p in event.ui_parts  # type: ignore[union-attr]
            ]
        return [
            {
                "agent": {
                    "messages": [
                        AIMessage(
                            content=event.content,
                            additional_kwargs=additional_kwargs,
                            response_metadata=response_metadata,
                        )
                    ]
                }
            }
        ]

    if isinstance(event, NodeErrorRuntimeEvent):
        return [
            {
                "agent": {
                    "messages": [
                        AIMessage(content=f"Agent error: {event.error_message}")
                    ]
                }
            }
        ]

    return []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _latest_human_text(state: Any) -> str | None:
    """Extract the latest human message text from astream_updates state."""
    if not isinstance(state, dict):
        return None
    raw_messages = state.get("messages")
    if not isinstance(raw_messages, list):
        return None
    for message in reversed(raw_messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # multimodal content blocks
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return str(block.get("text", ""))
    return None


def _requested_stream_modes(stream_mode: object) -> frozenset[str]:
    if isinstance(stream_mode, str):
        return frozenset({stream_mode})
    if isinstance(stream_mode, (list, tuple, set)):
        modes = {m for m in stream_mode if isinstance(m, str)}
        if modes:
            return frozenset(modes)
    return frozenset({"updates"})
