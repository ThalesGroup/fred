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

import json
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any
from weakref import WeakKeyDictionary

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


#: Argument schemas rendered once per schema class, not once per model call.
#:
#: `BaseModel.model_json_schema()` rebuilds the JSON schema on every call —
#: ~0.4 ms per schema, so ~2 ms for an agent bound to five pydantic-schema
#: tools. That is synchronous CPU on the event loop, repeated on every model
#: call of every turn, for a result that cannot differ: the same agent binding
#: hands the same schema classes to every call.
#:
#: This path covers tools whose `args_schema` is a pydantic **class** — Fred's
#: built-ins and capability tools. MCP tools do not reach it:
#: `langchain_mcp_adapters` sets `args_schema=tool.inputSchema`, a plain dict,
#: which `serialize_tools` copies directly.
#:
#: Keyed weakly so an agent reload that builds fresh schema classes does not pin
#: the old ones in memory.
_JSON_SCHEMA_CACHE: MutableMapping[type, str | None] = WeakKeyDictionary()


def _render_schema(args_schema: object) -> str | None:
    """Render one argument schema to its JSON text, or None if it will not render."""

    render = getattr(args_schema, "model_json_schema", None)
    if not callable(render):
        return None
    try:
        rendered = render()
    except Exception:
        # A schema that will not render must not break the turn: tracing is
        # never allowed to fail the request it is observing.
        return None
    return _schema_to_json(rendered) if isinstance(rendered, dict) else None


def _schema_to_json(schema: Mapping[str, Any]) -> str | None:
    """
    Render an argument schema as one JSON string rather than a nested structure.

    Why a string and not the dict: `_truncate_payload` bounds a trace payload by
    spending a character budget over the strings it walks, but it emits strings
    of 64 characters or less verbatim even past the budget and never walks dict
    *keys* at all. A JSON schema is almost entirely short strings and keys, so
    left nested it escapes the cap — measured at 47x a 100-character budget.
    One string per schema is a single truncatable unit, so the existing budget
    applies to tools exactly as it already applies to message content.
    """

    try:
        return json.dumps(schema, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None


def _json_schema_of(args_schema: object) -> str | None:
    """Render one tool's argument schema, memoized per schema class."""

    if not isinstance(args_schema, type):
        # An instance, not a class: `type(args_schema)` would collide with every
        # other instance of the same class, so render without caching.
        return _render_schema(args_schema)
    try:
        return _JSON_SCHEMA_CACHE[args_schema]
    except (KeyError, TypeError):
        # TypeError: a schema class that cannot be weak-referenced — render it
        # every time rather than refusing to trace it.
        pass

    schema = _render_schema(args_schema)
    try:
        _JSON_SCHEMA_CACHE[args_schema] = schema
    except TypeError:
        # Same non-weak-referenceable schema class as above: it cannot be cached,
        # so return the rendered schema uncached rather than refusing to trace it.
        pass
    return schema


def serialize_tools(tools: Sequence[object]) -> list[dict[str, Any]]:
    """
    Render the bound tool definitions as they reach the provider.

    Why this exists:
    - the `tools` request parameter carries each tool's name, description and
      **argument schema**, and the argument schema exists in no other channel:
      the system prompt names arguments in prose at best, and never their types
      or which ones are required. A trace that captures only messages therefore
      omits the contract the model actually generates tool calls against.

    `ModelRequest.tools` is `list[BaseTool | dict]`: LangChain tools arrive as
    objects, provider-native tool dicts pass through as-is. Both are normalized
    to the `{name, description, parameters}` shape the provider receives, so a
    reader compares like with like whatever the tool source.

    `parameters` is JSON **text**, not a nested structure — see `_schema_to_json`
    for why that is what keeps the payload inside the content budget.

    Example:
    - `serialize_tools(request.tools)`
    """

    payload: list[dict[str, Any]] = []
    for tool in tools:
        if isinstance(tool, Mapping):
            # Provider-native dict — already the wire shape. `function` is the
            # OpenAI envelope; anything else is the tool object itself.
            function = tool.get("function")
            source = function if isinstance(function, Mapping) else tool
            entry = {key: value for key, value in source.items() if key != "parameters"}
            parameters = source.get("parameters")
            if isinstance(parameters, Mapping):
                entry["parameters"] = _schema_to_json(parameters)
            payload.append(entry)
            continue

        name = getattr(tool, "name", None)
        if name is None:
            continue
        entry = {
            "name": name,
            "description": getattr(tool, "description", "") or "",
        }
        args_schema = getattr(tool, "args_schema", None)
        if isinstance(args_schema, Mapping):
            entry["parameters"] = _schema_to_json(args_schema)
        elif args_schema is not None:
            entry["parameters"] = _json_schema_of(args_schema)
        payload.append(entry)
    return payload


def serialize_model_request(
    messages: Sequence[BaseMessage],
    *,
    system_prompt: str | None = None,
    tools: Sequence[object] | None = None,
) -> object:
    """
    Render one model call's full request payload — messages **and** tools.

    Why this exists:
    - `serialize_messages` captures `system_prompt` + `messages`, which is only
      part of what leaves for the provider. The `tools` parameter is a sibling
      field of the same HTTP request and, on a tool-bound agent, a large share
      of it. Capturing messages alone makes a trace look complete while hiding
      the argument schemas the model is actually generating against.

    Shape: with tools, `{"messages": [...], "tools": [...]}` — the provider's
    own request shape. Without tools, the bare message list, unchanged, so
    agents that bind no tool keep exactly today's payload and today's chat
    rendering.

    `messages` is placed first on purpose. `_truncate_payload` walks a mapping
    in insertion order, so the transcript claims the content budget before the
    tool definitions do — preserving the property that a long turn drops tool
    boilerplate rather than the question and the answer.

    Example:
    - `serialize_model_request(request.messages, system_prompt=request.system_prompt, tools=request.tools)`
    """

    payload = serialize_messages(messages, system_prompt=system_prompt)
    if not tools:
        return payload
    return {"messages": payload, "tools": serialize_tools(tools)}


#: Character-count keys recorded as span **attributes**, never as usage details.
#:
#: Two measurements on a live Langfuse 4.7 settled this, in order:
#: 1. As `input_chars` in `usage_details`, the server summed the characters into
#:    `usage.input` — 157 944 "TOKENS" reported for 32 155 tokens plus 125 789
#:    characters. Corrupted the token total outright.
#: 2. Renamed under this prefix, the totals stayed correct, but the UI grouped
#:    the three counts into one "Other usage 119 778" line beside "Input usage
#:    32 155", under the panel's single TOKENS unit — reading as extra tokens.
#:
#: Every usage key is a quantity in one unit, so no naming makes a character
#: count belong there. Attributes carry no unit and are not aggregated, which is
#: also where `LoggingTracer` has always put payload sizes.
CHAR_USAGE_KEYS = ("chars_system", "chars_tools", "chars_messages")


def model_request_char_sizes(
    messages: Sequence[BaseMessage],
    *,
    system_prompt: str | None = None,
    tools: Sequence[object] | None = None,
) -> dict[str, int]:
    """
    Measure what one model call sends, in characters, split by request field.

    Why this exists:
    - a trace reports tokens, which are provider-specific and opaque: nothing in
      it says whether 32 000 tokens are a long conversation or a large tool
      catalogue. The character split answers that directly, and it is the only
      way to compare a payload against the source files it was built from.
    - characters are a **size**, not content (`OBSERVABILITY-AND-AUDIT.md` §7 —
      "`LoggingTracer` records payload *sizes* only"), so unlike the payload
      itself this may be recorded whether or not content capture is on. That
      matters: it is the one volume signal that survives with capture disabled.

    `chars_tools` measures the serialized tool definitions — names, descriptions
    and argument schemas, the part that carries the volume. It is not the exact
    provider wire size: each provider adds its own envelope, worth a few hundred
    characters against tens of thousands here.

    Example:
    - `model_request_char_sizes(request.messages, system_prompt=..., tools=request.tools)`
    """

    sizes = {
        "chars_system": len(system_prompt or ""),
        "chars_messages": sum(
            len(_content_to_text(getattr(message, "content", "")))
            for message in messages
            if isinstance(message, BaseMessage)
        ),
        "chars_tools": 0,
    }
    if tools:
        sizes["chars_tools"] = sum(
            len(str(entry.get("name") or ""))
            + len(str(entry.get("description") or ""))
            + len(str(entry.get("parameters") or ""))
            for entry in serialize_tools(tools)
        )
    return sizes


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
