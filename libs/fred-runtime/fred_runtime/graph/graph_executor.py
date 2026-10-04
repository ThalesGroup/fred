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
The graph agent executor: a `GraphAgentDefinition` compiled to a LangGraph
`StateGraph`.

LangGraph owns the node loop, the step limit, HITL (`interrupt`) and
persistence. This module wraps node handlers and turns the `custom`/`updates`
stream into `RuntimeEvent`s, emitted as they happen.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import inspect
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, aclosing, nullcontext
from dataclasses import dataclass, replace
from typing import Any, cast

from fred_core.history.history_schema import coerce_finish_reason
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    BoundRuntimeContext,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    GraphConditionalDefinition,
    GraphDefinition,
)
from fred_sdk.contracts.runtime import (
    AgentInvokerPort,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    ExecutionInterruptedRuntimeEvent,
    Executor,
    FinalRuntimeEvent,
    HumanChoiceOption,
    HumanInputRequest,
    NodeErrorRuntimeEvent,
    RuntimeEvent,
    RuntimeEventBase,
    RuntimeServices,
)
from fred_sdk.graph.runtime import (
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeResult,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp, GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel, TypeAdapter
from pydantic_core import to_jsonable_python

from fred_runtime.graph.node_context import (
    NodeContext,
    _graph_phase_timer,
    _start_runtime_span,
)
from fred_runtime.react.react_stream_adapter import (
    extract_interrupt_request,
    split_stream_event_mode,
)
from fred_runtime.runtime_support.checkpoints import graph_thread_id
from fred_runtime.runtime_support.hitl_batch import parse_batched_human_answers
from fred_runtime.runtime_support.model_metadata import sum_token_usage
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_runtime.runtime_support.tool_approval import ToolApproval

logger = logging.getLogger(__name__)

GraphNodeHandler = Callable[
    [BaseModel, GraphNodeContext], GraphNodeResult | Awaitable[GraphNodeResult]
]


def _validated_handlers(
    *, definition: GraphAgentDefinition, graph: GraphDefinition
) -> dict[str, GraphNodeHandler]:
    raw_handlers = dict(definition.node_handlers())
    validated: dict[str, GraphNodeHandler] = {}
    for node in graph.nodes:
        handler = raw_handlers.get(node.node_id)
        if not callable(handler):
            raise RuntimeError(
                f"Graph runtime is missing an executable handler for node '{node.node_id}'."
            )
        validated[node.node_id] = cast(GraphNodeHandler, handler)
    return validated


def _next_node_id(
    *,
    graph: GraphDefinition,
    current_node_id: str,
    route_key: str | None,
) -> str | None:
    direct_edges = [edge for edge in graph.edges if edge.source == current_node_id]
    conditional = _conditional_for_node(graph, current_node_id)

    if conditional is not None and direct_edges:
        raise RuntimeError(
            f"Node '{current_node_id}' mixes direct edges and conditional routes."
        )

    if conditional is not None:
        resolved_route_key = route_key or conditional.default_route_key
        if not resolved_route_key:
            raise RuntimeError(
                f"Node '{current_node_id}' requires a route_key but none was returned."
            )
        for route in conditional.routes:
            if route.route_key == resolved_route_key:
                return route.target
        raise RuntimeError(
            f"Node '{current_node_id}' returned unknown route_key '{resolved_route_key}'."
        )

    if not direct_edges:
        return None
    if len(direct_edges) > 1:
        raise RuntimeError(
            f"Node '{current_node_id}' has multiple direct edges; use conditionals instead."
        )
    return direct_edges[0].target


def _conditional_for_node(
    graph: GraphDefinition, node_id: str
) -> GraphConditionalDefinition | None:
    for conditional in graph.conditionals:
        if conditional.source == node_id:
            return conditional
    return None


def _resequence_event(event: RuntimeEvent, sequence: int) -> RuntimeEvent:
    return cast(RuntimeEvent, event.model_copy(update={"sequence": sequence}))


def _final_event_from_output(
    output_model: BaseModel,
    *,
    model_name: str | None = None,
    token_usage: dict[str, int] | None = None,
    finish_reason: str | None = None,
) -> FinalRuntimeEvent:
    """
    Build the canonical FinalRuntimeEvent from a graph output model.

    Why this exists:
    - graph agents can return either GraphExecutionOutput or a custom output model
    - the runtime still needs one consistent final event shape for the UI

    How to use:
    - pass the validated output model plus optional model metadata captured during execution

    Example:
    - `event = _final_event_from_output(output_model, model_name=name, token_usage=usage)`
    """

    normalized_finish_reason = coerce_finish_reason(finish_reason)
    if isinstance(output_model, GraphExecutionOutput):
        return FinalRuntimeEvent(
            sequence=0,
            content=output_model.content,
            sources=output_model.sources,
            ui_parts=output_model.ui_parts,
            model_name=model_name,
            token_usage=token_usage or output_model.token_usage,
            finish_reason=normalized_finish_reason,
        )

    payload = output_model.model_dump(mode="json")
    content = payload.get("content")
    if not isinstance(content, str):
        content = json.dumps(payload, ensure_ascii=False, indent=2)
    return FinalRuntimeEvent(
        sequence=0,
        content=content,
        model_name=model_name,
        token_usage=token_usage,
        finish_reason=normalized_finish_reason,
    )


# Technical terminal node: persists `build_completed_state(...)` inside the run,
# so the next turn reads the completed state from the thread's last checkpoint.
_COMPLETE_NODE = "__fred_complete__"
_TURN_KEY = "fred_graph_turn"


@dataclass(slots=True)
class _TurnRecorder:
    """Per-run model metadata, folded in as each node finishes."""

    model_name: str | None = None
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None

    def absorb(self, context: NodeContext) -> None:
        model_name, token_usage, finish_reason = context.last_model_metadata
        if model_name:
            self.model_name = model_name
        if token_usage:
            self.token_usage = sum_token_usage(self.token_usage, token_usage)
        if finish_reason:
            self.finish_reason = finish_reason


@dataclass(slots=True)
class _RunOutcome:
    output: BaseModel | None = None
    error: Exception | None = None
    awaiting: HumanInputRequest | None = None


class _IsolatedAgentInvoker(AgentInvokerPort):
    """
    Runs an in-process callee as its own root run.

    Without this, the callee inherits the calling node's LangGraph config
    (checkpointer, task id, stream handlers) through contextvars.
    """

    def __init__(self, inner: AgentInvokerPort) -> None:
        self._inner = inner

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        isolated = contextvars.copy_context()
        isolated.run(var_child_runnable_config.set, None)
        return await asyncio.create_task(self._inner.invoke(request), context=isolated)


class GraphExecutor(Executor[BaseModel, BaseModel]):
    """
    Executor running a graph agent as a compiled LangGraph `StateGraph`.

    One LangGraph thread per (session, agent namespace). A fresh turn writes
    every state field; a resume sends `Command(resume=...)`. Nothing is kept in
    memory between calls, so any executor instance sharing the checkpointer
    can resume a pause.
    """

    def __init__(
        self,
        *,
        definition: GraphAgentDefinition,
        binding: BoundRuntimeContext,
        services: RuntimeServices,
        model: BaseChatModel | None,
        runtime_tools: tuple[BaseTool, ...],
        checkpointer: BaseCheckpointSaver,
        checkpoint_ns: str,
        tool_approval: ToolApproval | None = None,
    ) -> None:
        self._definition = definition
        self._tool_approval = tool_approval
        self._binding = binding
        self._services = (
            replace(
                services,
                agent_invoker=_IsolatedAgentInvoker(services.agent_invoker),
            )
            if services.agent_invoker is not None
            else services
        )
        self._model = model
        self._runtime_tools = {tool.name: tool for tool in runtime_tools}
        self._graph = definition.build_graph()
        self._handlers = _validated_handlers(definition=definition, graph=self._graph)
        self._allowed_tool_refs = frozenset(
            requirement.tool_ref for requirement in definition.declared_tool_refs
        )
        self._nodes_by_id = {node.node_id: node for node in self._graph.nodes}
        self._state_model = definition.state_model()
        self._adapters: dict[str, TypeAdapter[Any]] = {}
        self._checkpoint_ns = checkpoint_ns
        self._checkpointer = checkpointer
        self._compiled = self._compile(checkpointer)

    # ── compilation ──────────────────────────────────────────────────────────

    def _compile(self, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
        builder = StateGraph(self._state_model)
        for node in self._graph.nodes:
            # Explicit input_schema: LangGraph would otherwise infer one from
            # the wrapper's annotations.
            builder.add_node(
                node.node_id,
                self._node(node.node_id, self._handlers[node.node_id]),
                input_schema=self._state_model,
            )
        builder.add_node(
            _COMPLETE_NODE, self._complete_node, input_schema=self._state_model
        )
        builder.add_edge(START, self._graph.entry_node)
        builder.add_edge(_COMPLETE_NODE, END)
        return builder.compile(checkpointer=checkpointer)

    def _node(self, node_id: str, handler: GraphNodeHandler):
        on_error = self._nodes_by_id[node_id].on_error

        async def run(state: Any, config: RunnableConfig) -> Command:
            recorder = _recorder(config)
            writer = get_stream_writer()
            context = NodeContext(
                binding=self._binding,
                services=self._services,
                model=self._model,
                graph_agent_id=self._definition.agent_id,
                node_id=node_id,
                allowed_tool_refs=self._allowed_tool_refs,
                runtime_tools=self._runtime_tools,
                tuning_values=self._definition.tuning_values,
                sink=writer,
                tool_approval=self._tool_approval,
                checkpoint_tools=True,
            )
            span = _start_runtime_span(
                services=self._services,
                binding=self._binding,
                name="v2.graph.node",
                attributes={"agent_id": self._definition.agent_id, "node_id": node_id},
            )
            with _graph_phase_timer(
                metrics=self._services.metrics,
                binding=self._binding,
                agent_id=self._definition.agent_id,
                phase="v2_graph_node",
                agent_step=node_id,
                extra_dims={"node_id": node_id},
            ) as kpi_dims:
                try:
                    raw_result = handler(state, context)
                    result = GraphNodeResult.model_validate(
                        await raw_result
                        if inspect.isawaitable(raw_result)
                        else raw_result
                    )
                    if span is not None:
                        span.set_attribute("status", "ok")
                except GraphBubbleUp:
                    kpi_dims["status"] = "awaiting_human"
                    if span is not None:
                        span.set_attribute("status", "awaiting_human")
                    raise
                except Exception as exc:
                    if span is not None:
                        span.set_attribute("status", "error")
                    if on_error is None:
                        raise
                    # Caught here rather than via add_node(error_handler=...):
                    # LangGraph 1.2.12 still re-raises a handled error under
                    # astream (see test_graph_capabilities.py).
                    return self._route_error(node_id, on_error, exc)
                finally:
                    if span is not None:
                        span.end()
            recorder.absorb(context)
            target = _next_node_id(
                graph=self._graph, current_node_id=node_id, route_key=result.route_key
            )
            return Command(
                goto=target or _COMPLETE_NODE,
                update=self._jsonable(result.state_update),
            )

        return run

    def _route_error(self, node_id: str, target: str, exc: Exception) -> Command:
        """`on_error`: report the failure and continue at the fallback node."""
        message = str(exc).strip() or type(exc).__name__
        logger.warning(
            "[V2][GRAPH] Node %r raised; routing to on_error=%r. agent=%s error=%s",
            node_id,
            target,
            self._definition.agent_id,
            message,
        )
        get_stream_writer()(
            NodeErrorRuntimeEvent(
                node_id=node_id, error_message=message, routed_to=target
            )
        )
        return Command(goto=target, update=self._jsonable({"node_error": message}))

    async def _complete_node(self, state: Any) -> dict[str, object]:
        completed = self._definition.build_completed_state(state)
        return self._jsonable(_as_update(completed))

    # ── execution ────────────────────────────────────────────────────────────

    async def invoke(
        self, input_model: BaseModel, config: ExecutionConfig
    ) -> BaseModel:
        # No one to offer "continue" to: an unfinished execution restarts, as before.
        config = config.model_copy(
            update={"interrupted_action": config.interrupted_action or "restart"}
        )
        outcome = _RunOutcome()
        async for _ in self._run(input_model, config, outcome):
            pass
        if outcome.error is not None:
            raise outcome.error
        if outcome.awaiting is not None:
            raise RuntimeError(
                "Graph execution is awaiting human input. Use stream() to surface the request."
            )
        assert outcome.output is not None
        return outcome.output

    async def stream(
        self, input_model: BaseModel, config: ExecutionConfig
    ) -> AsyncGenerator[RuntimeEvent, None]:
        outcome = _RunOutcome()
        sequence = 0
        async with aclosing(self._run(input_model, config, outcome)) as events:
            async for event in events:
                yield _resequence_event(event, sequence)
                sequence += 1
        if outcome.error is not None:
            yield FinalRuntimeEvent(
                sequence=sequence, content=f"An error occurred: {outcome.error}"
            )

    async def _run(
        self,
        input_model: BaseModel,
        config: ExecutionConfig,
        outcome: _RunOutcome,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        admission: AbstractAsyncContextManager[None] = nullcontext()
        if config.interrupted_action == "continue":
            if not isinstance(self._checkpointer, FredSqlCheckpointer):
                raise RuntimeError(
                    "Graph continuation requires a persistent SQL checkpointer "
                    "with owner-lifetime admission."
                )
            admission = self._checkpointer.graph_resume_lock.acquire(
                self.thread_id(config)
            )
        async with (
            admission,
            aclosing(self._run_admitted(input_model, config, outcome)) as events,
        ):
            async for event in events:
                yield event

    async def _run_admitted(
        self,
        input_model: BaseModel,
        config: ExecutionConfig,
        outcome: _RunOutcome,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        thread = self._thread_config(config)
        snapshot = await self._compiled.aget_state(thread)
        graph_input = self._graph_input(input_model, config, snapshot)
        if isinstance(graph_input, ExecutionInterruptedRuntimeEvent):
            yield graph_input
            return
        recorder = _TurnRecorder()
        completed: BaseModel | None = None
        run_config = cast(
            RunnableConfig,
            {
                "configurable": {
                    **thread.get("configurable", {}),
                    **self._owner_keys(),
                    _TURN_KEY: recorder,
                },
                # +1: the technical completion node is one more superstep.
                "recursion_limit": config.max_steps + 1,
            },
        )
        try:
            # "sync": a step's checkpoint is persisted before the next step starts.
            # LangGraph annotates this async generator as AsyncIterator.
            async with aclosing(
                cast(
                    AsyncGenerator[Any, None],
                    self._compiled.astream(
                        graph_input,
                        config=run_config,
                        stream_mode=["custom", "updates"],
                        durability="sync",
                    ),
                )
            ) as events:
                async for raw_event in events:
                    mode, payload = split_stream_event_mode(raw_event)
                    if mode == "custom" and isinstance(payload, RuntimeEventBase):
                        yield cast(RuntimeEvent, payload)
                    elif mode == "updates":
                        request = extract_interrupt_request(payload)
                        if request is not None:
                            outcome.awaiting = request
                        if isinstance(payload, dict) and _COMPLETE_NODE in payload:
                            completed = self._state_model.model_validate(
                                payload[_COMPLETE_NODE]
                            )
        except GraphRecursionError:
            outcome.error = RuntimeError(
                f"Graph execution exceeded max_steps={config.max_steps}."
            )
            return
        except Exception as exc:
            logger.exception(
                "[V2][GRAPH] Unhandled exception in graph agent=%s",
                self._definition.agent_id,
            )
            outcome.error = exc
            return

        if outcome.awaiting is not None:
            # Resume identity is LangGraph's own `interrupt_id`, as for ReAct.
            yield AwaitingHumanRuntimeEvent(request=outcome.awaiting)
            return

        if completed is None:
            outcome.error = RuntimeError("Graph execution produced no completed state.")
            return
        output = self._definition.output_model().model_validate(
            self._definition.build_output(completed)
        )
        outcome.output = output
        yield _final_event_from_output(
            output,
            model_name=recorder.model_name,
            token_usage=recorder.token_usage,
            finish_reason=recorder.finish_reason,
        )

    def _interrupted_event(self, snapshot: Any) -> ExecutionInterruptedRuntimeEvent:
        node_id = snapshot.next[0] if snapshot.next else snapshot.tasks[0].name
        node = self._nodes_by_id.get(node_id)
        title = node.title if node is not None else "final step"
        return ExecutionInterruptedRuntimeEvent(
            request=HumanInputRequest(
                stage="execution_interrupted",
                title=f"The previous execution is unfinished at “{title}”.",
                question=(
                    "An external operation may already have happened. "
                    "Resume only after other executions have stopped. "
                    "Restart does not undo previous effects."
                ),
                choices=(
                    HumanChoiceOption(id="continue", label="Continue"),
                    HumanChoiceOption(id="restart", label="Restart"),
                    HumanChoiceOption(id="later", label="Later"),
                ),
                metadata={"node_id": node_id, "node_title": title},
            ),
            interruption_id=_interruption_id(snapshot),
        )

    def _graph_input(
        self,
        input_model: BaseModel,
        config: ExecutionConfig,
        snapshot: Any,
    ) -> Command | dict[str, object] | ExecutionInterruptedRuntimeEvent | None:
        if config.resume_payload is not None:
            pending_ids = {pending.id for pending in snapshot.interrupts}
            if not pending_ids:
                raise RuntimeError(
                    "Graph execution received a resume payload without a pending pause."
                )
            batch = parse_batched_human_answers(config.resume_payload)
            if batch is not None:
                batch_ids = {item.interrupt_id for item in batch}
                if batch_ids != pending_ids:
                    raise RuntimeError(
                        "Graph batch answers must match every pending question."
                    )
                return Command(
                    resume={item.interrupt_id: item.answer for item in batch}
                )
            if config.interrupt_id is not None:
                if config.interrupt_id not in pending_ids:
                    raise RuntimeError(
                        "Graph execution received a resume payload for a stale or unknown pause."
                    )
                return Command(resume={config.interrupt_id: config.resume_payload})
            return Command(resume=config.resume_payload)

        interrupted = _is_interrupted(snapshot)
        if config.interrupted_action == "continue":
            if not interrupted or config.interruption_id != _interruption_id(snapshot):
                raise RuntimeError(
                    "Graph execution has no interrupted step matching this interruption_id."
                )
            return None  # LangGraph resumes the thread from its last checkpoint
        if interrupted and config.interrupted_action != "restart":
            return self._interrupted_event(snapshot)

        # Carry-forward reads the thread's latest values. After an abandoned
        # pause or a failed turn these are that turn's in-flight values.
        previous_state = (
            self._state_model.model_validate(snapshot.values)
            if snapshot.values
            else None
        )
        initial_state = self._definition.build_turn_state(
            input_model,
            self._binding,
            previous_state=previous_state,
            invocation_turns=config.invocation_turns,
        )
        # Every field is written: LangGraph keeps a previous value for any
        # field left out, and skips None/default fields of a Pydantic input.
        return self._jsonable(
            _as_update(self._state_model.model_validate(initial_state))
        )

    def _jsonable(self, update: Mapping[str, object]) -> dict[str, object]:
        """
        Channel values are stored JSON-shaped; the
        state model re-validates them on every node read. Checkpoints then
        never hold agent-specific classes that need a deserialization allowlist.
        """
        fields = self._state_model.model_fields
        return {
            key: (
                self._field_adapter(key).dump_python(value, mode="json")
                if key in fields
                else to_jsonable_python(value)
            )
            for key, value in update.items()
        }

    def _field_adapter(self, name: str) -> TypeAdapter[Any]:
        adapter = self._adapters.get(name)
        if adapter is None:
            adapter = TypeAdapter(self._state_model.model_fields[name].annotation)
            self._adapters[name] = adapter
        return adapter

    def _owner_keys(self) -> dict[str, str]:
        """
        Thread owner for the SQL checkpointer (`__`-keys stay out of checkpoint
        metadata). Graph threads cannot be matched to history by session id,
        so without this a per-user erase would never find them.
        """
        runtime = self._binding.runtime_context
        portable = self._binding.portable_context
        keys = {
            "__fred_user_id": runtime.user_id or portable.user_id,
            "__fred_team_id": runtime.team_id or portable.team_id,
        }
        return {key: value for key, value in keys.items() if value}

    def thread_id(self, config: ExecutionConfig) -> str:
        """This agent's LangGraph thread for the run's session (`graph_thread_id`)."""
        session = (
            config.session_id
            or self._binding.runtime_context.session_id
            or self._binding.portable_context.session_id
            or "__default__"
        )
        return graph_thread_id(session, self._checkpoint_ns)

    def _thread_config(self, config: ExecutionConfig) -> RunnableConfig:
        return cast(
            RunnableConfig, {"configurable": {"thread_id": self.thread_id(config)}}
        )


def _recorder(config: RunnableConfig) -> _TurnRecorder:
    recorder = (config.get("configurable") or {}).get(_TURN_KEY)
    # A node replayed outside `_run` (never expected) still gets a sink.
    return recorder if isinstance(recorder, _TurnRecorder) else _TurnRecorder()


def _is_interrupted(snapshot: Any) -> bool:
    # Completed task writes can outlive a failed step checkpoint: `next` then
    # looks empty, but the engine still has tasks to settle on continuation.
    return bool(snapshot.tasks) and not snapshot.interrupts


def _checkpoint_id(config: Any) -> str | None:
    configurable = (config or {}).get("configurable", {})
    return configurable.get("checkpoint_id")


def _interruption_id(snapshot: Any) -> str:
    """Opaque id of the thread head; any later checkpoint makes it stale."""
    thread_id = snapshot.config.get("configurable", {}).get("thread_id")
    head = f"{thread_id}\0{_checkpoint_id(snapshot.config)}"
    return hashlib.sha256(head.encode()).hexdigest()[:32]


def _as_update(state: BaseModel) -> dict[str, object]:
    return {name: getattr(state, name) for name in type(state).model_fields}


__all__ = ["GraphExecutor", "GraphNodeHandler"]
