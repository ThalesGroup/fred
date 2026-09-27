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
Real LangGraph integration proof for the #2216 P1 HITL resume identity model.

Why this file exists:
- `test_react_message_codec_resume.py` and `test_sql_checkpointer_hitl_claim.py`
  prove the codec and the claim table in isolation, each against a fake or
  minimal stand-in; neither exercises the real production tool loop end to
  end against a real LangGraph-emitted `Interrupt.id`.
- `test_hitl_resume_two_sequential_prompts_get_different_interrupt_ids`
  (`test_react_loop_regressions_1972.py`) already proves two DISTINCT FRED
  HITL occurrences get different ids through the real tool loop, but uses
  `InMemorySaver` and a raw scalar `Command(resume=...)` — it does not
  exercise `FredSqlCheckpointer`, `graph_input_from_react_input`'s targeted
  map-form resume, or a stale-vs-live id collision.
- this file closes that gap: one real compiled agent
  (`build_tool_loop_compiled_react_agent` — the actual production tool
  loop, `FredHitlMiddleware` included), one real `FredSqlCheckpointer`
  (SQLite-backed, not `InMemorySaver`), the actual `Interrupt` objects
  LangGraph emits (not the `"interrupt-a"` placeholder other unit tests
  use), and `graph_input_from_react_input` building every resume
  `Command`.

Proves, in one continuous run:
  A. the emitted id is the native LangGraph id, round-tripped unchanged by
     `extract_interrupt_request`
  B. a targeted resume with A's id executes A's tool exactly once
  C. a later, distinct FRED HITL prompt (B) gets a different id
  D. submitting A's stale id while B is pending does not execute B's tool
     and leaves B re-emitted, pending, unchanged
  E. a targeted resume with B's own id executes B's tool exactly once
  F. a resume with no interrupt_id at all fails closed (codec-level)

A second test pins WHERE that pending interrupt is stored: LangGraph
discards a root graph's `checkpoint_ns`, so the resume gate must read
unnamespaced or find nothing.

Does NOT use fake pending-write dictionaries for any of this — every
interrupt and every resume goes through the real compiled graph and the
real checkpointer.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

import pytest
from fred_runtime.app.agent_app import _pending_react_v2_interrupt_occurrences
from fred_runtime.react.react_message_codec import graph_input_from_react_input
from fred_runtime.react.react_stream_adapter import extract_interrupt_request
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_runtime.runtime_support.checkpoints import (
    AsyncCheckpointReader,
    load_checkpoint,
)
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.react_contract import ReActInput
from fred_sdk.contracts.runtime import ExecutionConfig, HumanInputRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Checkpointer, Command, Interrupt, interrupt
from pydantic import Field
from sqlalchemy.ext.asyncio import create_async_engine


class _RecordingModel(BaseChatModel):
    """Deterministic scripted model — identical shape to the one in
    `test_react_loop_regressions_1972.py`, kept local so this file has no
    cross-test-file dependency."""

    script: list[AIMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "recording-2216-integration"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_RecordingModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


class _FakeDefinition:
    agent_id = "agent-2216-integration"


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="request-2216",
            correlation_id="correlation-2216",
            actor="user-2216",
            tenant="team-2216",
            environment=PortableEnvironment.DEV,
        ),
    )


async def _drive(agent: Any, payload: object, thread: str) -> list[dict[str, Any]]:
    """Stream one run and return only the `updates`-mode events, exactly like
    `_TransportBackedReActExecutor.stream`."""

    config = {"configurable": {"thread_id": thread}}
    updates: list[dict[str, Any]] = []
    async for mode, update in agent.astream(
        payload, config=config, stream_mode=["messages", "updates"]
    ):
        if mode == "updates" and isinstance(update, dict):
            updates.append(update)
    return updates


def _find_interrupt_update(updates: list[dict[str, Any]]) -> dict[str, Any]:
    for update in updates:
        if "__interrupt__" in update:
            return update
    raise AssertionError("no pending interrupt found in this turn's updates")


def _interrupt_object(update: dict[str, Any]) -> Interrupt:
    raw = update["__interrupt__"]
    first = raw[0] if isinstance(raw, (list, tuple)) else raw
    assert isinstance(first, Interrupt), (
        f"expected a real LangGraph Interrupt object, got {type(first)!r}"
    )
    return first


def _interrupt_objects(update: dict[str, Any]) -> tuple[Interrupt, ...]:
    raw = update["__interrupt__"]
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    assert all(isinstance(value, Interrupt) for value in values)
    return tuple(values)


def _all_interrupt_objects(updates: list[dict[str, Any]]) -> tuple[Interrupt, ...]:
    return tuple(
        value
        for update in updates
        if "__interrupt__" in update
        for value in _interrupt_objects(update)
    )


@pytest.mark.asyncio
async def test_tool_pauses_keep_occurrence_identity_across_replay(tmp_path) -> None:
    seen_occurrences: list[str] = []

    @tool
    def ask_user(
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> str:
        """Ask one pure question and return its answer."""

        seen_occurrences.append(tool_call_id)
        answer = interrupt(
            HumanInputRequest(
                question=question,
                occurrence_id=tool_call_id,
            ).model_dump(mode="json")
        )
        assert isinstance(answer, dict)
        return str(answer["text"])

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("ask_user", {"question": "First?"}, "ask-1"),
                    _tool_call("ask_user", {"question": "Second?"}, "ask-2"),
                ],
            ),
            AIMessage(content="done"),
        ]
    )

    db_path = tmp_path / "tool_pause_replay.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        checkpointer = FredSqlCheckpointer(engine, prefix="v2_")
        agent = build_tool_loop_compiled_react_agent(
            model=model,
            tools=[ask_user],
            system_prompt="Ask both questions.",
            binding=_binding(),
            approval_policy=ToolApprovalPolicy(enabled=False),
            checkpointer=cast(Checkpointer, checkpointer),
            definition=cast(ReActAgentDefinition, _FakeDefinition()),
            available_tool_names={"ask_user"},
        )
        thread_id = "t-tool-pause-replay"

        first_updates = await _drive(
            agent,
            {"messages": [HumanMessage("ask both questions")]},
            thread_id,
        )
        first_interrupts = _all_interrupt_objects(first_updates)
        assert len(first_interrupts) == 2

        # Each interrupting task yields its own `updates` event, so parsing the
        # run exactly as `react_runtime` does surfaces BOTH pauses — and the
        # still-pending sibling is surfaced again by the resumed run below.
        surfaced = [
            request
            for update in first_updates
            if (request := extract_interrupt_request(update)) is not None
        ]
        # Concurrent tool pauses can arrive in either completion order.
        assert sorted((request.occurrence_id for request in surfaced), key=str) == [
            "ask-1",
            "ask-2",
        ]

        first_requests = [
            extract_interrupt_request({"__interrupt__": (value,)})
            for value in first_interrupts
        ]
        assert all(request is not None for request in first_requests)
        assert sorted(
            (request.occurrence_id for request in first_requests if request), key=str
        ) == [
            "ask-1",
            "ask-2",
        ]
        first_by_occurrence = {
            request.occurrence_id: interrupt_value
            for request, interrupt_value in zip(
                first_requests, first_interrupts, strict=True
            )
            if request is not None
        }

        resumed = await _drive(
            agent,
            Command(resume={first_by_occurrence["ask-1"].id: {"text": "one"}}),
            thread_id,
        )
        replayed_interrupts = _all_interrupt_objects(resumed)
        assert len(replayed_interrupts) == 1
        replayed_request = extract_interrupt_request(
            {"__interrupt__": replayed_interrupts}
        )
        assert replayed_request is not None
        assert replayed_request.interrupt_id == first_by_occurrence["ask-2"].id
        assert replayed_request.occurrence_id == "ask-2"
        assert sorted(seen_occurrences) == ["ask-1", "ask-1", "ask-2", "ask-2"]

        completed = await _drive(
            agent,
            Command(resume={first_by_occurrence["ask-2"].id: {"text": "two"}}),
            thread_id,
        )
        assert not _all_interrupt_objects(completed)
        assert sorted(seen_occurrences) == [
            "ask-1",
            "ask-1",
            "ask-2",
            "ask-2",
            "ask-2",
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_hitl_resume_identity_model_against_real_langgraph_and_sql_checkpointer(
    tmp_path,
) -> None:
    effects: list[str] = []

    @tool
    def update_ticket(ticket_id: str) -> str:
        """Update one ticket (approval-gated) — records the effect for the test."""

        effects.append(ticket_id)
        return f"updated {ticket_id}"

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("update_ticket", {"ticket_id": "INC-1"}, "c-1")],
            ),
            AIMessage(
                content="",
                tool_calls=[_tool_call("update_ticket", {"ticket_id": "INC-2"}, "c-2")],
            ),
            AIMessage(content="both done"),
        ]
    )

    db_path = tmp_path / "hitl_integration.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        checkpointer = FredSqlCheckpointer(engine, prefix="v2_")

        agent = build_tool_loop_compiled_react_agent(
            model=model,
            tools=[update_ticket],
            system_prompt="You update tickets.",
            binding=_binding(),
            approval_policy=ToolApprovalPolicy(
                enabled=True, always_require_tools=("update_ticket",)
            ),
            checkpointer=cast(Checkpointer, checkpointer),
            definition=cast(ReActAgentDefinition, _FakeDefinition()),
            available_tool_names={"update_ticket"},
        )
        thread_id = "t-2216-integration"

        # --- Turn 1: fresh input -> interrupt A ------------------------------
        updates_1 = await _drive(
            agent,
            {"messages": [HumanMessage("update INC-1 then INC-2")]},
            thread_id,
        )
        interrupt_update_a = _find_interrupt_update(updates_1)
        interrupt_a = _interrupt_object(interrupt_update_a)

        # Proof A: the id is the real LangGraph id (xxh3-128 hex, 32 chars —
        # not the "interrupt-a"-style placeholder other unit tests use), and
        # `extract_interrupt_request` round-trips it unchanged.
        assert isinstance(interrupt_a.id, str)
        assert len(interrupt_a.id) == 32
        assert all(c in "0123456789abcdef" for c in interrupt_a.id)
        request_a = extract_interrupt_request(interrupt_update_a)
        assert request_a is not None
        assert request_a.interrupt_id == interrupt_a.id
        assert request_a.checkpoint_id is None  # never aliased

        assert effects == []  # nothing executed yet — still pending approval

        # --- Resume A via the real codec -------------------------------------
        command_a = graph_input_from_react_input(
            ReActInput.model_construct(messages=()),
            ExecutionConfig(
                session_id=thread_id,
                interrupt_id=interrupt_a.id,
                resume_payload={"choice_id": "proceed"},
            ),
            sanitize_tool_name=lambda name: name,
        )
        assert isinstance(command_a, Command)
        assert command_a.resume == {interrupt_a.id: {"choice_id": "proceed"}}

        updates_2 = await _drive(agent, command_a, thread_id)

        # Proof B: resuming A executed A's tool exactly once.
        assert effects == ["INC-1"]

        # The model replanned and produced a second gated call -> interrupt B.
        interrupt_update_b = _find_interrupt_update(updates_2)
        interrupt_b = _interrupt_object(interrupt_update_b)

        # Proof C: a later, distinct FRED HITL occurrence gets a different id.
        assert interrupt_b.id != interrupt_a.id
        request_b = extract_interrupt_request(interrupt_update_b)
        assert request_b is not None
        assert request_b.interrupt_id == interrupt_b.id

        # --- Submit A's STALE id while B is pending ---------------------------
        command_stale_a = graph_input_from_react_input(
            ReActInput.model_construct(messages=()),
            ExecutionConfig(
                session_id=thread_id,
                interrupt_id=interrupt_a.id,
                resume_payload={"choice_id": "proceed"},
            ),
            sanitize_tool_name=lambda name: name,
        )
        updates_3 = await _drive(agent, command_stale_a, thread_id)

        # Proof D: B's tool did not execute, and B is re-emitted, pending,
        # with the SAME id — LangGraph's own targeted resume-map matching
        # (`Command(resume={id: ...})`) refuses to apply A's decision to B's
        # task, and simply re-raises the unchanged interrupt.
        assert effects == ["INC-1"]
        interrupt_update_b_again = _find_interrupt_update(updates_3)
        interrupt_b_again = _interrupt_object(interrupt_update_b_again)
        assert interrupt_b_again.id == interrupt_b.id

        # --- Submit B's own id -------------------------------------------------
        command_b = graph_input_from_react_input(
            ReActInput.model_construct(messages=()),
            ExecutionConfig(
                session_id=thread_id,
                interrupt_id=interrupt_b.id,
                resume_payload={"choice_id": "proceed"},
            ),
            sanitize_tool_name=lambda name: name,
        )
        updates_4 = await _drive(agent, command_b, thread_id)

        # Proof E: resuming B executed B's tool exactly once — total effects
        # across the whole run are exactly one INC-1 and one INC-2.
        assert effects == ["INC-1", "INC-2"]
        assert not any("__interrupt__" in update for update in updates_4)

        # Proof F: a resume with no interrupt_id at all fails closed — no
        # scalar Command(resume=...) fallback exists for ReAct V2.
        with pytest.raises(RuntimeError, match="interrupt_id"):
            graph_input_from_react_input(
                ReActInput.model_construct(messages=()),
                ExecutionConfig(
                    session_id=thread_id,
                    resume_payload={"choice_id": "proceed"},
                ),
                sanitize_tool_name=lambda name: name,
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_paused_checkpoint_is_stored_unnamespaced_whatever_the_config_asks(
    tmp_path,
) -> None:
    """
    A per-agent `checkpoint_ns` on a root graph never reaches storage, so the
    resume gate must not look for one.

    Driven through the real tool loop and a real `FredSqlCheckpointer`, with
    the namespaced config the ReAct executor used to build: LangGraph resets
    `checkpoint_ns` to `""` (`pregel/_loop.py::PregelLoop.__init__`), the
    paused checkpoint and its `__interrupt__` write land there, and a read at
    the per-agent namespace finds nothing at all — which is what turned every
    ReAct V2 HITL resume into a 409.
    """

    @tool
    def update_ticket(ticket_id: str) -> str:
        """Update one ticket (approval-gated)."""

        return f"updated {ticket_id}"

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("update_ticket", {"ticket_id": "INC-1"}, "c-1")],
            )
        ]
    )

    db_path = tmp_path / "hitl_namespace.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        checkpointer = FredSqlCheckpointer(engine, prefix="v2_")
        reader = cast(AsyncCheckpointReader, checkpointer)
        agent: Any = build_tool_loop_compiled_react_agent(
            model=model,
            tools=[update_ticket],
            system_prompt="You update tickets.",
            binding=_binding(),
            approval_policy=ToolApprovalPolicy(
                enabled=True, always_require_tools=("update_ticket",)
            ),
            checkpointer=cast(Checkpointer, checkpointer),
            definition=cast(ReActAgentDefinition, _FakeDefinition()),
            available_tool_names={"update_ticket"},
        )
        thread_id = "t-namespace-integration"
        agent_ns = "instance-namespace-integration"

        updates: list[dict[str, Any]] = []
        async for mode, update in agent.astream(
            {"messages": [HumanMessage(content="update INC-1")]},
            config={
                "configurable": {"thread_id": thread_id, "checkpoint_ns": agent_ns}
            },
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates" and isinstance(update, dict):
                updates.append(update)

        interrupt = _interrupt_object(_find_interrupt_update(updates))

        assert (
            await load_checkpoint(reader, thread_id=thread_id, checkpoint_ns=agent_ns)
            is None
        )
        loaded = await load_checkpoint(reader, thread_id=thread_id)
        assert loaded is not None
        _, pending_writes = loaded
        assert _pending_react_v2_interrupt_occurrences(pending_writes) == frozenset(
            {(interrupt.id, None)}
        )
    finally:
        await engine.dispose()
