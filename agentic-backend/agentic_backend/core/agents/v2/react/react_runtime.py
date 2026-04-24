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
Executable runtime for v2 ReAct agents.

Use this file to understand how a ReAct definition is executed in Fred:
1. Convert typed input messages to LangChain messages.
2. Build the tool loop from declared `declared_tool_refs`.
3. Stream runtime events (assistant delta, tool call/result, final).

Scope of this file:
- this runtime is only for the ReAct family of agents
- graph agents use `graph_runtime.py`, which has a different execution model
- deep agents reuse most of this ReAct runtime surface, but swap the internal
  compiled-agent engine in `deep_runtime.py`

If you are debugging a ReAct agent in production, this is the first file to
open.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import cast

from fred_core.store import VectorSearchHit
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
)
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from ..contracts.context import (
    BoundRuntimeContext,
    UiPart,
)
from ..contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from ..contracts.react_contract import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActOutput,
    ReActToolCall,
)
from ..contracts.runtime import (
    AgentRuntime,
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    Executor,
    FinalRuntimeEvent,
    RuntimeEvent,
    RuntimeServices,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
    TracerPort,
)

# Everything imported from `react_langchain_adapter` below is SDK-bound glue.
# Read it as one boundary:
# - this file should decide when Fred invokes, streams, and emits runtime events
# - the adapter file should deal with LangChain messages, stream payload shapes,
#   and runnable config translation
from .react_langchain_adapter import (
    REACT_MODEL_OPERATION_ROUTING,
)
from .react_langchain_adapter import (
    CompiledReActAgent as _CompiledReActAgent,
)
from .react_langchain_adapter import (
    assistant_delta_from_stream_event as _assistant_delta_from_stream_event,
)
from .react_langchain_adapter import (
    build_tool_loop_model_call_wrapper as _build_tool_loop_model_call_wrapper,
)
from .react_langchain_adapter import (
    extract_interrupt_request as _extract_interrupt_request,
)
from .react_langchain_adapter import (
    extract_messages_from_update as _extract_messages_from_update,
)
from .react_langchain_adapter import (
    final_assistant_message as _final_assistant_message_adapter,
)
from .react_langchain_adapter import (
    from_langchain_message as _from_langchain_message_adapter,
)
from .react_langchain_adapter import (
    graph_input_from_react_input as _graph_input_adapter,
)
from .react_langchain_adapter import (
    infer_react_model_operation_from_messages as _infer_react_model_operation_from_messages,
)
from .react_langchain_adapter import (
    merge_sources as _merge_sources,
)
from .react_langchain_adapter import (
    merge_ui_parts as _merge_ui_parts,
)
from .react_langchain_adapter import (
    normalize_tool_artifact as _normalize_tool_artifact,
)
from .react_langchain_adapter import (
    runtime_metadata_from_message as _runtime_metadata_from_message,
)
from .react_langchain_adapter import (
    runtime_metadata_from_stream_event as _runtime_metadata_from_stream_event,
)
from .react_langchain_adapter import (
    split_stream_event_mode as _split_stream_event_mode,
)
from .react_langchain_adapter import (
    to_runnable_config as _to_runnable_config,
)
from .react_prompting import (
    build_guardrail_suffix as _build_guardrail_suffix,
)
from .react_prompting import (
    render_prompt_template as _render_prompt_template,
)
from .react_tool_binding import (
    ReActToolBinder,
)
from .react_tool_binding import (
    build_runtime_tool_prompt_suffix as _build_runtime_tool_prompt_suffix,
)
from .react_tool_loop import build_tool_loop_compiled_react_agent
from .react_tool_rendering import stringify_tool_output as _stringify_content
from .react_tool_resolution import ReActRuntimeToolResolver
from .react_tool_utils import sanitize_tool_name as _sanitize_tool_name

logger = logging.getLogger(__name__)

__all__ = [
    "ReActInput",
    "ReActMessage",
    "ReActMessageRole",
    "ReActOutput",
    "ReActRuntime",
    "ReActToolCall",
    "_to_runnable_config",
]


def _graph_input(
    input_model: ReActInput,
    config: ExecutionConfig,
) -> object:
    """
    Convert Fred ReAct input to the compiled-agent graph input shape.

    Why this exists:
    - `react_runtime.py` should call one local helper instead of repeating the
      adapter call plus `sanitize_tool_name=_sanitize_tool_name`
    - that keeps the executor code readable while the LangChain-specific shape
      stays in the adapter module

    How to use:
    - pass the validated `ReActInput` plus `ExecutionConfig` before invoking the
      compiled agent

    Example:
    - `_graph_input(input_model, ExecutionConfig())`
    """

    return _graph_input_adapter(
        input_model,
        config,
        sanitize_tool_name=_sanitize_tool_name,
    )


class _TransportBackedReActExecutor(Executor[ReActInput, ReActOutput]):
    """
    Executes one ReAct run against the compiled LangChain/LangGraph agent.

    Why this class exists:
    - the compiled LangChain/LangGraph agent returns SDK-shaped messages and stream
      updates
    - Fred needs one place that turns those updates into `RuntimeEvent` values such
      as assistant deltas, tool calls, tool results, and the final answer

    How to use:
    - build this executor from `ReActRuntime.build_executor(...)`
    - call `invoke(...)` for one-shot execution or `stream(...)` for runtime events

    Example:
    - `executor = _TransportBackedReActExecutor(...)`
    """

    def __init__(
        self,
        *,
        compiled_agent: _CompiledReActAgent,
        binding: BoundRuntimeContext,
        services: RuntimeServices,
    ) -> None:
        self._compiled_agent = compiled_agent
        self._binding = binding
        self._services = services

    async def invoke(
        self,
        input_model: ReActInput,
        config: ExecutionConfig,
        *,
        context: object | None = None,
    ) -> ReActOutput:
        span = None
        if self._services.tracer is not None:
            span = self._services.tracer.start_span(
                name="agent.invoke",
                context=self._binding.portable_context,
                attributes={"agent_id": self._binding.portable_context.agent_id or ""},
            )
        try:
            result = await self._compiled_agent.ainvoke(
                _graph_input(input_model, config),
                config=_to_runnable_config(config),
                context=context,
            )
            transcript = tuple(
                _from_langchain_message_adapter(
                    message,
                    sanitize_tool_name=_sanitize_tool_name,
                )
                for message in result["messages"]
                if isinstance(message, BaseMessage)
            )
            final_message = _final_assistant_message_adapter(
                result["messages"],
                sanitize_tool_name=_sanitize_tool_name,
            )
            return ReActOutput(final_message=final_message, transcript=transcript)
        finally:
            if span is not None:
                span.end()

    async def stream(
        self,
        input_model: ReActInput,
        config: ExecutionConfig,
        *,
        context: object | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        span = None
        if self._services.tracer is not None:
            span = self._services.tracer.start_span(
                name="agent.stream",
                context=self._binding.portable_context,
                attributes={"agent_id": self._binding.portable_context.agent_id or ""},
            )

        sequence = 0
        last_assistant_message: ReActMessage | None = None
        collected_sources: tuple[VectorSearchHit, ...] = ()
        collected_ui_parts: tuple[UiPart, ...] = ()
        last_model_name: str | None = None
        last_token_usage: dict[str, int] | None = None
        last_finish_reason: str | None = None
        # When any tool returns is_error=True, the error is surfaced directly as
        # the final response.  The LLM is NOT trusted to relay it: its subsequent
        # turn is consumed but discarded, and its streaming deltas are suppressed.
        last_tool_error: str | None = None
        suppress_assistant_deltas: bool = False
        try:
            async for raw_event in self._compiled_agent.astream(
                _graph_input(input_model, config),
                config=_to_runnable_config(config),
                stream_mode=["messages", "updates"],
                context=context,
            ):
                mode, update = _split_stream_event_mode(raw_event)

                if mode == "messages":
                    model_name, token_usage, finish_reason = (
                        _runtime_metadata_from_stream_event(update)
                    )
                    if model_name is not None:
                        last_model_name = model_name
                    if token_usage is not None:
                        last_token_usage = token_usage
                    if finish_reason is not None:
                        last_finish_reason = finish_reason
                    delta = _assistant_delta_from_stream_event(update)
                    if delta is not None and not suppress_assistant_deltas:
                        yield AssistantDeltaRuntimeEvent(
                            sequence=sequence,
                            delta=delta,
                        )
                        sequence += 1
                    continue

                if mode != "updates":
                    continue

                interrupt_request = _extract_interrupt_request(update)
                if interrupt_request is not None:
                    yield AwaitingHumanRuntimeEvent(
                        sequence=sequence,
                        request=interrupt_request,
                    )
                    sequence += 1
                    continue

                for message in _extract_messages_from_update(update):
                    if isinstance(message, ToolMessage):
                        artifact = _normalize_tool_artifact(message.artifact)
                        sources = artifact.sources if artifact is not None else ()
                        ui_parts = artifact.ui_parts if artifact is not None else ()
                        collected_sources = _merge_sources(collected_sources, sources)
                        collected_ui_parts = _merge_ui_parts(
                            collected_ui_parts, ui_parts
                        )
                        is_error = artifact.is_error if artifact is not None else False
                        if is_error:
                            # Strip the "Tool error:\n" prefix added for the LLM's
                            # benefit — the user-facing message should be clean.
                            raw = _stringify_content(message.content)
                            last_tool_error = raw.removeprefix("Tool error:\n")
                            suppress_assistant_deltas = True
                            logger.debug(
                                "[V2][REACT] tool error intercepted tool=%s — "
                                "suppressing LLM turn, surfacing error directly",
                                message.name,
                            )
                        yield ToolResultRuntimeEvent(
                            sequence=sequence,
                            call_id=message.tool_call_id,
                            content=_stringify_content(message.content),
                            tool_name=message.name,
                            is_error=is_error,
                            sources=sources,
                            ui_parts=ui_parts,
                        )
                        sequence += 1
                        continue

                    if isinstance(message, AIMessage) and message.tool_calls:
                        for tool_call in message.tool_calls:
                            yield ToolCallRuntimeEvent(
                                sequence=sequence,
                                tool_name=str(tool_call.get("name") or ""),
                                call_id=str(tool_call.get("id") or ""),
                                arguments=cast(
                                    dict[str, object], tool_call.get("args") or {}
                                ),
                            )
                            sequence += 1
                        continue

                    if isinstance(message, AIMessage):
                        model_name, token_usage, finish_reason = (
                            _runtime_metadata_from_message(message)
                        )
                        if model_name is not None:
                            last_model_name = model_name
                        if token_usage is not None:
                            last_token_usage = token_usage
                        if finish_reason is not None:
                            last_finish_reason = finish_reason
                        last_assistant_message = _from_langchain_message_adapter(
                            message,
                            sanitize_tool_name=_sanitize_tool_name,
                        )

            if last_tool_error is not None or last_assistant_message is not None:
                final_content = (
                    last_tool_error
                    if last_tool_error is not None
                    else last_assistant_message.content  # type: ignore[union-attr]
                )
                yield FinalRuntimeEvent(
                    sequence=sequence,
                    content=final_content,
                    sources=collected_sources,
                    ui_parts=collected_ui_parts,
                    model_name=last_model_name,
                    token_usage=last_token_usage,
                    finish_reason=last_finish_reason,
                )
        finally:
            if span is not None:
                span.end()


class ReActRuntime(AgentRuntime[ReActAgentDefinition, ReActInput, ReActOutput]):
    """
    Runtime implementation for `ReActAgentDefinition`.

    A ReActRuntime is created by the runtime factory when a ReActAgentDefinition is activated. It is responsible for:
    - binding to runtime services such as tool providers, artifact publishers, and resource readers
    - building the compiled agent executor with the resolved tools and system prompt
    - streaming runtime events from the compiled agent and converting them to `RuntimeEvent` values

    Boundary of this class:
    - this class is for the ReAct family only
    - graph agents do not use it
    - deep agents subclass it because they keep the same input/output/events and
      only replace the internal LangChain/deepagents executor

    Where to look when customizing behavior:
    - tool wiring: `build_executor(...)` and `_create_compiled_react_agent(...)`
    - streaming/final event shape: `_TransportBackedReActExecutor`
    - bind/activation logic: `on_bind(...)` and `on_activate(...)`
    """

    def __init__(self, *, definition: ReActAgentDefinition, services: RuntimeServices):
        super().__init__(definition=definition, services=services)
        self._model: BaseChatModel | None = None

    def on_bind(self, binding: BoundRuntimeContext) -> None:
        if self.services.tool_provider is not None:
            self.services.tool_provider.bind(binding)
        if self.services.artifact_publisher is not None:
            self.services.artifact_publisher.bind(binding)
        if self.services.resource_reader is not None:
            self.services.resource_reader.bind(binding)

    async def on_activate(self, binding: BoundRuntimeContext) -> None:
        if self.services.chat_model_factory is None:
            raise RuntimeError(
                "ReActRuntime requires RuntimeServices.chat_model_factory."
            )
        self._model = cast(
            BaseChatModel,
            self.services.chat_model_factory.build(self.definition, binding),
        )
        if self.services.tool_provider is not None:
            await self.services.tool_provider.activate()

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[ReActInput, ReActOutput]:
        if self._model is None:
            raise RuntimeError("ReActRuntime model is not initialized.")

        policy = self.definition.policy()
        if policy.tool_selection.max_tool_calls_per_turn is not None:
            raise NotImplementedError(
                "Per-turn tool-call limits are not enforced by the first v2 ReAct runtime yet."
            )

        logger.debug(
            "[V2][EXECUTOR] build start agent=%s declared_tool_refs=%r toolset_key=%r",
            self.definition.agent_id,
            [r.tool_ref for r in self.definition.declared_tool_refs],
            self._toolset_key(),
        )
        runtime_tools = ReActRuntimeToolResolver(
            declared_tool_refs=self.definition.declared_tool_refs,
            toolset_key=self._toolset_key(),
            services=self.services,
            binding=binding,
        ).resolve_tools()
        bound_tools = ReActToolBinder(
            runtime_tools=runtime_tools,
            tracer=self.services.tracer,
            binding=binding,
        ).build_tools()
        logger.debug(
            "[V2][EXECUTOR] bound_tools=%d names=%r",
            len(bound_tools),
            [bt.tool.name for bt in bound_tools],
        )
        system_prompt = _render_prompt_template(
            policy.system_prompt_template or "",
            binding=binding,
            agent_id=self.definition.agent_id,
        )
        logger.debug(
            "[V2][EXECUTOR] system_prompt_preview=%r",
            (system_prompt[:200] + "...")
            if len(system_prompt) > 200
            else system_prompt,
        )
        system_prompt = (
            f"{system_prompt}"
            f"{_build_runtime_tool_prompt_suffix(bound_tools)}"
            f"{_build_guardrail_suffix(self.definition)}"
        )
        available_tool_names = {
            bound_tool.runtime_name
            for bound_tool in bound_tools
            if bound_tool.runtime_name
        }

        compiled_agent = _create_compiled_react_agent(
            model=self._model,
            tools=[bound_tool.tool for bound_tool in bound_tools],
            system_prompt=system_prompt,
            binding=binding,
            approval_policy=policy.tool_approval,
            checkpointer=cast(Checkpointer, self.services.checkpointer),
            tracer=self.services.tracer,
            chat_model_factory=self.services.chat_model_factory,
            definition=self.definition,
            available_tool_names=available_tool_names,
        )
        return _TransportBackedReActExecutor(
            compiled_agent=compiled_agent,
            binding=binding,
            services=self.services,
        )

    async def on_dispose(self) -> None:
        if self.services.tool_provider is not None:
            await self.services.tool_provider.aclose()
        self._model = None

    def _toolset_key(self) -> str | None:
        """
        Return the optional toolset registry key for this definition.

        Why this exists:
        - registered toolsets are keyed separately from the agent id
        - the runtime should normalize that optional key once before tool binding

        How to use:
        - call before resolving registered tool specs

        Example:
        - `toolset_key = self._toolset_key()`
        """

        raw = getattr(self.definition, "toolset_key", None)
        if not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        return cleaned or None


def _create_compiled_react_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    binding: BoundRuntimeContext,
    approval_policy: ToolApprovalPolicy,
    checkpointer: Checkpointer,
    tracer: TracerPort | None,
    chat_model_factory: object | None,
    definition: ReActAgentDefinition,
    available_tool_names: set[str] | frozenset[str],
) -> _CompiledReActAgent:
    """
    Create the compiled ReAct agent implementation used at runtime.

    Why this exists:
    - plain ReAct and HITL should run through the same tool loop so message memory,
      tool execution, and deterministic filesystem continuation behave the same
    - runtime construction still needs one place to wire model routing, approval,
      tracing, and checkpointing together

    Who calls it:
    - `ReActRuntime.build_executor(...)` during runtime build

    When it is called:
    - once per fresh runtime instance

    Expected inputs / invariants:
    - `model` is a base chat model already selected by runtime factory
    - `tools` are validated and ready to bind
    - `checkpointer` is available for resumability

    Return / side effects:
    - returns one compiled agent implementing `_CompiledReActAgent`
    - no immediate side effects beyond graph/agent object construction

    Fallback / errors:
    - construction errors propagate directly

    Observability signals to look at:
    - dynamic routing path: `[V2][MODEL_ROUTING]` logs
    - model-call tracing path: `v2.react.model` spans
    """
    return cast(
        _CompiledReActAgent,
        build_tool_loop_compiled_react_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            binding=binding,
            approval_policy=approval_policy,
            checkpointer=checkpointer,
            chat_model_factory=chat_model_factory,
            definition=definition,
            infer_operation_from_messages=_infer_react_model_operation_from_messages,
            default_operation=REACT_MODEL_OPERATION_ROUTING,
            available_tool_names=available_tool_names,
            model_call_wrapper=_build_tool_loop_model_call_wrapper(
                tracer=tracer,
                binding=binding,
                infer_operation_from_messages=_infer_react_model_operation_from_messages,
                default_operation=REACT_MODEL_OPERATION_ROUTING,
            ),
        ),
    )
