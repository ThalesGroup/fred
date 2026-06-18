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
Stream-event parsing for LangGraph ReAct execution.

Why this module exists:
- once Fred has compiled a ReAct agent, LangGraph streams back raw SDK payloads
  such as update dictionaries, interrupt objects, `AIMessageChunk` values, and
  `ToolMessage` artifacts
- the Fred runtime should not contain those low-level parsing rules directly
- this module converts those raw stream payloads into stable Fred-side pieces such
  as assistant deltas, HITL requests, token usage, sources, and UI parts

How to use:
- use `split_stream_event_mode(...)` and `extract_messages_from_update(...)` while
  consuming `compiled_agent.astream(...)`
- use the metadata and merge helpers when building Fred runtime events from tool
  results and final assistant output

Example:
- stream event mode:
  `mode, payload = split_stream_event_mode(raw_event)`
- interrupt parsing:
  `request = extract_interrupt_request(payload)`
- final source aggregation:
  `collected_sources = merge_sources(collected_sources, artifact.sources)`
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from fred_core.store import VectorSearchHit
from fred_sdk.contracts.context import ToolInvocationResult, UiPart
from fred_sdk.contracts.runtime import HumanInputRequest
from langchain_core.messages import AIMessageChunk, BaseMessage
from pydantic import ValidationError

from fred_runtime.runtime_support.model_metadata import (  # noqa: F401
    normalize_token_usage,
    runtime_metadata_from_message,
    runtime_metadata_from_stream_event,
)

from .react_message_codec import stringify_langchain_content
from .react_thinking import extract_thinking_text, is_thinking_block


def extract_messages_from_update(update: object) -> list[BaseMessage]:
    """
    Collect LangChain messages from one nested LangGraph update payload.

    Why this exists:
    - LangGraph update events can nest message lists under multiple keys
    - the runtime event bridge should not know those traversal details

    How to use:
    - pass one raw update payload from `astream(..., stream_mode=[...])`

    Example:
    - `messages = extract_messages_from_update(update)`
    """

    messages: list[BaseMessage] = []
    if isinstance(update, dict):
        raw_messages = update.get("messages")
        if isinstance(raw_messages, list):
            messages.extend(
                message for message in raw_messages if isinstance(message, BaseMessage)
            )
        for value in update.values():
            messages.extend(extract_messages_from_update(value))
    return messages


def split_stream_event_mode(raw_event: object) -> tuple[str, object]:
    """
    Normalize one LangGraph stream event to `(mode, payload)`.

    Why this exists:
    - LangGraph can emit either plain payloads or `(mode, payload)` tuples
    - the runtime event bridge should handle both forms uniformly

    How to use:
    - pass one raw item from `compiled_agent.astream(...)`

    Example:
    - `mode, payload = split_stream_event_mode(raw_event)`
    """

    if (
        isinstance(raw_event, tuple)
        and len(raw_event) == 2
        and isinstance(raw_event[0], str)
    ):
        return raw_event[0], raw_event[1]
    return "updates", raw_event


def extract_interrupt_request(update: object) -> HumanInputRequest | None:
    """
    Parse one LangGraph interrupt payload into the Fred HITL request model.

    Why this exists:
    - LangGraph interrupt payloads have a few structural variants
    - the Fred runtime wants one stable `HumanInputRequest` object regardless of
      the SDK shape

    How to use:
    - pass one update payload from the compiled agent stream

    Example:
    - `request = extract_interrupt_request(update)`
    """

    if not isinstance(update, dict):
        return None
    key = next(iter(update), None)
    if key not in {"interrupt", "__interrupt__"}:
        return None

    raw_interrupt = update[key]
    payload_obj: object
    checkpoint_id: str | None = None
    if isinstance(raw_interrupt, list):
        if not raw_interrupt:
            raise RuntimeError("Runtime emitted an empty interrupt list.")
        raw_interrupt = raw_interrupt[0]

    if isinstance(raw_interrupt, tuple):
        if len(raw_interrupt) == 2:
            payload_obj = raw_interrupt[0]
            checkpoint_id = getattr(raw_interrupt[1], "id", None) or getattr(
                raw_interrupt[1], "checkpoint_id", None
            )
        elif len(raw_interrupt) == 1:
            first = raw_interrupt[0]
            payload_obj = getattr(first, "value", first)
            checkpoint_id = getattr(first, "id", None) or getattr(
                first, "checkpoint_id", None
            )
        else:
            raise RuntimeError(
                f"Runtime emitted an unsupported interrupt tuple length: {len(raw_interrupt)}."
            )
    elif isinstance(raw_interrupt, dict):
        payload_obj = raw_interrupt.get("value", raw_interrupt)
        raw_checkpoint_id = (
            raw_interrupt.get("checkpoint_id")
            or raw_interrupt.get("id")
            or raw_interrupt.get("interrupt_id")
        )
        if isinstance(raw_checkpoint_id, str) and raw_checkpoint_id.strip():
            checkpoint_id = raw_checkpoint_id
    else:
        payload_obj = getattr(raw_interrupt, "value", raw_interrupt)
        raw_checkpoint_id = getattr(raw_interrupt, "id", None) or getattr(
            raw_interrupt, "checkpoint_id", None
        )
        if isinstance(raw_checkpoint_id, str) and raw_checkpoint_id.strip():
            checkpoint_id = raw_checkpoint_id

    try:
        request = HumanInputRequest.model_validate(payload_obj)
    except ValidationError as exc:
        raise RuntimeError(
            "Runtime emitted an invalid HITL payload. "
            "Expected HumanInputRequest-compatible data."
        ) from exc
    if checkpoint_id is not None:
        request = request.model_copy(update={"checkpoint_id": checkpoint_id})
    return request


@dataclass(frozen=True)
class StreamChunkDecode:
    """
    One streamed `AIMessageChunk` split into model-native reasoning and answer text.

    Why this exists (RUNTIME-05 Layer 2b):
    - reasoning-capable models interleave reasoning blocks with the answer inside a
      single `AIMessageChunk.content`
    - the runtime must route reasoning to the `THOUGHT_*` stream
      (`source="model_native"`) and the answer to assistant deltas — never mix them

    Fields:
    - `thought_fragments`: ordered model-native reasoning text fragments in this
      chunk (empty when the chunk carries no reasoning)
    - `text`: the assistant answer text in this chunk, or None when the chunk is
      reasoning-only / not assistant text
    """

    thought_fragments: tuple[str, ...] = ()
    text: str | None = None


def decode_stream_chunk(raw_event: object) -> StreamChunkDecode:
    """
    Split one streamed event into model-native reasoning fragments and answer text.

    Why this exists:
    - a single Mistral/Claude streamed chunk can contain a reasoning block, an
      answer block, or — at the transition frame — both at once
    - callers need the reasoning and the answer separated, in order, so they can
      emit `THOUGHT_*` events before the first `ASSISTANT_DELTA`

    How to use:
    - pass one raw `messages` stream item from the compiled agent; the caller owns
      THOUGHT block open/close state across frames

    Example:
    - `decoded = decode_stream_chunk(raw_event)`
    """

    if isinstance(raw_event, tuple) and len(raw_event) == 2:
        chunk, chunk_meta = raw_event
        if isinstance(chunk_meta, dict) and chunk_meta.get("langgraph_node") == "tools":
            return StreamChunkDecode()
    else:
        chunk = raw_event
    if not isinstance(chunk, AIMessageChunk):
        return StreamChunkDecode()
    if chunk.tool_calls or chunk.tool_call_chunks:
        return StreamChunkDecode()

    fragments: list[str] = []
    # Some OpenAI-compatible gateways surface reasoning at the top level rather than
    # as a content block (e.g. DeepSeek-style `reasoning_content`).
    additional = getattr(chunk, "additional_kwargs", None)
    if isinstance(additional, dict):
        for key in ("reasoning_content", "reasoning"):
            value = additional.get(key)
            if isinstance(value, str) and value:
                fragments.append(value)

    text = _split_thinking_from_content(chunk.content, fragments)
    return StreamChunkDecode(
        thought_fragments=tuple(fragment for fragment in fragments if fragment),
        text=text or None,
    )


def _split_thinking_from_content(content: object, fragments_out: list[str]) -> str:
    """
    Render the answer text of one content value, diverting reasoning blocks.

    Reasoning blocks are appended to ``fragments_out`` and excluded from the
    returned text. Non-reasoning blocks render exactly as
    `stringify_langchain_content` would, so non-thinking models are unaffected.
    """

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return stringify_langchain_content(content)
    text_parts: list[str] = []
    for item in content:
        if is_thinking_block(item):
            fragment = extract_thinking_text(item)
            if fragment:
                fragments_out.append(fragment)
            continue
        rendered = stringify_langchain_content([item])
        if rendered:
            text_parts.append(rendered)
    return "\n".join(text_parts)


def assistant_delta_from_stream_event(raw_event: object) -> str | None:
    """
    Extract one plain assistant text delta from a stream event.

    Why this exists:
    - Fred streams assistant deltas separately from tool calls/results
    - chunk filtering should stay in one adapter helper

    Model-native reasoning is excluded from the returned delta — it is routed to the
    `THOUGHT_*` stream via `decode_stream_chunk` (RUNTIME-05 Layer 2b).

    How to use:
    - pass one raw `messages` stream item from the compiled agent

    Example:
    - `delta = assistant_delta_from_stream_event(raw_event)`
    """

    return decode_stream_chunk(raw_event).text


def normalize_tool_artifact(artifact: object) -> ToolInvocationResult | None:
    """
    Parse one optional LangChain tool artifact into the Fred tool result model.

    Why this exists:
    - runtime provider tools may return bare objects or typed Fred artifacts
    - stream handling should normalize that artifact once before building events

    How to use:
    - pass `ToolMessage.artifact` or another raw artifact payload

    Example:
    - `artifact = normalize_tool_artifact(message.artifact)`
    """

    if artifact is None:
        return None
    if isinstance(artifact, ToolInvocationResult):
        return artifact
    try:
        return ToolInvocationResult.model_validate(artifact)
    except ValidationError as exc:
        raise RuntimeError(
            "Tool runtime produced an invalid artifact. "
            "Expected ToolInvocationResult-compatible data."
        ) from exc


def merge_sources(
    existing: tuple[VectorSearchHit, ...],
    new_sources: tuple[VectorSearchHit, ...],
) -> tuple[VectorSearchHit, ...]:
    """
    Merge tool-result sources without duplicating equivalent hits.

    Why this exists:
    - multiple tool results can contribute sources to one final assistant answer
    - the Fred final event should not repeat the same source record

    How to use:
    - pass the currently collected sources plus the newly emitted ones

    Example:
    - `collected_sources = merge_sources(collected_sources, artifact.sources)`
    """

    if not new_sources:
        return existing

    merged = list(existing)
    seen = {
        (source.uid, source.rank, source.content, source.title) for source in existing
    }
    for source in new_sources:
        key = (source.uid, source.rank, source.content, source.title)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return tuple(merged)


def merge_ui_parts(
    existing: tuple[UiPart, ...],
    new_parts: tuple[UiPart, ...],
) -> tuple[UiPart, ...]:
    """
    Merge tool-result UI parts without duplicating identical parts.

    Why this exists:
    - multiple tools can emit reusable UI parts during one run
    - the final runtime event should present a deduplicated set

    How to use:
    - pass the currently collected UI parts plus the newly emitted ones

    Example:
    - `collected_ui_parts = merge_ui_parts(collected_ui_parts, artifact.ui_parts)`
    """

    if not new_parts:
        return existing

    merged = list(existing)
    seen = {
        json.dumps(part.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for part in existing
    }
    for part in new_parts:
        key = json.dumps(
            part.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(part)
    return tuple(merged)
