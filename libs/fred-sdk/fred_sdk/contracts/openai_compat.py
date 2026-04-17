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
OpenAI-compatible chat completions contract types and event transformer.

Why this module exists:
- Fred agent pods can optionally expose /v1/chat/completions, compatible with
  OpenAI and any OpenAI-protocol frontend (Open WebUI, openai-python SDK, etc.)
- Fred-specific metadata (sources, citations, HITL, errors) travels in a `fred`
  top-level key on each SSE chunk; standard OpenAI clients silently ignore
  unknown top-level fields, so this is fully backward-compatible

How to use:
- `fred_event_to_openai_chunk(event, completion_id, model, created)` transforms
  one RuntimeEvent dict (as yielded by the agent stream) into an OpenAI chunk
- returns None for events that should be dropped (e.g. status events)

Example:
    chunk = fred_event_to_openai_chunk(event, "chatcmpl-abc", "my-agent", 1234567890)
    if chunk is not None:
        yield f"data: {chunk.model_dump_json(exclude_none=True)}\\n\\n"
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class OpenAIMessage(BaseModel):
    """One message in an OpenAI chat completions request."""

    role: Literal["system", "user", "assistant"]
    content: str


class OpenAIChatRequest(BaseModel):
    """
    OpenAI /v1/chat/completions request body accepted by Fred.

    `model` maps to a registered Fred agent_id.
    `messages` must contain at least one user message; the last user message
    is forwarded to the agent as the turn input.
    `stream` is always True — non-streaming is not supported by this endpoint.

    Fred extensions via HTTP headers (ignored by standard clients):
    - X-Fred-Session-Id: session_id for multi-turn continuity (LangGraph checkpointer)
    - X-Fred-Team-Id: team_id for scoped tool and knowledge access
    """

    model: str
    messages: list[OpenAIMessage] = Field(..., min_length=1)
    stream: bool = True


# ---------------------------------------------------------------------------
# Fred metadata extension
# ---------------------------------------------------------------------------


class FredSourceRef(BaseModel):
    """
    Serializable citation reference derived from a VectorSearchHit.

    Why this is a separate model (not VectorSearchHit directly):
    - VectorSearchHit is a fred-core internal type with ~25 fields
    - OpenAI clients and frontends only need a small, stable citation shape
    - this model is the stable public representation for the `fred.sources` list

    Fields:
    - title: human-readable document title
    - uid: document UID for deep linking
    - page: page number within the document (when available)
    - score: similarity score from vector search
    - citation_url: direct link to the relevant passage (e.g. /documents/{uid}#chunk=...)
    """

    title: str | None = None
    uid: str | None = None
    page: int | None = None
    score: float | None = None
    citation_url: str | None = None


class FredChunkMetadata(BaseModel):
    """
    Fred-specific metadata carried in the top-level `fred` field of each SSE chunk.

    Standard OpenAI clients ignore unknown top-level fields; Fred-aware clients
    (e.g. the Fred frontend, a custom Open WebUI plugin) read this field to
    display citations, HITL prompts, and error banners inline.

    Fields:
    - sources: knowledge citations attached to the answer (populated on
      tool_result and final events)
    - awaiting_human: present on the final chunk when the agent is paused and
      needs user input to resume (HITL); contains the HumanInputRequest payload
    - node_error: short error description when a graph node failed with on_error
      routing; the UI should render this as a warning banner, not an answer
    - token_usage: input/output token counts from the final event
    """

    sources: list[FredSourceRef] = Field(default_factory=list)
    awaiting_human: dict[str, Any] | None = None
    node_error: str | None = None
    token_usage: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# OpenAI chunk models
# ---------------------------------------------------------------------------


class OpenAIDelta(BaseModel):
    """Content delta within one SSE chunk choice."""

    role: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class OpenAIChoice(BaseModel):
    """One choice (index 0) inside an OpenAI chat.completion.chunk."""

    index: int = 0
    delta: OpenAIDelta
    finish_reason: str | None = None


class OpenAICompletionChunk(BaseModel):
    """
    One SSE data line in the OpenAI chat.completion.chunk stream.

    The `fred` field is a Fred extension: it carries citations, HITL requests,
    and error context. Standard OpenAI clients ignore it.
    """

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[OpenAIChoice]
    fred: FredChunkMetadata | None = None


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------


def fred_event_to_openai_chunk(
    event: dict[str, Any],
    completion_id: str,
    model: str,
    created: int,
) -> OpenAICompletionChunk | None:
    """
    Map one Fred RuntimeEvent dict to an OpenAI chat.completion.chunk.

    Returns None for events that should be silently dropped (status events and
    any unknown kind).

    Why this function exists:
    - pure data transformation with no I/O: fully testable offline
    - centralised in fred-sdk so any Fred component speaking the OpenAI SSE
      protocol uses a single, typed, versioned mapping

    How to use:
    - call for each dict yielded by `_iterate_runtime_event_payloads`
    - serialise the returned chunk with `model_dump_json(exclude_none=True)`

    Event-to-chunk mapping:
    - assistant_delta  → content delta chunk
    - tool_call        → tool_calls chunk (full call in one shot, not streamed)
    - tool_result      → zero-content chunk carrying fred.sources when present
    - final            → finish_reason="stop" chunk with fred.sources + token_usage
    - awaiting_human   → finish_reason="stop" chunk with fred.awaiting_human
    - node_error       → finish_reason="stop" chunk with fred.node_error
    - status           → dropped (None)

    Example:
        chunk = fred_event_to_openai_chunk(event, "chatcmpl-123", "my-agent", 1700000000)
        if chunk is not None:
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\\n\\n"
    """
    kind = event.get("kind")

    if kind == "assistant_delta":
        return _make_chunk(
            completion_id,
            model,
            created,
            delta=OpenAIDelta(content=event.get("delta", "")),
        )

    if kind == "tool_call":
        # Emit the full tool call in one chunk (Fred delivers arguments atomically).
        tool_call: dict[str, Any] = {
            "index": 0,
            "id": event.get("call_id", ""),
            "type": "function",
            "function": {
                "name": event.get("tool_name", ""),
                "arguments": json.dumps(event.get("arguments", {})),
            },
        }
        return _make_chunk(
            completion_id,
            model,
            created,
            delta=OpenAIDelta(tool_calls=[tool_call]),
        )

    if kind == "tool_result":
        sources = _extract_sources(event.get("sources", []))
        fred = FredChunkMetadata(sources=sources) if sources else None
        # Zero-content delta — carries fred.sources metadata only.
        return _make_chunk(
            completion_id,
            model,
            created,
            delta=OpenAIDelta(),
            fred=fred,
        )

    if kind == "final":
        sources = _extract_sources(event.get("sources", []))
        return _make_chunk(
            completion_id,
            model,
            created,
            delta=OpenAIDelta(),
            finish_reason=event.get("finish_reason") or "stop",
            fred=FredChunkMetadata(
                sources=sources,
                token_usage=event.get("token_usage"),
            ),
        )

    if kind == "awaiting_human":
        return _make_chunk(
            completion_id,
            model,
            created,
            delta=OpenAIDelta(),
            finish_reason="stop",
            fred=FredChunkMetadata(
                awaiting_human=event.get("request"),
            ),
        )

    if kind == "node_error":
        return _make_chunk(
            completion_id,
            model,
            created,
            delta=OpenAIDelta(),
            finish_reason="stop",
            fred=FredChunkMetadata(
                node_error=event.get("error_message"),
            ),
        )

    # status events and unknown kinds are dropped
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    completion_id: str,
    model: str,
    created: int,
    delta: OpenAIDelta,
    finish_reason: str | None = None,
    fred: FredChunkMetadata | None = None,
) -> OpenAICompletionChunk:
    return OpenAICompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[OpenAIChoice(delta=delta, finish_reason=finish_reason)],
        fred=fred,
    )


def _extract_sources(raw: list[Any]) -> list[FredSourceRef]:
    """
    Normalise raw VectorSearchHit dicts into FredSourceRef objects.

    Why this exists:
    - VectorSearchHit is a fred-core type with ~25 fields; the OpenAI compat
      layer should not couple to its internal structure
    - this function projects only the fields relevant for citation display

    How to use:
    - pass the `sources` list from any RuntimeEvent that carries one
    """
    result: list[FredSourceRef] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(
                FredSourceRef(
                    title=item.get("title"),
                    uid=item.get("uid"),
                    page=item.get("page"),
                    score=item.get("score"),
                    citation_url=item.get("citation_url"),
                )
            )
    return result
