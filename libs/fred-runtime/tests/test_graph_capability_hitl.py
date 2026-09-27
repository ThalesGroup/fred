# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""Real graph checkpoints: capability approval, refusal and replay-safe tool calls."""

from __future__ import annotations

import pytest
from fred_runtime.app.agent_app import _pending_interrupt_occurrences
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.graph.graph_executor import GraphExecutor
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.integrations.v2_runtime.adapters import InProcessToolInvoker
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_runtime.runtime_support.tool_approval import CapabilityHitlBinding
from fred_sdk import GraphAgent, GraphWorkflow, StepResult, typed_node
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    HitlSpec,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import ToolRefRequirement
from fred_sdk.contracts.runtime import (
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeServices,
    ToolCallRuntimeEvent,
)
from fred_sdk.graph.runtime import GraphNodeContext
from langchain_core.tools import tool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine


class Input(BaseModel):
    message: str = "go"


class State(BaseModel):
    message: str = ""
    final_text: str = ""


def binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(language="fr"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_path", ["runtime", "ref"])
@pytest.mark.parametrize("decision", ["proceed", "cancel", "invalid"])
@pytest.mark.parametrize("gate_mode", ["required", "conditional", "disabled", "broken"])
async def test_capability_gate_survives_rebuild_without_replaying_prior_tools(
    tmp_path, monkeypatch, decision, gate_mode, tool_path
):
    replay_arguments = {"label": "first"}
    replay_tool_name = ["write_probe"]
    calls = []
    audits = []
    monkeypatch.setattr(
        "fred_runtime.runtime_support.tool_execution.emit_audit_log",
        lambda event, **data: audits.append((event, data)),
    )

    @tool("write_probe")
    async def write_probe(label: str) -> str:
        """Record one side effect."""
        calls.append(label)
        return label

    @typed_node(State)
    async def node(state: State, context: GraphNodeContext) -> StepResult:
        invoke = (
            context.invoke_runtime_tool
            if tool_path == "runtime"
            else context.invoke_tool
        )
        await invoke(replay_tool_name[0], dict(replay_arguments))
        await invoke("write_probe", {"label": "second"})
        return StepResult(state_update={"final_text": "finished"})

    class Agent(GraphAgent):
        agent_id: str = "test.graph.hitl"
        role: str = "test"
        description: str = "test"
        input_schema = Input
        state_schema = State
        declared_tool_refs: tuple[ToolRefRequirement, ...] = (
            ToolRefRequirement(tool_ref="write_probe"),
        )
        workflow = GraphWorkflow(entry="node", nodes={"node": node})

    async def write_ref(request: ToolInvocationRequest) -> ToolInvocationResult:
        calls.append(request.payload["label"])
        return ToolInvocationResult(tool_ref=request.tool_ref)

    capability_context = CapabilityContext(
        identity=CapabilityIdentity(user_id="u"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )

    def condition(request):
        assert request.context is capability_context
        assert request.tool is write_probe
        assert request.tool_call["args"]["label"] in {"first", "second"}
        if gate_mode == "broken":
            raise ValueError("Predicate unavailable")
        return gate_mode == "conditional"

    block = CapabilityAgentBlock(
        middleware=(),
        tools=(write_probe,),
        hitl={
            "write_probe": CapabilityHitlBinding(
                spec=HitlSpec(
                    tool="write_probe",
                    require=gate_mode == "required",
                    when=condition if gate_mode != "required" else None,
                    question="Confirmer ?",
                ),
                context=capability_context,
                tool=write_probe,
            )
        },
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'hitl.sqlite'}")
    try:

        async def turn(config: ExecutionConfig):
            # Rebuild both saver and runtime: no executor-local state can save us.
            saver = FredSqlCheckpointer(engine)
            await saver._ensure_tables()
            runtime = GraphRuntime(
                definition=Agent(),
                services=RuntimeServices(
                    checkpointer=saver,
                    tool_invoker=InProcessToolInvoker(
                        handlers={"write_probe": write_ref}
                    ),
                ),
                capability_block=block,
            )
            executor = await runtime.build_executor(binding())
            assert isinstance(executor, GraphExecutor)
            events = [event async for event in executor.stream(Input(), config)]
            if isinstance(events[-1], AwaitingHumanRuntimeEvent):
                checkpoint = await saver.aget_tuple(
                    {"configurable": {"thread_id": executor.thread_id(config)}}
                )
                assert checkpoint is not None
                request = events[-1].request
                assert (request.interrupt_id, request.occurrence_id) in (
                    _pending_interrupt_occurrences(checkpoint.pending_writes or ())
                )
                assert request.interrupt_id is not None
                for expected in (True, False):
                    token = await saver.aclaim_hitl_resume(
                        thread_id=executor.thread_id(config),
                        checkpoint_ns="",
                        interrupt_id=request.interrupt_id,
                        occurrence_id=request.occurrence_id,
                    )
                    assert (token is not None) is expected
            return events

        events = await turn(ExecutionConfig(session_id="s"))
        if gate_mode == "disabled":
            assert isinstance(events[-1], FinalRuntimeEvent)
            assert calls == ["first", "second"]
            assert len(audits) == 4
            return
        first = events[-1]
        assert isinstance(first, AwaitingHumanRuntimeEvent), events
        assert first.request.question == "Confirmer ?"
        assert calls == []
        assert audits == []
        assert first.request.pending_calls[0].tool_call_id == next(
            e.call_id for e in events if isinstance(e, ToolCallRuntimeEvent)
        )
        replay_arguments["label"] = "changed-after-approval"
        replay_tool_name[0] = "different-tool-after-approval"
        events = await turn(
            ExecutionConfig(
                session_id="s",
                interrupt_id=first.request.interrupt_id,
                resume_payload={"choice_id": decision},
            )
        )
        second = events[-1]
        assert isinstance(second, AwaitingHumanRuntimeEvent), events
        assert calls == (["first"] if decision == "proceed" else [])
        assert len(audits) == (2 if decision == "proceed" else 0)
        # A later task has a different interrupt id, even in the same authored node.
        assert second.request.interrupt_id != first.request.interrupt_id
        assert second.request.occurrence_id != first.request.occurrence_id
        events = await turn(
            ExecutionConfig(
                session_id="s",
                interrupt_id=second.request.interrupt_id,
                resume_payload={"choice_id": "proceed"},
            )
        )
        assert isinstance(events[-1], FinalRuntimeEvent), events
        assert events[-1].content == "finished"
        assert calls == (["first", "second"] if decision == "proceed" else ["second"])
        assert len(audits) == len(calls) * 2
        # Completed task replay emits neither a duplicate call nor audit record.
        resumed_calls = [e for e in events if isinstance(e, ToolCallRuntimeEvent)]
        assert len(resumed_calls) == 1
        assert resumed_calls[0].call_id == second.request.pending_calls[0].tool_call_id
    finally:
        await engine.dispose()
