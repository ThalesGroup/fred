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

Does NOT use fake pending-write dictionaries for any of this — every
interrupt and every resume goes through the real compiled graph and the
real checkpointer.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_runtime.react.react_message_codec import graph_input_from_react_input
from fred_runtime.react.react_model_adapter import (
    REACT_MODEL_OPERATION_ROUTING,
    infer_react_model_operation_from_messages,
)
from fred_runtime.react.react_stream_adapter import extract_interrupt_request
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.react_contract import ReActInput
from fred_sdk.contracts.runtime import ChatModelFactoryPort, ExecutionConfig
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.types import Checkpointer, Command, Interrupt
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
            chat_model_factory=cast(ChatModelFactoryPort | None, None),
            definition=cast(ReActAgentDefinition, _FakeDefinition()),
            infer_operation_from_messages=infer_react_model_operation_from_messages,
            default_operation=REACT_MODEL_OPERATION_ROUTING,
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
