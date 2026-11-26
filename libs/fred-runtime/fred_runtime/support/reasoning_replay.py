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
Replay Mistral reasoning to Mistral in its own `thinking` chunk shape.

Mistral's docs ask for the assistant's reasoning chunks back in the history.
`langchain_openai` drops `thinking` blocks from the payload, so a Mistral model
served through the OpenAI-compatible client gets them re-inserted here.
Full rationale: `RUNTIME-EXECUTION-CONTRACT.md` §8.117.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from fred_runtime.react.react_tool_utils import sanitize_tool_name

from .thinking import native_reasoning_content


_MISTRAL_TOOL_NAME_LENGTH = 64
_MISTRAL_TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _sanitize_history_tool_names(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> None:
    occupied: set[str] = set()
    invalid_batches: dict[int, list[dict[str, Any]]] = {}
    for index, entry in enumerate(messages):
        if entry["role"] != "assistant":
            continue
        for call in entry.get("tool_calls") or ():
            if call.get("type") != "function":
                continue
            function = call["function"]
            name = function.get("name")
            if not isinstance(name, str):
                continue
            if _MISTRAL_TOOL_NAME.fullmatch(name):
                occupied.add(name)
            else:
                invalid_batches.setdefault(index, []).append(call)
    if not invalid_batches:
        return

    occupied.update(
        tool["function"]["name"] for tool in tools if tool.get("type") == "function"
    )
    aliases: dict[str, str] = {}
    repaired_errors: dict[str, tuple[str, str]] = {}
    suffix = 2
    for index, entry in enumerate(messages):
        if entry["role"] != "tool":
            repaired_errors.clear()
            for call in invalid_batches.get(index, ()):
                function = call["function"]
                name = function["name"]
                if name not in aliases:
                    ascii_name = name.encode("ascii", errors="ignore").decode("ascii")
                    base = sanitize_tool_name(ascii_name)[:_MISTRAL_TOOL_NAME_LENGTH]
                    alias = base
                    while alias in occupied:
                        ending = f"_{suffix}"
                        alias = base[: _MISTRAL_TOOL_NAME_LENGTH - len(ending)] + ending
                        suffix += 1
                    aliases[name] = alias
                    occupied.add(alias)
                alias = aliases[name]
                # LangChain can borrow the function mapping from an old checkpoint.
                call["function"] = {**function, "name": alias}
                repaired_errors[call["id"]] = (name, alias)
            continue
        repair = repaired_errors.get(entry["tool_call_id"])
        if repair is None:
            continue
        name, alias = repair
        content = entry.get("content")
        # The unknown-tool result names the same call as the assistant history.
        prefix = f"Error: {name} is not a valid tool, try one of ["
        if isinstance(content, str) and content.startswith(prefix):
            entry["content"] = f"Error: {alias}" + content[len(f"Error: {name}") :]


def is_mistral_model_name(model_name: str | None) -> bool:
    """Return whether one configured/effective model name is Mistral."""

    if model_name is None:
        return False
    normalized = model_name.lower()
    return normalized.startswith("mistral") or "/mistral" in normalized


class MistralReasoningReplayChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` that formats assistant history for Mistral Chat Completions."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        wire = payload.get("messages")
        if not isinstance(wire, list):
            return payload
        _sanitize_history_tool_names(wire, payload.get("tools") or [])
        messages = self._convert_input(input_).to_messages()
        if len(wire) != len(messages):
            return payload
        for source, entry in zip(messages, wire, strict=True):
            if isinstance(source, AIMessage) and isinstance(source.content, list):
                content = native_reasoning_content(source.content)
                if isinstance(content, list) and isinstance(entry, dict):
                    entry["content"] = content
        return payload


def with_mistral_reasoning_replay(model: object) -> object:
    """Give a plain Mistral `ChatOpenAI` the reasoning-replay payload; others pass."""

    if type(model) is not ChatOpenAI or not is_mistral_model_name(model.model_name):
        return model
    # Same fields and clients; only the payload serialisation differs.
    object.__setattr__(model, "__class__", MistralReasoningReplayChatOpenAI)
    return model


def replays_native_reasoning(model: object) -> bool:
    """Return whether the history should keep reasoning blocks for this model."""

    return isinstance(model, MistralReasoningReplayChatOpenAI)
