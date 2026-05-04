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

from langchain_core.messages import AIMessageChunk, BaseMessage


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
