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

from collections.abc import Mapping
from typing import Any, TypeVar

from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from openai import BaseModel as OpenAIModel

from .thinking import (
    FLAT_REASONING_METADATA_KEY,
    extract_thinking_text,
    is_thinking_block,
    native_reasoning_content,
    store_flat_reasoning,
)

_ChatModel = TypeVar("_ChatModel", bound=BaseChatModel)


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


class MistralReasoningReplayChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` that sends assistant reasoning back as Mistral chunks."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        wire = payload.get("messages")
        messages = self._convert_input(input_).to_messages()
        # Responses API or an unexpected payload shape: leave it as built.
        if not isinstance(wire, list) or len(wire) != len(messages):
            return payload
        for source, entry in zip(messages, wire, strict=True):
            if isinstance(source, AIMessage) and isinstance(source.content, list):
                content = native_reasoning_content(source.content)
                if isinstance(content, list) and isinstance(entry, dict):
                    entry["content"] = content
        return payload


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


def with_openai_reasoning(model: _ChatModel) -> _ChatModel:
    """Use in runtimes that can store and render model-native thought blocks."""
    if type(model) is ChatOpenAI:
        return _with_chat_adapter(model, OpenAICompatibleReasoningChat)
    if type(model) is MistralReasoningReplayChatOpenAI:
        return _with_chat_adapter(model, _MistralReasoningChat)
    return model


def replays_native_reasoning(model: object) -> bool:
    """Return whether the history should keep reasoning blocks for this model."""

    return isinstance(model, MistralReasoningReplayChatOpenAI)
