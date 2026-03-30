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

from fred_core.store import VectorSearchHit
from langchain_core.messages import AIMessageChunk, BaseMessage
from pydantic import ValidationError

from ..contracts.context import ToolInvocationResult, UiPart
from ..contracts.runtime import HumanInputRequest
from .react_message_codec import stringify_langchain_content


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


def assistant_delta_from_stream_event(raw_event: object) -> str | None:
    """
    Extract one plain assistant text delta from a stream event.

    Why this exists:
    - Fred streams assistant deltas separately from tool calls/results
    - chunk filtering should stay in one adapter helper

    How to use:
    - pass one raw `messages` stream item from the compiled agent

    Example:
    - `delta = assistant_delta_from_stream_event(raw_event)`
    """

    chunk = raw_event[0] if isinstance(raw_event, tuple) and raw_event else raw_event
    if not isinstance(chunk, AIMessageChunk):
        return None
    if chunk.tool_calls or chunk.tool_call_chunks:
        return None
    delta = stringify_langchain_content(chunk.content)
    return delta if delta else None


def runtime_metadata_from_stream_event(
    raw_event: object,
) -> tuple[str | None, dict[str, int] | None, str | None]:
    """
    Extract model metadata from one streamed LangChain message chunk.

    Why this exists:
    - Fred wants model name, token usage, and finish reason on final events
    - streamed chunks and final messages should share the same normalization rules

    How to use:
    - pass one raw `messages` stream item

    Example:
    - `model_name, usage, finish_reason = runtime_metadata_from_stream_event(raw_event)`
    """

    chunk = raw_event[0] if isinstance(raw_event, tuple) and raw_event else raw_event
    if not isinstance(chunk, AIMessageChunk):
        return (None, None, None)
    return runtime_metadata_from_message(chunk)


def runtime_metadata_from_message(
    message: BaseMessage,
) -> tuple[str | None, dict[str, int] | None, str | None]:
    """
    Normalize model metadata from one LangChain message.

    Why this exists:
    - different model providers expose usage metadata under different keys
    - the Fred final event should use one small stable metadata shape

    How to use:
    - pass one assistant message or chunk after a model call

    Example:
    - `runtime_metadata_from_message(message)`
    """

    response_metadata = getattr(message, "response_metadata", {}) or {}
    usage_metadata = getattr(message, "usage_metadata", {}) or {}
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}

    model_name = None
    if isinstance(response_metadata, dict):
        raw_model_name = response_metadata.get("model_name") or response_metadata.get(
            "model"
        )
        if isinstance(raw_model_name, str) and raw_model_name.strip():
            model_name = raw_model_name

    finish_reason = None
    if isinstance(response_metadata, dict):
        raw_finish_reason = response_metadata.get("finish_reason")
        if raw_finish_reason is not None:
            finish_reason = str(raw_finish_reason)

    token_usage = (
        normalize_token_usage(usage_metadata)
        or normalize_token_usage(
            response_metadata.get("usage_metadata")
            if isinstance(response_metadata, dict)
            else None
        )
        or normalize_token_usage(
            response_metadata.get("token_usage")
            if isinstance(response_metadata, dict)
            else None
        )
        or normalize_token_usage(
            response_metadata.get("usage")
            if isinstance(response_metadata, dict)
            else None
        )
        or normalize_token_usage(
            additional_kwargs.get("token_usage")
            if isinstance(additional_kwargs, dict)
            else None
        )
        or normalize_token_usage(
            additional_kwargs.get("usage")
            if isinstance(additional_kwargs, dict)
            else None
        )
    )

    return (model_name, token_usage, finish_reason)


def normalize_token_usage(raw: object) -> dict[str, int] | None:
    """
    Normalize provider token-usage payloads to one Fred shape.

    Why this exists:
    - LangChain providers do not agree on one usage metadata schema
    - the Fred runtime should expose one typed token-usage map

    How to use:
    - pass any provider usage payload or nested usage dict

    Example:
    - `normalize_token_usage({"prompt_tokens": 11, "completion_tokens": 7})`
    """

    if not isinstance(raw, dict) or not raw:
        return None

    usage = raw
    nested_usage = usage.get("usage")
    if isinstance(nested_usage, dict):
        usage = nested_usage

    def _to_int(value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if not isinstance(value, (float, str)):
            return 0
        try:
            return int(value)
        except Exception:
            return 0

    input_raw = usage.get("input_tokens")
    if input_raw is None:
        input_raw = usage.get("prompt_tokens")
    if input_raw is None:
        input_raw = usage.get("prompt_tokens_total")
    if input_raw is None:
        input_raw = usage.get("input_token_count")
    if input_raw is None:
        input_raw = usage.get("prompt_eval_count")

    output_raw = usage.get("output_tokens")
    if output_raw is None:
        output_raw = usage.get("completion_tokens")
    if output_raw is None:
        output_raw = usage.get("completion_tokens_total")
    if output_raw is None:
        output_raw = usage.get("output_token_count")
    if output_raw is None:
        output_raw = usage.get("eval_count")

    total_raw = usage.get("total_tokens")
    if total_raw is None:
        total_raw = usage.get("token_count")

    has_any = any(
        usage.get(key) is not None
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
            "prompt_tokens_total",
            "completion_tokens_total",
            "input_token_count",
            "output_token_count",
            "prompt_eval_count",
            "eval_count",
            "token_count",
        )
    )
    if not has_any:
        return None

    input_tokens = _to_int(input_raw)
    output_tokens = _to_int(output_raw)
    total_tokens = _to_int(total_raw)
    if total_raw is None:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


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
