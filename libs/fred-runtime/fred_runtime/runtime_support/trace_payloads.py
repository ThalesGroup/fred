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
Trace payload shaping for a content-capturing tracing backend.

Why this module exists:
- a tracing backend that shows what a model received and produced needs those
  payloads as plain, JSON-serializable structures; LangChain message objects
  are neither plain nor stable across providers
- the conversion is shared by the ReAct middleware, the tool binding, and the
  Graph runtime, and none of them should grow its own variant

**Content policy.** Everything this module produces IS content in the sense of
`docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §7, which excludes content
from every observability stream. These helpers are therefore only ever called
behind `tracer.captures_content`, which is off unless a developer explicitly
turned it on for a local Langfuse. Nothing here may be routed to the generic
app-log store, KPI rows, or the audit trail.

How to use:
- `if tracer.captures_content: span.set_io(input=serialize_messages(msgs))`
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

# Fred's normalized usage keys (`normalize_token_usage`) mapped onto the names
# Langfuse recognizes. `input`/`output`/`total` are the canonical trio it uses
# for cost inference; the cache keys follow its documented provider extras.
_USAGE_KEY_MAP = {
    "input_tokens": "input",
    "output_tokens": "output",
    "total_tokens": "total",
    "cache_read_tokens": "cache_read_input_tokens",
    "cache_creation_tokens": "cache_creation_input_tokens",
}


def to_langfuse_usage(token_usage: Mapping[str, int] | None) -> dict[str, int] | None:
    """
    Translate a normalized Fred token-usage map to Langfuse `usage_details`.

    Zero-valued entries are dropped: a provider that reports no cache usage
    sends zeros, and rendering "0 cache read tokens" on every generation adds
    noise without information.

    Example:
    - `to_langfuse_usage({"input_tokens": 812, "output_tokens": 96, ...})`
    """

    if not token_usage:
        return None
    usage = {
        _USAGE_KEY_MAP[key]: int(value)
        for key, value in token_usage.items()
        if key in _USAGE_KEY_MAP and isinstance(value, int) and value > 0
    }
    return usage or None


def _content_to_text(content: object) -> str:
    """
    Flatten a LangChain message content field to plain text.

    Content is a string for most providers but a list of typed blocks for
    multimodal ones (Anthropic, OpenAI vision). Non-text blocks are reduced to
    their type name rather than dumped whole — a base64 image would blow the
    payload budget and tells a trace reader nothing.
    """

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(f"[{block.get('type') or 'block'}]")
        return "".join(parts)
    return str(content)


def _tool_calls_of(message: BaseMessage) -> list[dict[str, Any]]:
    raw_tool_calls = getattr(message, "tool_calls", None) or []
    tool_calls: list[dict[str, Any]] = []
    for tool_call in raw_tool_calls:
        if isinstance(tool_call, dict):
            tool_calls.append(
                {
                    "name": tool_call.get("name"),
                    "args": tool_call.get("args") or {},
                    "id": tool_call.get("id"),
                }
            )
        else:
            tool_calls.append(
                {
                    "name": getattr(tool_call, "name", None),
                    "args": getattr(tool_call, "args", {}) or {},
                    "id": getattr(tool_call, "id", None),
                }
            )
    return tool_calls


_ROLE_BY_MESSAGE_TYPE = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
}


def serialize_message(message: BaseMessage) -> dict[str, Any]:
    """
    Render one LangChain message as a plain `{role, content, ...}` dict.

    The role vocabulary is the chat-completion one Langfuse's message viewer
    understands, so a captured prompt renders as a conversation rather than as
    an opaque object dump.

    Example:
    - `serialize_message(HumanMessage(content="hello"))`
    """

    message_type = getattr(message, "type", "") or ""
    payload: dict[str, Any] = {
        "role": _ROLE_BY_MESSAGE_TYPE.get(message_type, message_type or "unknown"),
        "content": _content_to_text(getattr(message, "content", "")),
    }
    tool_calls = _tool_calls_of(message)
    if tool_calls:
        payload["tool_calls"] = tool_calls
    tool_call_id = getattr(message, "tool_call_id", None)
    if isinstance(tool_call_id, str) and tool_call_id:
        payload["tool_call_id"] = tool_call_id
    name = getattr(message, "name", None)
    if isinstance(name, str) and name:
        payload["name"] = name
    return payload


def serialize_messages(
    messages: Sequence[BaseMessage],
    *,
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """
    Render a message list as the prompt payload of a generation span.

    `system_prompt` is prepended when the caller holds it separately from the
    transcript — LangChain's middleware surfaces it on the request rather than
    as a message, and a captured prompt that omits it misrepresents what the
    model actually received.

    Example:
    - `serialize_messages(request.messages, system_prompt=request.system_prompt)`
    """

    payload: list[dict[str, Any]] = []
    if system_prompt:
        payload.append({"role": "system", "content": system_prompt})
    payload.extend(
        serialize_message(message)
        for message in messages
        if isinstance(message, BaseMessage)
    )
    return payload


def serialize_model_output(messages: Sequence[BaseMessage]) -> object:
    """
    Render a model response as the output payload of a generation span.

    A single assistant message with no tool calls collapses to its bare text —
    that is the common case, and a one-element list of dicts around a sentence
    only makes the trace harder to read. Anything else keeps the full list.

    Example:
    - `serialize_model_output(response.result)`
    """

    serialized = [
        serialize_message(message)
        for message in messages
        if isinstance(message, BaseMessage)
    ]
    if (
        len(serialized) == 1
        and serialized[0].get("role") == "assistant"
        and "tool_calls" not in serialized[0]
    ):
        return serialized[0]["content"]
    return serialized


def final_assistant_message(messages: Sequence[BaseMessage]) -> AIMessage | None:
    """
    Return the last assistant message of a model response, if any.

    Example:
    - `final_assistant_message(response.result)`
    """

    return next(
        (message for message in reversed(messages) if isinstance(message, AIMessage)),
        None,
    )
