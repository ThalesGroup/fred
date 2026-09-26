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
Deterministic in-process chat model for the test assistant.

It goes through the real LangChain call path (callbacks, streaming, bound
kwargs), so a runtime sees it exactly like a provider model: streamed text,
schema-valid structured output, tool calls and optional model-native reasoning.
Answers are derived from the last user message, never random.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from typing import Any

from fred_core.common import ModelConfiguration
from fred_runtime.model_routing import FredCoreModelProvider, ModelCapability
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import AgentDefinition
from fred_sdk.contracts.runtime import ChatModelFactoryPort
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

MOCK_PROVIDER = "fred-test-mock"
MOCK_MODEL_NAME = "fred-test-mock"

_WORD_CHUNK = re.compile(r"\S+\s*")


class MockChatModel(BaseChatModel):
    """
    Scripted chat model: echoes a deterministic answer, fills structured
    schemas, and calls a bound tool whose name appears in the user message.

    Enum (Literal) fields of a structured schema pick the first option mentioned
    in the user message, so routing stays controllable from the prompt.
    """

    model_name: str = MOCK_MODEL_NAME
    chunk_delay_s: float = 0.0
    emit_reasoning: bool = False

    @property
    def _llm_type(self) -> str:
        return "fred-test-mock"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return self.bind(
            tools=[convert_to_openai_tool(tool) for tool in tools], **kwargs
        )

    def with_structured_output(  # type: ignore[override]
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[Any, Any]:
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise NotImplementedError("MockChatModel only supports Pydantic schemas.")

        def _parse(message: BaseMessage) -> BaseModel:
            return schema.model_validate_json(_text(message.content))

        def _with_raw(message: BaseMessage) -> dict[str, Any]:
            return {"raw": message, "parsed": _parse(message), "parsing_error": None}

        # A JSON schema, not the class: bound kwargs reach tracers as call params.
        bound = self.bind(fred_mock_schema=schema.model_json_schema())
        return bound | RunnableLambda(_with_raw if include_raw else _parse)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self._respond(messages, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        yield from self._chunks(self._respond(messages, **kwargs))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        # The base class forwards each chunk to on_llm_new_token itself.
        for chunk in self._chunks(self._respond(messages, **kwargs)):
            if self.chunk_delay_s:
                await asyncio.sleep(self.chunk_delay_s)
            yield chunk

    def _respond(self, messages: list[BaseMessage], **kwargs: Any) -> AIMessage:
        hint = _last_user_text(messages)
        schema = kwargs.get("fred_mock_schema")
        tools = kwargs.get("tools") or []
        last = messages[-1] if messages else None

        tool_calls: list[dict[str, Any]] = []
        if schema is not None:
            content = json.dumps(_sample_object(schema, hint), ensure_ascii=False)
        elif isinstance(last, ToolMessage):
            content = f"Mock answer from the tool result: {_text(last.content)[:300]}"
        else:
            tool = _matching_tool(tools, hint)
            if tool is not None:
                content = ""
                tool_calls.append(
                    {
                        "name": tool["function"]["name"],
                        "args": _sample_object(
                            tool["function"].get("parameters") or {}, hint
                        ),
                        "id": f"call_{uuid.uuid4().hex[:20]}",
                    }
                )
            else:
                content = f"Mock answer to: {hint}" if hint else "Mock answer."

        input_tokens = sum(len(_text(m.content).split()) for m in messages)
        output_tokens = len(content.split())
        reasoning = (
            f"Mock reasoning about: {hint}"
            if self.emit_reasoning and schema is None
            else None
        )
        return AIMessage(
            content=content,
            tool_calls=tool_calls,
            additional_kwargs={"reasoning_content": reasoning} if reasoning else {},
            response_metadata={
                "model_name": self.model_name,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            },
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )

    def _chunks(self, message: AIMessage) -> Iterator[ChatGenerationChunk]:
        reasoning = message.additional_kwargs.get("reasoning_content")
        if reasoning:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="", additional_kwargs={"reasoning_content": reasoning}
                )
            )
        for call in message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        tool_call_chunk(
                            name=call["name"],
                            args=json.dumps(call["args"]),
                            id=call["id"],
                            index=0,
                        )
                    ],
                )
            )
        for piece in _WORD_CHUNK.findall(_text(message.content)):
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))
        # Metadata rides on a final empty chunk, as provider streams do.
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                response_metadata=dict(message.response_metadata),
                usage_metadata=message.usage_metadata,
                chunk_position="last",
            )
        )


class MockAwareModelProvider(FredCoreModelProvider):
    """
    Catalog model provider serving `provider: fred-test-mock` in process.

    Every other provider goes to fred-core, so a catalog profile is enough to
    switch an agent instance to the mock — no model server needed.
    """

    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object:
        if model_config.provider != MOCK_PROVIDER:
            return super().build_model(model_config, capability=capability)
        if capability != ModelCapability.CHAT:
            raise ValueError(f"{MOCK_PROVIDER} only serves chat models.")
        settings = model_config.settings or {}
        return MockChatModel(
            model_name=model_config.name or MOCK_MODEL_NAME,
            chunk_delay_s=float(settings.get("chunk_delay_s", 0.0)),
            emit_reasoning=bool(settings.get("emit_reasoning", False)),
        )


class MockChatModelFactory(ChatModelFactoryPort):
    """`ChatModelFactoryPort` that always serves one `MockChatModel`."""

    def __init__(self, model: MockChatModel | None = None) -> None:
        self._model = model or MockChatModel()

    def build(
        self, definition: AgentDefinition, binding: BoundRuntimeContext
    ) -> MockChatModel:
        del definition, binding
        return self._model


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in content
            if isinstance(part, (str, dict))
        )
    return str(content or "")


def _last_user_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _text(message.content).strip()
    return ""


def _mentioned(option: str, hint: str) -> bool:
    lowered = hint.lower()
    return option.lower() in lowered or option.replace("_", " ").lower() in lowered


def _pick(options: Sequence[Any], hint: str) -> Any:
    for option in options:
        if _mentioned(str(option), hint):
            return option
    return options[0]


def _matching_tool(tools: Sequence[dict[str, Any]], hint: str) -> dict[str, Any] | None:
    for tool in tools:
        name = tool.get("function", {}).get("name", "")
        if name and _mentioned(name, hint):
            return tool
    return None


def _sample_object(
    schema: dict[str, Any], hint: str, defs: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Fill the required fields of a JSON schema; optional ones keep their defaults."""
    known = defs if defs is not None else schema.get("$defs") or {}
    properties: dict[str, Any] = schema.get("properties") or {}
    return {
        name: _sample_value(properties.get(name) or {}, hint, known)
        for name in schema.get("required") or []
    }


def _sample_value(spec: dict[str, Any], hint: str, defs: dict[str, Any]) -> Any:
    if ref := spec.get("$ref"):
        return _sample_value(defs.get(str(ref).rsplit("/", 1)[-1]) or {}, hint, defs)
    if enum := spec.get("enum"):
        return _pick(enum, hint)
    if "const" in spec:
        return spec["const"]
    for key in ("anyOf", "oneOf"):
        options = [
            option for option in spec.get(key) or [] if option.get("type") != "null"
        ]
        if options:
            return _sample_value(options[0], hint, defs)
    kind = spec.get("type")
    if kind == "object":
        return _sample_object(spec, hint, defs)
    return {
        "integer": 1,
        "number": 1.0,
        "boolean": False,
        "array": [],
    }.get(kind if isinstance(kind, str) else "string", hint or "mock")
