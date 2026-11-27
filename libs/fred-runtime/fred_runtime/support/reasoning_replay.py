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

"""Read OpenAI-compatible reasoning and optionally replay Mistral thinking."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, TypeVar

from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from openai import BaseModel as OpenAIModel

from fred_runtime.react.react_tool_utils import sanitize_tool_name

from .thinking import (
    FLAT_REASONING_METADATA_KEY,
    extract_thinking_text,
    is_thinking_block,
    native_reasoning_content,
    store_flat_reasoning,
)

_ChatModel = TypeVar("_ChatModel", bound=BaseChatModel)

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


def _capture_flat_reasoning(message: AIMessage, fields: object) -> None:
    """Keep the vLLM extension at the boundary where LangChain drops it."""
    for key in ("reasoning", "reasoning_content"):
        reasoning = (
            fields.get(key)
            if isinstance(fields, Mapping)
            else getattr(fields, key, None)
        )
        if isinstance(reasoning, str) and reasoning:
            break
    else:
        return

    content = message.content
    if isinstance(content, list) and any(
        is_thinking_block(block) and extract_thinking_text(block) for block in content
    ):
        return  # Prefer native blocks if the endpoint supplies both forms.
    # LangChain joins fragment strings as it combines chunks. Growing a list
    # of thinking blocks here makes its final merge quadratic in frame count.
    message.additional_kwargs["reasoning"] = reasoning
    message.response_metadata[FLAT_REASONING_METADATA_KEY] = True


class OpenAICompatibleReasoningChat(ChatOpenAI):
    """Preserve vLLM reasoning for streaming and completed assistant messages."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if result is not None and isinstance(result.message, AIMessageChunk):
            choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices")
            if choices:
                _capture_flat_reasoning(result.message, choices[0]["delta"])
        return result

    def _create_chat_result(
        self,
        response: dict | OpenAIModel,
        generation_info: dict | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        choices = (
            response["choices"]
            if isinstance(response, dict)
            else getattr(response, "choices", ())
        )
        for generation, choice in zip(result.generations, choices, strict=True):
            if isinstance(generation.message, AIMessage):
                fields = (
                    choice["message"] if isinstance(choice, dict) else choice.message
                )
                _capture_flat_reasoning(generation.message, fields)
                store_flat_reasoning(generation.message)
        return result


class _MistralToolHistoryChatOpenAI(ChatOpenAI):
    """Repair historical tool calls for Mistral Chat Completions."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        wire = payload.get("messages")
        if isinstance(wire, list):
            _sanitize_history_tool_names(wire, payload.get("tools") or [])
        return payload


class MistralReasoningReplayChatOpenAI(_MistralToolHistoryChatOpenAI):
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
        messages = self._convert_input(input_).to_messages()
        if len(wire) != len(messages):
            return payload
        for source, entry in zip(messages, wire, strict=True):
            if isinstance(source, AIMessage) and isinstance(source.content, list):
                content = native_reasoning_content(source.content)
                if isinstance(content, list) and isinstance(entry, dict):
                    entry["content"] = content
        return payload


class _MistralToolHistoryReasoningChat(
    _MistralToolHistoryChatOpenAI, OpenAICompatibleReasoningChat
):
    """Capture flat reasoning and repair history on replay-disabled routes."""


class _MistralReasoningChat(
    MistralReasoningReplayChatOpenAI, OpenAICompatibleReasoningChat
):
    """Normalize responses while preserving the selected native replay policy."""


def _with_chat_adapter(model: _ChatModel, adapter: type[ChatOpenAI]) -> _ChatModel:
    adapted = model.model_copy()
    # The subclasses share ChatOpenAI's fields and reuse its configured clients.
    object.__setattr__(adapted, "__class__", adapter)
    return adapted


def with_mistral_reasoning_replay(model: _ChatModel) -> _ChatModel:
    if type(model) is ChatOpenAI:
        return _with_chat_adapter(model, MistralReasoningReplayChatOpenAI)
    return model


def with_mistral_tool_history(model: _ChatModel) -> _ChatModel:
    if type(model) is ChatOpenAI and is_mistral_model_name(model.model_name):
        return _with_chat_adapter(model, _MistralToolHistoryChatOpenAI)
    return model


def with_openai_reasoning(model: _ChatModel) -> _ChatModel:
    """Use in runtimes that can store and render model-native thought blocks."""
    if type(model) is ChatOpenAI:
        return _with_chat_adapter(model, OpenAICompatibleReasoningChat)
    if type(model) is _MistralToolHistoryChatOpenAI:
        return _with_chat_adapter(model, _MistralToolHistoryReasoningChat)
    if type(model) is MistralReasoningReplayChatOpenAI:
        return _with_chat_adapter(model, _MistralReasoningChat)
    return model


def replays_native_reasoning(model: object) -> bool:
    """Return whether the history should keep reasoning blocks for this model."""

    return isinstance(model, MistralReasoningReplayChatOpenAI)
