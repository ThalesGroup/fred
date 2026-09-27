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
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fred_core.kpi import BaseKPIWriter, KPIActor
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall, tool_call
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from ..react_model_adapter import (
    extract_model_name_from_model_response,
    extract_model_name_from_object,
)

RECOVERED_TOOL_CALL_TEXT_METADATA_KEY = "fred_tool_call_text_recovered"

_MAX_RECOVERY_BLOCKS = 256
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


def is_mistral_model_name(model_name: str | None) -> bool:
    """Return whether one configured/effective model name is Mistral."""

    if model_name is None:
        return False
    normalized = model_name.lower()
    return normalized.startswith("mistral") or "/mistral" in normalized


def is_tool_call_recovery_reference_block(block: object) -> bool:
    """Match the exact empty reference sentinel seen in reconstructed incidents."""

    return block == {"type": "reference", "reference_ids": []}


def _anchored_text(
    content: object, tools_by_name: dict[str, BaseTool]
) -> tuple[str, str, str] | None:
    if not isinstance(content, list):
        return None
    if len(content) > _MAX_RECOVERY_BLOCKS:
        return None

    before: list[str] = []
    after: list[str] = []
    seen_reference = False
    text_chars = 0
    for block in content:
        if not isinstance(block, dict):
            return None
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            text = block["text"]
            text_chars += len(text)
            if text_chars > MAX_TOOL_CALL_RECOVERY_CHARS:
                return None
            (after if seen_reference else before).append(text)
        elif block_type == "thinking" and not seen_reference:
            continue
        elif is_tool_call_recovery_reference_block(block) and not seen_reference:
            seen_reference = True
        else:
            return None
    if not seen_reference or not before or not after:
        return None

    before_text = "".join(before)
    matching_names = [
        name
        for name in tools_by_name
        if len(name) <= MAX_TOOL_CALL_RECOVERY_NAME_CHARS
        and before_text.endswith(name)
        and (
            len(before_text) == len(name)
            or before_text[-len(name) - 1] not in _TOOL_NAME_CHARS
        )
    ]
    if not matching_names:
        return None
    first_name = max(matching_names, key=len)
    return before_text[: -len(first_name)], first_name, "".join(after).strip()


def _parse_sequence(
    text: str,
    *,
    first_name: str,
    tools_by_name: dict[str, BaseTool],
) -> tuple[list[ToolCall], str] | None:
    parsed: list[tuple[str, dict[str, Any]]] = []
    retained: list[str] = []
    position = 0

    def decode_args(name: str, start: int) -> tuple[dict[str, Any], int] | None:
        try:
            args, end = _JSON_DECODER.raw_decode(text, start)
            if not isinstance(args, dict):
                return None
            schema = cast(type[BaseModel], tools_by_name[name].get_input_schema())
            schema.model_validate(args, extra="forbid")
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
            retained.append(text[position:])
            break
        if len(parsed) >= _MAX_RECOVERED_CALLS:
            return None
        name, args, start, end = next_call
        retained.append(text[position:start])
        parsed.append((name, args))
        position = end
    calls = [
        tool_call(
            name=name,
            args=args,
            id=f"recovered-{uuid.uuid4().hex}",
        )
        for name, args in parsed
    ]
    return calls, "".join(retained)


def _recover_calls(
    content: object, tools_by_name: dict[str, BaseTool]
) -> tuple[str, list[ToolCall]] | None:
    anchored = _anchored_text(content, tools_by_name)
    if anchored is None:
        return None
    preamble, first_name, call_text = anchored
    parsed = _parse_sequence(
        call_text,
        first_name=first_name,
        tools_by_name=tools_by_name,
    )
    if parsed is None:
        return None
    calls, retained = parsed
    return (preamble + retained).strip(), calls


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
        if not self._enabled:
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
            if (
                not isinstance(message, AIMessage)
                or message.tool_calls
                or message.invalid_tool_calls
            ):
                continue
            model_name = extract_model_name_from_model_response(message)
            if model_name is None or not is_mistral_model_name(model_name):
                continue
            recovered = _recover_calls(message.content, tools_by_name)
            if recovered is None:
                continue
            preamble, calls = recovered
            metadata = dict(message.response_metadata)
            metadata[RECOVERED_TOOL_CALL_TEXT_METADATA_KEY] = True
            result[index] = message.model_copy(
                update={
                    "content": preamble,
                    "tool_calls": calls,
                    "response_metadata": metadata,
                }
            )
            changed = True
            metric_model_name = (
                extract_model_name_from_object(request.model) or model_name
            )
            recovered_counts[metric_model_name] = recovered_counts.get(
                metric_model_name, 0
            ) + len(calls)
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
