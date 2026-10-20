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

"""Recover completed Mistral tool-call text into native tool calls."""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fred_core.kpi import BaseKPIWriter, KPIActor
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall, tool_call
from langchain_core.tools import BaseTool, InjectedToolCallId
from pydantic import BaseModel, ValidationError

from fred_runtime.support.reasoning_replay import is_mistral_model_name
from fred_runtime.support.thinking import is_payloadless_block, is_thinking_block

from ..react_model_adapter import (
    extract_model_name_from_model_response,
    extract_model_name_from_object,
)

logger = logging.getLogger(__name__)

RECOVERED_TOOL_CALL_TEXT_METADATA_KEY = "fred_tool_call_text_recovered"

MAX_TOOL_CALL_RECOVERY_CHARS = 16_384
MAX_TOOL_CALL_RECOVERY_NAME_CHARS = 256
_MAX_RECOVERED_CALLS = 16
_TOOL_NAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
)
_FOLLOWUP_CALL = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]{1,256})\s*(?=\{)")


class _DuplicateJsonKey(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON constant: {value}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


_JSON_DECODER = json.JSONDecoder(
    parse_constant=_reject_json_constant,
    object_pairs_hook=_strict_json_object,
)
_LINE_BREAK_JSON_DECODER = json.JSONDecoder(
    strict=False,
    parse_constant=_reject_json_constant,
    object_pairs_hook=_strict_json_object,
)


def _has_other_raw_string_controls(text: str) -> bool:
    in_string = False
    escaped = False
    for char in text:
        if not in_string:
            in_string = char == '"'
        elif escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            in_string = False
        elif ord(char) < 0x20 and char not in "\r\n":
            return True
    return False


def is_tool_call_recovery_reference_block(block: object) -> bool:
    """Match the exact empty reference sentinel seen in reconstructed incidents."""

    return block == {"type": "reference", "reference_ids": []}


def recovery_text_fragment(block: object) -> str | None:
    """Read text from a typed block or a plain LangChain content fragment."""

    if isinstance(block, str):
        return block
    if isinstance(block, dict) and block.get("type") == "text":
        value = block.get("text")
        if isinstance(value, str):
            return value
    return None


def _trailing_registered_name(
    text: str, tools_by_name: dict[str, BaseTool], *, dot_boundary: bool = False
) -> str | None:
    # At the reference anchor a sentence can end right on the name
    # ("...landscape.read_document"); a longer dotted registered name still wins.
    matching_names = [
        name
        for name in tools_by_name
        if len(name) <= MAX_TOOL_CALL_RECOVERY_NAME_CHARS
        and text.endswith(name)
        and (
            len(text) == len(name)
            or text[-len(name) - 1] not in _TOOL_NAME_CHARS
            or (dot_boundary and text[-len(name) - 1] == ".")
        )
    ]
    return max(matching_names, key=len) if matching_names else None


def _anchored_text(
    content: object, tools_by_name: dict[str, BaseTool]
) -> tuple[str, list[tuple[str, str]]] | None:
    # No block-count cap: streaming leaves one block per delta (hundreds of
    # thinking blocks in a long turn). The text and call caps bound the work.
    if not isinstance(content, list):
        return None

    before: list[str] = []
    segment: list[str] = []
    segments: list[tuple[str, str]] = []
    marked_name: str | None = None
    preamble = ""
    text_chars = 0
    for block in content:
        text = recovery_text_fragment(block)
        if text is not None:
            text_chars += len(text)
            if text_chars > MAX_TOOL_CALL_RECOVERY_CHARS:
                return None
            (segment if marked_name is not None else before).append(text)
        elif (
            isinstance(block, dict)
            and block.get("type") == "thinking"
            and marked_name is None
        ):
            continue
        elif is_payloadless_block(block):
            continue
        elif is_tool_call_recovery_reference_block(block):
            if marked_name is None:
                before_text = "".join(before)
                marked_name = _trailing_registered_name(
                    before_text, tools_by_name, dot_boundary=True
                )
                if marked_name is None:
                    return None
                preamble = before_text[: -len(marked_name)]
            else:
                current = "".join(segment)
                next_name = _trailing_registered_name(
                    current, tools_by_name, dot_boundary=True
                )
                if next_name is None:
                    return None
                segments.append((marked_name, current[: -len(next_name)]))
                marked_name = next_name
                segment = []
        else:
            return None
    if marked_name is None or not segment:
        return None
    segments.append((marked_name, "".join(segment)))
    return preamble, segments


def _parse_sequence(
    text: str,
    *,
    first_name: str,
    tools_by_name: dict[str, BaseTool],
    max_calls: int,
) -> tuple[list[tuple[str, dict[str, Any]]], int] | None:
    """Parse the calls in one segment; return them and the leftover text length."""
    if max_calls < 1:
        return None
    parsed: list[tuple[str, dict[str, Any]]] = []
    leftover_chars = 0
    position = 0

    def decode_args(name: str, start: int) -> tuple[dict[str, Any], int] | None:
        try:
            try:
                args, end = _JSON_DECODER.raw_decode(text, start)
            except json.JSONDecodeError:
                args, end = _LINE_BREAK_JSON_DECODER.raw_decode(text, start)
                if _has_other_raw_string_controls(text[start:end]):
                    return None
            if not isinstance(args, dict):
                return None
            tool = tools_by_name[name]
            full_schema = cast(type[BaseModel], tool.get_input_schema())
            public_schema = tool.tool_call_schema
            validation_args = args
            if isinstance(public_schema, type):
                schema = cast(type[BaseModel], public_schema)
                schema.model_validate(args, extra="forbid")
                hidden_fields = (
                    full_schema.model_fields.keys() - schema.model_fields.keys()
                )
                if hidden_fields:
                    if hidden_fields != {"tool_call_id"} or (
                        InjectedToolCallId
                        not in full_schema.model_fields["tool_call_id"].metadata
                    ):
                        return None
                    validation_args = {**args, "tool_call_id": "recovery-validation"}
            full_schema.model_validate(validation_args, extra="forbid")
        except (
            json.JSONDecodeError,
            RecursionError,
            ValidationError,
            TypeError,
            ValueError,
        ):
            return None
        return args, end

    first = decode_args(first_name, position)
    if first is None:
        return None
    args, position = first
    parsed.append((first_name, args))
    while True:
        next_call: tuple[str, dict[str, Any], int, int] | None = None
        for candidate in _FOLLOWUP_CALL.finditer(text, position):
            name = candidate.group(1)
            if name not in tools_by_name:
                continue
            decoded = decode_args(name, candidate.end())
            if decoded is not None:
                candidate_args, end = decoded
                next_call = name, candidate_args, candidate.start(), end
                break
        if next_call is None:
            leftover_chars += len(text[position:].strip())
            break
        if len(parsed) >= max_calls:
            return None
        name, args, start, end = next_call
        leftover_chars += len(text[position:start].strip())
        parsed.append((name, args))
        position = end
    return parsed, leftover_chars


def _recover_calls(
    content: object, tools_by_name: dict[str, BaseTool]
) -> tuple[str, list[ToolCall], int] | None:
    """Return the preamble, the recovered calls and the dropped text length.

    Text after the first recovered call is dropped: in every observed leak it
    was runaway output (closers, diff headers, looping prose), never an answer.
    """
    anchored = _anchored_text(content, tools_by_name)
    if anchored is None:
        return None
    preamble, segments = anchored
    parsed_calls: list[tuple[str, dict[str, Any]]] = []
    dropped_chars = 0
    for first_name, segment in segments:
        parsed = _parse_sequence(
            segment.lstrip(),
            first_name=first_name,
            tools_by_name=tools_by_name,
            max_calls=_MAX_RECOVERED_CALLS - len(parsed_calls),
        )
        if parsed is None:
            return None
        calls, leftover_chars = parsed
        parsed_calls.extend(calls)
        dropped_chars += leftover_chars
    native_calls = [
        tool_call(name=name, args=args, id=f"recovered-{uuid.uuid4().hex}")
        for name, args in parsed_calls
    ]
    return preamble.strip(), native_calls, dropped_chars


def _repaired_call_names(
    calls: list[ToolCall], tools_by_name: dict[str, BaseTool]
) -> list[ToolCall] | None:
    # A model can loop its own output into a native call's name. A name ending in
    # a registered tool keeps that tool; other unknown names reach the tool node's
    # "not a valid tool" error, clipped so the error echo stays bounded.
    repaired: list[ToolCall] = []
    changed = False
    for call in calls:
        name = call["name"]
        if name not in tools_by_name:
            fixed = (
                _trailing_registered_name(name, tools_by_name)
                or name[:MAX_TOOL_CALL_RECOVERY_NAME_CHARS]
            )
            if fixed != name:
                call = call.copy()
                call["name"] = fixed
                changed = True
        repaired.append(call)
    return repaired if changed else None


class ToolCallTextRecoveryMiddleware(AgentMiddleware):
    """Adapt unambiguous completed tool-call text before agent routing."""

    def __init__(
        self, *, enabled: bool = True, kpi: BaseKPIWriter | None = None
    ) -> None:
        super().__init__()
        self._enabled = enabled
        self._kpi = kpi

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        response = await handler(request)
        # A middleware that set tool_choice="none" asked for a reply only: tool-call
        # text is then left as text, never turned back into a call.
        if not self._enabled or request.tool_choice == "none":
            return response
        tools_by_name = {
            entry.name: entry
            for entry in request.tools
            if isinstance(entry, BaseTool) and entry.name
        }
        if not tools_by_name:
            return response

        result = list(response.result)
        changed = False
        recovered_counts: dict[str, int] = {}
        for index, message in enumerate(result):
            if not isinstance(message, AIMessage):
                continue
            native_calls = message.tool_calls
            repaired = (
                _repaired_call_names(native_calls, tools_by_name)
                if native_calls
                else None
            )
            if repaired is not None:
                native_calls = repaired
            model_name = extract_model_name_from_model_response(message)
            recovered = (
                _recover_calls(message.content, tools_by_name)
                if not message.invalid_tool_calls and is_mistral_model_name(model_name)
                else None
            )
            if recovered is None or model_name is None:
                if repaired is not None:
                    result[index] = message.model_copy(update={"tool_calls": repaired})
                    changed = True
                continue
            preamble, text_calls, dropped_chars = recovered
            # Text calls precede the native delta in the stream; a text call
            # equal to a native one is the same call written twice.
            text_calls = [
                call
                for call in text_calls
                if not any(
                    (call["name"], call["args"]) == (native["name"], native["args"])
                    for native in native_calls
                )
            ]
            if dropped_chars:
                logger.info(
                    "Tool-call recovery dropped %d chars of text after the call",
                    dropped_chars,
                )
            metadata = dict(message.response_metadata)
            metadata[RECOVERED_TOOL_CALL_TEXT_METADATA_KEY] = True
            content: str | list[str | dict[Any, Any]] = preamble
            if isinstance(message.content, list):
                thinking = [
                    block for block in message.content if is_thinking_block(block)
                ]
                if thinking:
                    content = [*thinking, preamble] if preamble else thinking
            result[index] = message.model_copy(
                update={
                    "content": content,
                    "tool_calls": [*text_calls, *native_calls],
                    "response_metadata": metadata,
                }
            )
            changed = True
            if text_calls:
                metric_model_name = (
                    extract_model_name_from_object(request.model) or model_name
                )
                recovered_counts[metric_model_name] = recovered_counts.get(
                    metric_model_name, 0
                ) + len(text_calls)
        if not changed:
            return response
        if self._kpi is not None:
            for model_name, count in recovered_counts.items():
                self._kpi.count(
                    "agent.tool_call_text_recovered_total",
                    count,
                    dims={"model_name": model_name},
                    actor=KPIActor(type="system"),
                )
        return ModelResponse(
            result=result,
            structured_response=response.structured_response,
        )
