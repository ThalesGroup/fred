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
Shared helpers for extracting model metadata and token usage.

Why this module exists:
- both ReAct and Graph runtimes need consistent token-usage normalization
- LangChain providers expose usage metadata under different keys
- keeping this logic in one shared place avoids divergence over time

How to use:
- call `runtime_metadata_from_message(...)` on AIMessage/AIMessageChunk instances
- call `runtime_metadata_from_stream_event(...)` inside streaming loops
- call `normalize_token_usage(...)` if you already have a raw usage payload

Example:
- `model_name, usage, finish_reason = runtime_metadata_from_message(message)`
"""

from __future__ import annotations

from fred_core.history.history_schema import (
    FinishReason,
    ModelCallTokenUsage,
    coerce_finish_reason,
)
from langchain_core.messages import AIMessageChunk, BaseMessage


def runtime_metadata_from_stream_event(
    raw_event: object,
) -> tuple[str | None, dict[str, int] | None, FinishReason | None]:
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
) -> tuple[str | None, dict[str, int] | None, FinishReason | None]:
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

    model_name = None
    if isinstance(response_metadata, dict):
        raw_model_name = response_metadata.get("model_name") or response_metadata.get(
            "model"
        )
        if isinstance(raw_model_name, str) and raw_model_name.strip():
            model_name = raw_model_name

    finish_reason = None
    if isinstance(response_metadata, dict):
        # Anthropic reports this under "stop_reason", not "finish_reason" — every
        # other provider Fred supports uses "finish_reason". Normalized here (not
        # left raw) so the live SSE event and the persisted history agree on the
        # same value for the same turn; see `coerce_finish_reason` for why this
        # can never fail on an unrecognized provider value.
        raw_finish_reason = response_metadata.get(
            "finish_reason"
        ) or response_metadata.get("stop_reason")
        finish_reason = coerce_finish_reason(raw_finish_reason)

    token_usage = next(
        (
            usage
            for raw in _usage_candidates(message)
            if (usage := normalize_token_usage(raw)) is not None
        ),
        None,
    )

    return (model_name, token_usage, finish_reason)


def _usage_candidates(message: BaseMessage) -> tuple[object, ...]:
    response = getattr(message, "response_metadata", {}) or {}
    additional = getattr(message, "additional_kwargs", {}) or {}
    return (
        getattr(message, "usage_metadata", None),
        response.get("usage_metadata") if isinstance(response, dict) else None,
        response.get("token_usage") if isinstance(response, dict) else None,
        response.get("usage") if isinstance(response, dict) else None,
        additional.get("token_usage") if isinstance(additional, dict) else None,
        additional.get("usage") if isinstance(additional, dict) else None,
    )


def reported_model_call_usage(
    message: BaseMessage, *, model: str | None, tool_call_count: int
) -> ModelCallTokenUsage | None:
    """Retain only counters actually reported by one completed API response.

    Unlike billing normalization, this must not turn absent/invalid fields into
    zero or infer a counter from a total. One response can request several tools.
    """

    def reported_count(usage: dict[str, object], keys: tuple[str, ...]) -> int | None:
        for key in keys:
            value = usage.get(key)
            if value is None:
                continue
            if type(value) is int and value >= 0:
                return value
            if isinstance(value, str) and value.isascii() and value.isdecimal():
                return int(value)
            return None
        return None

    # Prefer raw provider payloads: adapters can synthesize zero for an absent
    # field in UsageMetadata. A normalized-only zero has unknown provenance.
    candidates = _usage_candidates(message)
    for index, raw in enumerate((*candidates[1:], candidates[0])):
        if not isinstance(raw, dict) or not raw:
            continue
        nested_usage = raw.get("usage")
        usage = nested_usage if isinstance(nested_usage, dict) else raw
        raw_provider = index < len(candidates) - 1
        input_tokens = reported_count(
            usage,
            (
                "input_tokens",
                "prompt_tokens",
                "prompt_tokens_total",
                "input_token_count",
                "prompt_eval_count",
            ),
        )
        output_tokens = reported_count(
            usage,
            (
                "output_tokens",
                "completion_tokens",
                "completion_tokens_total",
                "output_token_count",
                "eval_count",
            ),
        )
        if not raw_provider:
            input_tokens = input_tokens or None
            output_tokens = output_tokens or None
        if input_tokens is not None or output_tokens is not None:
            return ModelCallTokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                model_call_id=message.id,
                tool_call_count=tool_call_count,
            )
        if raw_provider and any(
            key in usage
            for key in (
                "input_tokens",
                "prompt_tokens",
                "prompt_tokens_total",
                "input_token_count",
                "prompt_eval_count",
                "output_tokens",
                "completion_tokens",
                "completion_tokens_total",
                "output_token_count",
                "eval_count",
                "total_tokens",
                "token_count",
            )
        ):
            break
    # Batch scope is known even when the provider omitted counters. Retaining
    # it prevents a later response shared by parallel tools looking exclusive.
    return (
        ModelCallTokenUsage(
            model=model, model_call_id=message.id, tool_call_count=tool_call_count
        )
        if tool_call_count
        else None
    )


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

    input_token_details = usage.get("input_token_details")
    cache_read_raw = None
    cache_creation_raw = None
    if isinstance(input_token_details, dict):
        cache_read_raw = input_token_details.get("cache_read")
        cache_creation_raw = input_token_details.get("cache_creation")

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
        "cache_read_tokens": _to_int(cache_read_raw),
        "cache_creation_tokens": _to_int(cache_creation_raw),
    }


def sum_token_usage(
    a: dict[str, int] | None, b: dict[str, int] | None
) -> dict[str, int] | None:
    """
    Add two normalized token-usage maps together.

    Why this exists:
    - a turn can make several model calls (tool-deciding calls, then the
      final answer, or several calls inside one Graph node) — the turn's
      real total is their sum, not whichever call happened to run last
    - a caller tracking a running total across a loop needs one place to
      combine the accumulator with each newly observed call

    How to use:
    - `total = sum_token_usage(total, newly_observed_usage)` inside a loop;
      either side may be `None` (treated as zero) — the result is `None`
      only when both sides are `None`

    Example:
    - `sum_token_usage({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}, {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4})`
      -> `{"input_tokens": 13, "output_tokens": 6, "total_tokens": 19}`
    """

    if a is None and b is None:
        return None
    left = a or {}
    right = b or {}
    return {
        "input_tokens": left.get("input_tokens", 0) + right.get("input_tokens", 0),
        "output_tokens": left.get("output_tokens", 0) + right.get("output_tokens", 0),
        "total_tokens": left.get("total_tokens", 0) + right.get("total_tokens", 0),
        "cache_read_tokens": left.get("cache_read_tokens", 0)
        + right.get("cache_read_tokens", 0),
        "cache_creation_tokens": left.get("cache_creation_tokens", 0)
        + right.get("cache_creation_tokens", 0),
    }
