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
"""Behavioral oracle for the ReAct execution loop (#1972).

These tests capture the observable contract of the ReAct tool loop BEFORE the
migration from the hand-rolled 4-node StateGraph to LangChain `create_agent`
with the platform middleware frame (RFC AGENT-CAPABILITY-RFC.md §5.2–§5.4),
so the migration can be proven equivalent against reality rather than against
its own reimplementation:

- the HITL interrupt payload (`HumanInputRequest`, EN + FR) byte-for-byte,
  one combined interrupt per gated batch (#2177), and the `Command(resume=...)` flow
- dangling-tool-call sanitize on a poisoned checkpoint (OpenAI 400 guard)
- provider reasoning-strip on replayed history (Mistral 422 guard)
- history trim to the human boundary
- legacy tool-output attach on `response_metadata["tools"]`

They only exercise the stable seam `build_tool_loop_compiled_react_agent(...)`
plus the stream-adapter parsing used by the RuntimeEvent transcoder, so the
same file runs unchanged against the legacy graph and the `create_agent` loop.

Known-bug note (cancel): the legacy graph *intended* a cancelled approval to
skip the tool batch via a `skip_tools` state key, but LangGraph silently drops
writes to keys that are not declared on `MessagesState`, so cancelling never
actually prevented execution. `test_hitl_resume_cancel_skips_tool_batch`
asserts the documented/intended contract ("Do not run this tool; let the agent
replan") and is expected to fail on the legacy loop.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

import pytest
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_runtime.react.react_stream_adapter import extract_interrupt_request
from fred_runtime.react.react_tool_loop import (
    _V2_MAX_HISTORY_CHARS,
    _V2_MAX_HISTORY_MESSAGES,
    build_tool_loop_compiled_react_agent,
)
from fred_runtime.runtime_support.trace_payloads import serialize_model_output
from fred_runtime.support.thinking import content_to_text
from fred_runtime.support.tool_loop import ChatTurnTooLargeError
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer, Command
from pydantic import Field

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@tool
def update_ticket(ticket_id: str) -> str:
    """Update one ticket (gated via the operator `always_require_tools` list)."""

    return f"updated {ticket_id}"


@tool
def get_info(topic: str) -> str:
    """Read a piece of information (not in `always_require_tools` → no approval)."""

    return f"info about {topic}"


class RecordingModel(BaseChatModel):
    """Deterministic scripted model that records every model input verbatim."""

    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "recording-1972"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "RecordingModel":
        return self  # the script decides when to call a tool

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        msg = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


class _FakeDefinition:
    agent_id = "agent-1972"


def _binding(language: str | None = None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(language=language),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _compile_agent(
    model: BaseChatModel,
    *,
    tools: list[Any] | None = None,
    language: str | None = None,
    approval_enabled: bool = True,
    always_require_tools: tuple[str, ...] = (),
    kpi: object | None = None,
    max_tool_calls_per_turn: int | None = None,
    tool_call_text_recovery_enabled: bool = True,
) -> Any:
    selected_tools = tools if tools is not None else [update_ticket, get_info]
    return build_tool_loop_compiled_react_agent(
        model=model,
        tools=selected_tools,
        system_prompt="SYS-1972.",
        binding=_binding(language),
        approval_policy=ToolApprovalPolicy(
            enabled=approval_enabled,
            always_require_tools=always_require_tools,
        ),
        checkpointer=cast(Checkpointer, InMemorySaver()),
        definition=cast(ReActAgentDefinition, _FakeDefinition()),
        available_tool_names={tool.name for tool in selected_tools},
        kpi=cast(Any, kpi),
        max_tool_calls_per_turn=max_tool_calls_per_turn,
        tool_call_text_recovery_enabled=tool_call_text_recovery_enabled,
    )


async def _drive(agent: Any, payload: object, thread: str) -> list[object]:
    """Stream one run exactly like `_TransportBackedReActExecutor.stream`."""

    config = {"configurable": {"thread_id": thread}}
    updates: list[object] = []
    async for raw_event in agent.astream(
        payload, config=config, stream_mode=["messages", "updates"]
    ):
        mode, update = raw_event
        if mode == "updates":
            updates.append(update)
    return updates


def _raw_interrupt_values(updates: list[object]) -> list[object]:
    """Collect raw `interrupt(...)` payloads exactly as put on the wire."""

    values: list[object] = []
    for update in updates:
        if isinstance(update, dict) and "__interrupt__" in update:
            raw = update["__interrupt__"]
            first = raw[0] if isinstance(raw, (list, tuple)) else raw
            values.append(getattr(first, "value", first))
    return values


def _update_messages(updates: list[object]) -> list[BaseMessage]:
    """Collect all messages carried by node updates, in stream order."""

    messages: list[BaseMessage] = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        for value in update.values():
            if isinstance(value, dict):
                for message in value.get("messages") or []:
                    if isinstance(message, BaseMessage):
                        messages.append(message)
    return messages


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


# ---------------------------------------------------------------------------
# (a) HITL interrupt payload round-trip — byte-for-byte wire contract
# ---------------------------------------------------------------------------

# Frozen wire payloads (`HumanInputRequest.model_dump(mode="json")`), copied
# from the pre-migration loop output. Do NOT regenerate these from the payload
# builder: the point is to pin the bytes the frontend contract depends on.
_EXPECTED_PAYLOAD_EN: dict[str, Any] = {
    "stage": "tool_approval",
    "title": "Confirm tool execution",
    "question": (
        "The agent wants to execute Update Ticket. "
        "This may modify state, trigger an external action, or consume a "
        "large number of tokens. "
        "Do you want to continue?"
    ),
    "choices": [
        {
            "id": "proceed",
            "label": "Accept",
            "description": "Run this tool now.",
            "default": True,
        },
        {
            "id": "cancel",
            "label": "Reject",
            "description": "Do not run this tool; let the agent replan.",
            "default": False,
        },
    ],
    "free_text": False,
    "metadata": {},
    "checkpoint_id": None,
    "interrupt_id": None,
    "pending_calls": [
        {
            "tool_call_id": "c-1",
            "tool_name": "update_ticket",
            "args_preview": '{"ticket_id": "INC-42"}',
        }
    ],
}

_EXPECTED_PAYLOAD_FR: dict[str, Any] = {
    "stage": "tool_approval",
    "title": "Confirmer l'exécution de l'outil",
    "question": (
        "L'agent souhaite exécuter « Update Ticket ». "
        "Cette action peut modifier un état, déclencher une action externe "
        "ou consommer beaucoup de tokens. "
        "Voulez-vous continuer ?"
    ),
    "choices": [
        {
            "id": "proceed",
            "label": "Accepter",
            "description": "Exécuter cet outil maintenant.",
            "default": True,
        },
        {
            "id": "cancel",
            "label": "Refuser",
            "description": "Ne pas exécuter cet outil et laisser l'agent se replanifier.",
            "default": False,
        },
    ],
    "free_text": False,
    "metadata": {},
    "checkpoint_id": None,
    "interrupt_id": None,
    "pending_calls": [
        {
            "tool_call_id": "c-1",
            "tool_name": "update_ticket",
            "args_preview": '{"ticket_id": "INC-42"}',
        }
    ],
}


def _ticket_call_script() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[_tool_call("update_ticket", {"ticket_id": "INC-42"}, "c-1")],
        ),
        AIMessage(content="ticket updated, all done"),
    ]


@pytest.mark.asyncio
async def test_hitl_interrupt_payload_english_byte_for_byte() -> None:
    model = RecordingModel(script=_ticket_call_script())
    agent = _compile_agent(model, always_require_tools=("update_ticket",))

    updates = await _drive(
        agent, {"messages": [HumanMessage("update INC-42")]}, "t-payload-en"
    )

    values = _raw_interrupt_values(updates)
    assert values == [_EXPECTED_PAYLOAD_EN]
    # The RuntimeEvent transcoder path must still parse the same update into
    # the typed HumanInputRequest (AwaitingHumanRuntimeEvent.request).
    parsed = [
        request
        for update in updates
        if (request := extract_interrupt_request(update)) is not None
    ]
    assert len(parsed) == 1
    assert parsed[0].stage == "tool_approval"
    assert len(parsed[0].pending_calls) == 1
    assert parsed[0].pending_calls[0].tool_name == "update_ticket"
    assert parsed[0].pending_calls[0].tool_call_id == "c-1"


@pytest.mark.asyncio
async def test_hitl_interrupt_payload_french_byte_for_byte() -> None:
    model = RecordingModel(script=_ticket_call_script())
    agent = _compile_agent(
        model, language="fr-FR", always_require_tools=("update_ticket",)
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("mets à jour INC-42")]}, "t-payload-fr"
    )

    assert _raw_interrupt_values(updates) == [_EXPECTED_PAYLOAD_FR]


@pytest.mark.asyncio
async def test_hitl_resume_proceed_executes_tool_and_answers() -> None:
    model = RecordingModel(script=_ticket_call_script())
    agent = _compile_agent(model, always_require_tools=("update_ticket",))

    await _drive(agent, {"messages": [HumanMessage("update INC-42")]}, "t-proceed")
    updates = await _drive(agent, Command(resume={"choice_id": "proceed"}), "t-proceed")

    assert _raw_interrupt_values(updates) == []
    messages = _update_messages(updates)
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.content for m in tool_messages] == ["updated INC-42"]
    finals = [m for m in messages if isinstance(m, AIMessage) and m.content]
    assert [m.content for m in finals] == ["ticket updated, all done"]


@pytest.mark.asyncio
async def test_hitl_batches_multiple_gated_calls_into_one_interrupt() -> None:
    """#2177: N gated calls from the same model turn (e.g. summarizing every
    document in a folder) raise exactly ONE combined interrupt, not one
    confirmation per call — a single proceed then runs all of them."""

    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("update_ticket", {"ticket_id": "INC-1"}, "c-1"),
                    _tool_call("update_ticket", {"ticket_id": "INC-2"}, "c-2"),
                    _tool_call("update_ticket", {"ticket_id": "INC-3"}, "c-3"),
                ],
            ),
            AIMessage(content="all three updated"),
        ]
    )
    agent = _compile_agent(model, always_require_tools=("update_ticket",))

    first = await _drive(
        agent, {"messages": [HumanMessage("update INC-1, INC-2 and INC-3")]}, "t-batch"
    )
    values = _raw_interrupt_values(first)
    assert len(values) == 1  # exactly one interrupt, not three
    payload = cast(dict[str, Any], values[0])
    assert payload["title"] == "Confirm 3 tool executions"
    # Repeated calls to the SAME tool are deduplicated in the question text —
    # "Update Ticket, Update Ticket, Update Ticket" says nothing the trace's
    # own step count doesn't already say, and the raw tool name never shows.
    assert "Update Ticket (×3)" in payload["question"]
    assert "update_ticket" not in payload["question"]
    assert [c["tool_call_id"] for c in payload["pending_calls"]] == [
        "c-1",
        "c-2",
        "c-3",
    ]
    assert [c["args_preview"] for c in payload["pending_calls"]] == [
        '{"ticket_id": "INC-1"}',
        '{"ticket_id": "INC-2"}',
        '{"ticket_id": "INC-3"}',
    ]

    second = await _drive(agent, Command(resume={"choice_id": "proceed"}), "t-batch")
    assert (
        _raw_interrupt_values(second) == []
    )  # a single proceed clears the whole batch
    tool_messages = [m for m in _update_messages(second) if isinstance(m, ToolMessage)]
    assert sorted(str(m.content) for m in tool_messages) == [
        "updated INC-1",
        "updated INC-2",
        "updated INC-3",
    ]


@pytest.mark.asyncio
async def test_hitl_batch_question_dedups_repeats_but_keeps_distinct_tools() -> None:
    """A mixed batch (some tool called more than once, another called once)
    groups the repeats and keeps first-seen order, rather than either
    collapsing everything into one bucket or spelling out every repeat."""

    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("update_ticket", {"ticket_id": "INC-1"}, "c-1"),
                    _tool_call("get_info", {"topic": "fred"}, "c-2"),
                    _tool_call("update_ticket", {"ticket_id": "INC-2"}, "c-3"),
                ],
            ),
        ]
    )
    agent = _compile_agent(model, always_require_tools=("update_ticket", "get_info"))

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("update two tickets and look up fred")]},
        "t-mixed-batch",
    )

    values = _raw_interrupt_values(updates)
    assert len(values) == 1
    payload = cast(dict[str, Any], values[0])
    assert "Update Ticket (×2), Get Info" in payload["question"]


def test_build_tool_approval_request_rejects_empty_calls() -> None:
    """The caller (`aafter_model`) only ever invokes this with at least one
    gated call — pin that as an explicit, loud precondition rather than
    letting a future caller violate it silently (found in PR review)."""

    from fred_runtime.react.middleware.hitl import build_tool_approval_request

    with pytest.raises(ValueError, match="at least one"):
        build_tool_approval_request(binding=_binding(), calls=[])


@pytest.mark.asyncio
async def test_hitl_cancel_on_a_batch_skips_every_call_not_just_one() -> None:
    """The same atomic guarantee `test_hitl_resume_cancel_skips_tool_batch`
    covers for one call already held for N before batching (a cancel skipped
    the WHOLE batch even when it was asked about sequentially) — this pins it
    now that the batch is asked about once instead of N times."""

    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("update_ticket", {"ticket_id": "INC-4"}, "c-1"),
                    _tool_call("update_ticket", {"ticket_id": "INC-5"}, "c-2"),
                ],
            ),
            AIMessage(content="okay, I will not touch either ticket"),
        ]
    )
    agent = _compile_agent(model, always_require_tools=("update_ticket",))

    await _drive(
        agent, {"messages": [HumanMessage("update INC-4 and INC-5")]}, "t-batch-cancel"
    )
    updates = await _drive(
        agent, Command(resume={"choice_id": "cancel"}), "t-batch-cancel"
    )

    messages = _update_messages(updates)
    assert [m for m in messages if isinstance(m, ToolMessage)] == []
    finals = [m for m in messages if isinstance(m, AIMessage) and m.content]
    assert [m.content for m in finals] == ["okay, I will not touch either ticket"]


@pytest.mark.asyncio
async def test_hitl_tool_outside_operator_list_skips_gate() -> None:
    """
    A tool with no capability `HitlSpec` and not in the operator's
    `always_require_tools` exact list runs without an approval interrupt
    (#1978: the legacy name-prefix heuristics — e.g. a `get_`/`update_` split
    — were retired; gating is now purely capability declarations + the
    operator's exact tool list).
    """

    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("get_info", {"topic": "fred"}, "c-1")],
            ),
            AIMessage(content="here is the info"),
        ]
    )
    agent = _compile_agent(model)

    updates = await _drive(
        agent, {"messages": [HumanMessage("what about fred?")]}, "t-readonly"
    )

    assert _raw_interrupt_values(updates) == []
    tool_messages = [m for m in _update_messages(updates) if isinstance(m, ToolMessage)]
    assert [m.content for m in tool_messages] == ["info about fred"]


@pytest.mark.asyncio
async def test_hitl_operator_policy_gates_named_tool() -> None:
    """The operator's exact `always_require_tools` list gates any named tool,
    independent of naming convention (#1978)."""

    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("get_info", {"topic": "fred"}, "c-1")],
            ),
        ]
    )
    agent = _compile_agent(model, always_require_tools=("get_info",))

    updates = await _drive(
        agent, {"messages": [HumanMessage("what about fred?")]}, "t-operator"
    )

    values = _raw_interrupt_values(updates)
    assert len(values) == 1
    payload = cast(dict[str, Any], values[0])
    assert [c["tool_name"] for c in payload["pending_calls"]] == ["get_info"]


@pytest.mark.asyncio
async def test_hitl_resume_cancel_skips_tool_batch() -> None:
    """Cancel must not execute the tool; the agent replans (RFC §5.4).

    The legacy 4-node graph intended this via a `skip_tools` state key, but
    LangGraph drops writes to undeclared `MessagesState` keys, so the tool ran
    anyway (latent bug). The create_agent migration fixed it: `FredHitlMiddleware`
    jumps back to the model on cancel, and checkpoint hygiene drops the dangling
    assistant tool-call message from the replan input.
    """

    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("update_ticket", {"ticket_id": "INC-43"}, "c-1")
                ],
            ),
            AIMessage(content="okay, I will not touch the ticket"),
        ]
    )
    agent = _compile_agent(model, always_require_tools=("update_ticket",))

    await _drive(agent, {"messages": [HumanMessage("update INC-43")]}, "t-cancel")
    updates = await _drive(agent, Command(resume={"choice_id": "cancel"}), "t-cancel")

    messages = _update_messages(updates)
    assert [m for m in messages if isinstance(m, ToolMessage)] == []
    finals = [m for m in messages if isinstance(m, AIMessage) and m.content]
    assert [m.content for m in finals] == ["okay, I will not touch the ticket"]
    # The dangling assistant tool-call message is dropped from the replan
    # model input (checkpoint hygiene), so the model never sees a half-open
    # tool exchange.
    replan_input = model.calls[-1]
    assert not any(getattr(m, "tool_calls", None) for m in replan_input)


# ---------------------------------------------------------------------------
# (b) Dangling-tool-call sanitize on a poisoned checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sanitize_dangling_tool_calls_from_poisoned_history() -> None:
    model = RecordingModel(script=[AIMessage(content="recovered fine")])
    agent = _compile_agent(model, approval_enabled=False)

    poisoned: list[BaseMessage] = [
        HumanMessage("earlier question"),
        # A crashed turn stored the tool call but never the tool result.
        AIMessage(
            content="",
            tool_calls=[_tool_call("update_ticket", {"ticket_id": "LOST"}, "c-lost")],
        ),
        HumanMessage("new question after the crash"),
    ]
    await _drive(agent, {"messages": poisoned}, "t-poisoned")

    assert len(model.calls) == 1
    model_input = model.calls[0]
    # The dangling AIMessage(tool_calls) must not reach the model (OpenAI 400
    # guard) while both human messages survive.
    assert not any(getattr(m, "tool_calls", None) for m in model_input)
    human_contents = [m.content for m in model_input if isinstance(m, HumanMessage)]
    assert human_contents == ["earlier question", "new question after the crash"]


@pytest.mark.asyncio
async def test_sanitize_drops_orphaned_leading_tool_message() -> None:
    """#1999: a ToolMessage with no preceding AIMessage(tool_calls) at all
    (e.g. left fronting the window by an earlier sanitize/trim pass) must be
    dropped — passing it through crashes the next model call with
    "Unexpected role 'tool' after role '<previous>'"."""

    model = RecordingModel(script=[AIMessage(content="recovered fine")])
    agent = _compile_agent(model, approval_enabled=False)

    poisoned: list[BaseMessage] = [
        HumanMessage("earlier question"),
        ToolMessage(
            content="orphaned result", tool_call_id="c-orphan", name="get_info"
        ),
        HumanMessage("new question after the crash"),
    ]
    await _drive(agent, {"messages": poisoned}, "t-orphan-tool")

    assert len(model.calls) == 1
    model_input = model.calls[0]
    assert not any(isinstance(m, ToolMessage) for m in model_input)
    human_contents = [m.content for m in model_input if isinstance(m, HumanMessage)]
    assert human_contents == ["earlier question", "new question after the crash"]


# ---------------------------------------------------------------------------
# (c) Mistral reasoning-strip on replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reasoning_blocks_are_stripped_from_replayed_history() -> None:
    model = RecordingModel(script=[AIMessage(content="follow-up answer")])
    agent = _compile_agent(model, approval_enabled=False)

    history: list[BaseMessage] = [
        HumanMessage("first question"),
        # Replayed checkpoint content of a reasoning-capable model (Mistral /
        # Claude thinking): list content mixing a reasoning block and text.
        AIMessage(
            content=[
                {"type": "thinking", "thinking": "private chain of thought"},
                {"type": "text", "text": "visible first answer"},
            ]
        ),
        HumanMessage("second question"),
    ]
    await _drive(agent, {"messages": history}, "t-reasoning")

    assert len(model.calls) == 1
    replayed_ai = [m for m in model.calls[0] if isinstance(m, AIMessage)]
    assert len(replayed_ai) == 1
    # Mistral 422 guard: assistant history content must be a plain string with
    # the reasoning dropped and the visible text preserved.
    assert replayed_ai[0].content == "visible first answer"


# ---------------------------------------------------------------------------
# History trim to the human boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_is_trimmed_to_human_boundary() -> None:
    model = RecordingModel(script=[AIMessage(content="trimmed answer")])
    agent = _compile_agent(model, approval_enabled=False)

    # Build strictly more than the bounded window (`_V2_MAX_HISTORY_MESSAGES`) so
    # trimming actually fires, regardless of the exact configured window size.
    # Assertions are derived from the constant rather than hard-coded, so tuning
    # the window (e.g. 10 → 500 for tabular workflows) does not silently break
    # this regression: it still guards the two invariants that matter — the
    # payload is capped at the window, and it always starts on a HumanMessage so
    # it never begins mid tool-call/result pair.
    pairs = _V2_MAX_HISTORY_MESSAGES // 2 + 5  # → 2*pairs + 1 messages, > window
    history: list[BaseMessage] = []
    for i in range(1, pairs + 1):  # H1 A1 ... H_pairs A_pairs
        history.append(HumanMessage(f"question {i}"))
        history.append(AIMessage(content=f"answer {i}"))
    history.append(HumanMessage(f"question {pairs + 1}"))

    await _drive(agent, {"messages": history}, "t-trim")

    assert len(model.calls) == 1
    model_input = model.calls[0]
    non_system = [m for m in model_input if not isinstance(m, SystemMessage)]
    # Trimmed to the last `_V2_MAX_HISTORY_MESSAGES`, then advanced forward to the
    # first HumanMessage in that window.
    assert 0 < len(non_system) <= _V2_MAX_HISTORY_MESSAGES
    assert isinstance(non_system[0], HumanMessage)
    # The window is a contiguous suffix of the original history (the latest turn,
    # "question {pairs + 1}", is always preserved).
    assert [m.content for m in non_system] == [
        m.content for m in history[len(history) - len(non_system) :]
    ]
    assert non_system[-1].content == f"question {pairs + 1}"


# ---------------------------------------------------------------------------
# History trim by size budget (#2350) — a companion to the message-count trim
# above: a handful of large messages can blow the char budget while staying
# far under `_V2_MAX_HISTORY_MESSAGES`, which never engages on message count
# alone.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_is_trimmed_by_char_budget() -> None:
    model = RecordingModel(script=[AIMessage(content="trimmed answer")])
    agent = _compile_agent(model, approval_enabled=False)

    # Few messages (far under `_V2_MAX_HISTORY_MESSAGES`), but each one large
    # enough that the total blows past `_V2_MAX_HISTORY_CHARS` — the exact
    # shape of the field incident this guards against (a `write_document`
    # tool output ballooning input tokens while message count stayed ~60).
    big = "x" * (_V2_MAX_HISTORY_CHARS // 3 + 1000)
    history: list[BaseMessage] = [
        HumanMessage(f"q1 {big}"),
        AIMessage(content=f"a1 {big}"),
        HumanMessage(f"q2 {big}"),
        AIMessage(content=f"a2 {big}"),
        HumanMessage("current question"),
    ]

    await _drive(agent, {"messages": history}, "t-char-trim")

    assert len(model.calls) == 1
    model_input = model.calls[0]
    non_system = [m for m in model_input if not isinstance(m, SystemMessage)]
    total_chars = sum(len(str(m.content)) for m in non_system)
    assert total_chars <= _V2_MAX_HISTORY_CHARS
    assert isinstance(non_system[0], HumanMessage)
    # The latest turn is always preserved.
    assert non_system[-1].content == "current question"


@pytest.mark.asyncio
async def test_history_is_trimmed_by_char_budget_from_tool_call_arguments() -> None:
    """
    Regression for the exact field incident, found missing in PR review: a
    tool-calling AIMessage's own `content` is typically empty — the real
    payload (e.g. `write_document`'s `content_markdown`) lives in
    `tool_calls[*]["args"]`. A budget that only looked at `content` would
    barely register a session shaped exactly like the one that motivated
    this fix. This drives the full compiled agent, not just the pure trim
    function, so it also proves the huge argument doesn't survive as
    "current turn" content forever — a later, small turn still gets through.
    """
    # Bigger than the whole budget on its own: if the argument were correctly
    # counted, the trim MUST engage on the next turn (this is the regression
    # check — under the pre-fix code, an all-empty-`content` history like
    # this one measured as ~0 chars and the trim never engaged at all).
    huge_doc = "x" * (_V2_MAX_HISTORY_CHARS + 20_000)
    model = RecordingModel(script=[AIMessage(content="ok")])
    agent = _compile_agent(model, approval_enabled=False)

    history: list[BaseMessage] = [
        HumanMessage("write the RTM document"),
        AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "write_document",
                    {"title": "RTM", "content_markdown": huge_doc},
                    "c-doc",
                )
            ],
        ),
        ToolMessage(
            content="Document 'RTM' saved (id=abc123).",
            tool_call_id="c-doc",
            name="write_document",
        ),
        HumanMessage("now add the real requirements"),
    ]

    await _drive(agent, {"messages": history}, "t-tool-call-args")

    assert len(model.calls) == 1
    model_input = model.calls[0]
    non_system = [m for m in model_input if not isinstance(m, SystemMessage)]
    # The huge write_document call is old history by the time this new turn
    # runs — it must have been trimmed away, not silently carried forward
    # forever because it never registered as large in the first place.
    for m in non_system:
        assert huge_doc not in str(m.content)
        for tc in getattr(m, "tool_calls", None) or []:
            assert huge_doc not in str(tc.get("args", {}))
    assert non_system[-1].content == "now add the real requirements"


@pytest.mark.asyncio
async def test_current_turn_alone_over_char_budget_fails_cleanly() -> None:
    """
    When the CURRENT turn's own content already exceeds the char budget, no
    amount of trimming older history can help — the turn must fail with a
    clean, structured error instead of a raw provider context-length crash.
    """
    model = RecordingModel(script=[AIMessage(content="unreachable")])
    agent = _compile_agent(model, approval_enabled=False)

    oversized = "x" * (_V2_MAX_HISTORY_CHARS + 1)
    history: list[BaseMessage] = [HumanMessage(oversized)]

    with pytest.raises(ChatTurnTooLargeError) as exc_info:
        await _drive(agent, {"messages": history}, "t-char-too-big")

    assert exc_info.value.limit_chars == _V2_MAX_HISTORY_CHARS
    assert exc_info.value.actual_chars > _V2_MAX_HISTORY_CHARS
    # Never echo the oversized content back.
    assert oversized not in str(exc_info.value)
    assert model.calls == []


@pytest.mark.asyncio
async def test_oversized_reasoning_trace_is_budgeted_after_rehoming() -> None:
    """
    Regression (found in PR review): the char budget must run AFTER
    `thread_reasoning_within_open_turn`, not before. A `thinking` block's
    own text isn't visible to `_message_char_len` as structured reasoning
    content — only once rehomed into ordinary `content` text does its size
    become measurable. Budgeting before that rehoming would let an oversized
    reasoning trace slip through unmeasured and then expand past the limit
    on the way to the provider.
    """
    model = RecordingModel(script=[AIMessage(content="unreachable")])
    agent = _compile_agent(model, approval_enabled=False)

    huge_reasoning = "x" * (_V2_MAX_HISTORY_CHARS + 20_000)
    history: list[BaseMessage] = [
        HumanMessage("investigate the contract"),
        # Open-turn reasoning (after the last HumanMessage) — invisible to a
        # budget that only reads plain `content` strings or tool-call args.
        AIMessage(content=[{"type": "thinking", "thinking": huge_reasoning}]),
    ]

    with pytest.raises(ChatTurnTooLargeError) as exc_info:
        await _drive(agent, {"messages": history}, "t-reasoning-too-big")

    assert exc_info.value.actual_chars > _V2_MAX_HISTORY_CHARS
    assert model.calls == []


@pytest.mark.asyncio
async def test_oversized_trailing_tool_result_fails_cleanly_not_silently_empty() -> (
    None
):
    """
    Regression (found in PR review): when the latest ToolMessage alone
    exceeds the char budget (e.g. one huge RAG result), the reverse-scan
    trim keeps only that lone ToolMessage — a window with no preceding
    AIMessage(tool_calls) in it, which `_advance_to_safe_boundary` treats as
    entirely orphaned and collapses to `[]`. Measuring the now-empty result
    would silently pass the budget check and call the model with NO
    messages at all — worse than a raw crash. It must fail with
    `ChatTurnTooLargeError` instead.
    """
    model = RecordingModel(script=[AIMessage(content="unreachable")])
    agent = _compile_agent(model, approval_enabled=False)

    huge_result = "x" * (_V2_MAX_HISTORY_CHARS + 20_000)
    history: list[BaseMessage] = [
        HumanMessage("search the corpus"),
        AIMessage(
            content="",
            tool_calls=[_tool_call("search_documents", {"query": "corpus"}, "c-rag")],
        ),
        ToolMessage(content=huge_result, tool_call_id="c-rag", name="search_documents"),
    ]

    with pytest.raises(ChatTurnTooLargeError) as exc_info:
        await _drive(agent, {"messages": history}, "t-tool-result-too-big")

    assert exc_info.value.actual_chars > _V2_MAX_HISTORY_CHARS
    assert model.calls == []


class _RecordingKPIStore(BaseKPIStore):
    """
    Minimal BaseKPIStore that just remembers every emitted event (#2350).

    Mirrors `test_tool_observability_middleware.py`'s own established
    pattern for stubbing the KPI writer — duplicated locally rather than
    imported, matching that file's own stated convention.
    """

    def __init__(self) -> None:
        self.events: list[KPIEvent] = []

    def ensure_ready(self) -> None:
        return

    def index_event(self, event: KPIEvent) -> None:
        self.events.append(event)

    def bulk_index(self, events: list[KPIEvent]) -> None:
        self.events.extend(events)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        return KPIQueryResult(rows=[])


def _install_recording_kpi_writer() -> tuple[_RecordingKPIStore, KPIWriter]:
    store = _RecordingKPIStore()
    return store, KPIWriter(store=store)


@pytest.mark.asyncio
async def test_current_turn_too_large_emits_a_kpi_counter() -> None:
    """
    `agent.turn_rejected_total` is the production signal for whether
    `_V2_MAX_HISTORY_CHARS` is well-tuned (#2350) — same shape as the
    sibling `agent.tool_failed_total` counter in `ToolObservabilityMiddleware`
    (status/error_code/exception_type dims, `KPIActor(type="system")`), so it
    reaches Grafana through the same allow-listed labels without needing a
    new one.
    """
    store, kpi = _install_recording_kpi_writer()
    model = RecordingModel(script=[AIMessage(content="unreachable")])
    agent = _compile_agent(model, approval_enabled=False, kpi=kpi)

    oversized = "x" * (_V2_MAX_HISTORY_CHARS + 1)
    with pytest.raises(ChatTurnTooLargeError):
        await _drive(agent, {"messages": [HumanMessage(oversized)]}, "t-kpi")

    matches = [
        e
        for e in store.events
        if e.metric and e.metric.name == "agent.turn_rejected_total"
    ]
    assert len(matches) == 1
    dims = matches[0].dims or {}
    assert dims.get("status") == "error"
    assert dims.get("error_code") == "ChatTurnTooLargeError"
    assert dims.get("exception_type") == "ChatTurnTooLargeError"
    # Never the oversized content, on a KPI event any more than in the error
    # message itself.
    assert oversized not in str(matches[0].model_dump())


# ---------------------------------------------------------------------------
# Legacy tool-output attach on response metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latest_tool_outputs_attached_to_response_metadata() -> None:
    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("get_info", {"topic": "fred"}, "c-1")],
            ),
            AIMessage(content="done with info"),
        ]
    )
    agent = _compile_agent(model, approval_enabled=False)

    config = {"configurable": {"thread_id": "t-metadata"}}
    result = await agent.ainvoke(
        {"messages": [HumanMessage("what about fred?")]}, config=config
    )

    final = result["messages"][-1]
    assert isinstance(final, AIMessage)
    assert final.response_metadata["tools"]["get_info"] == "info about fred"


# ---------------------------------------------------------------------------
# FRED narrow Interrupt.id invariant (#2216 P1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_resume_two_sequential_prompts_get_different_interrupt_ids() -> None:
    """
    LangGraph's `Interrupt.id` is NOT universally occurrence-unique — two
    `interrupt()` calls within the SAME task share an id, matched by call
    order instead (`test_langgraph_interrupt_id_semantics.py` pins that
    upstream fact directly). #2216's fix relies on a narrower, FRED-specific
    claim instead: `FredHitlMiddleware.aafter_model` never raises more than
    one `interrupt()` per task (exactly one call site, gated by `if not
    gated: return None` — no loop), so two DISTINCT FRED HITL occurrences —
    reached via two separate resumes on the same thread — always land in
    different tasks and therefore always get different ids.

    Proven here against FRED's real, supported HITL flow
    (`build_tool_loop_compiled_react_agent`, the same production tool loop
    `_compile_agent` wraps for every other test in this file), not a toy
    graph: interrupt A (approve ticket INC-1), resume A, interrupt B
    (approve ticket INC-2) — B's id must differ from A's.
    """

    model = RecordingModel(
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
    agent = _compile_agent(model, always_require_tools=("update_ticket",))

    first = await _drive(
        agent, {"messages": [HumanMessage("update INC-1 then INC-2")]}, "t-two-ids"
    )

    def _interrupt_id(updates: list[object]) -> str:
        for update in updates:
            if isinstance(update, dict) and "__interrupt__" in update:
                raw = update["__interrupt__"]
                first_entry = raw[0] if isinstance(raw, (list, tuple)) else raw
                return getattr(first_entry, "id")
        raise AssertionError("no interrupt found in updates")

    interrupt_id_a = _interrupt_id(first)

    second = await _drive(agent, Command(resume={"choice_id": "proceed"}), "t-two-ids")
    interrupt_id_b = _interrupt_id(second)

    assert interrupt_id_a != interrupt_id_b


# ---------------------------------------------------------------------------
# Mistral tool-call-as-text controlled replay
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ToolCallTextIncident:
    """Redacted evidence plus a reconstructed completed model message."""

    name: str
    session_id: str
    history_rank: int
    trace_id: str
    observation_id: str
    reconstructed_content: list[dict[str, object]]
    observed_history_projection: str
    observed_trace_thinking_blocks: int
    observed_trace_after_thinking: str
    native_calls: tuple[dict[str, Any], ...]


_REPLAY_SESSION_ID = "70c54206-d3e7-481b-9d08-7a9e68d712d0"
_RECONSTRUCTED_REFERENCE_BLOCK: dict[str, object] = {
    "type": "reference",
    "reference_ids": [],
}


def _redacted_thinking_blocks(count: int) -> list[dict[str, object]]:
    """Represent trace placeholders without claiming to recover private text."""

    return [{"type": "thinking", "thinking": "<redacted>"} for _ in range(count)]


_TOOL_CALL_TEXT_INCIDENTS = (
    _ToolCallTextIncident(
        name="query_then_catalog",
        session_id=_REPLAY_SESSION_ID,
        history_rank=5,
        trace_id="485242a3a6272c245fc7ec7ba346e1a3",
        observation_id="73d1e5558f82c3b6",
        reconstructed_content=[
            *_redacted_thinking_blocks(37),
            {"type": "text", "text": "read"},
            {"type": "text", "text": "_query"},
            _RECONSTRUCTED_REFERENCE_BLOCK,
            {
                "type": "text",
                "text": (
                    '{"sql": "SELECT * FROM <redacted_table> LIMIT 5", '
                    '"dataset_uids": ["<redacted_dataset>"]} '
                    "list_tabular_documents{}"
                ),
            },
        ],
        observed_history_projection=(
            "read\n_query\n{'type': 'reference', 'reference_ids': []}\n"
            '{"sql": "SELECT * FROM <redacted_table> LIMIT 5", '
            '"dataset_uids": ["<redacted_dataset>"]} list_tabular_documents{}'
        ),
        observed_trace_thinking_blocks=37,
        observed_trace_after_thinking=(
            'read_query[reference]{"sql": "SELECT * FROM <redacted_table> LIMIT 5", '
            '"dataset_uids": ["<redacted_dataset>"]} list_tabular_documents{}'
        ),
        native_calls=(
            {
                "name": "read_query",
                "args": {
                    "sql": "SELECT * FROM fake_table LIMIT 5",
                    "dataset_uids": ["fake-dataset"],
                },
            },
            {"name": "list_tabular_documents", "args": {}},
        ),
    ),
    _ToolCallTextIncident(
        name="two_delegated_tasks",
        session_id=_REPLAY_SESSION_ID,
        history_rank=16,
        trace_id="970ee98fef7b8f7d68de1fa3be653299",
        observation_id="38a70a22fceabdf4",
        reconstructed_content=[
            *_redacted_thinking_blocks(123),
            {"type": "text", "text": "Plan de découpage en cinq lots.\n\ntask"},
            _RECONSTRUCTED_REFERENCE_BLOCK,
            {
                "type": "text",
                "text": (
                    '{"description": "<redacted instructions for rows 1-100>", '
                    '"subagent_type": "general-purpose"}'
                    'task{"description": "<redacted instructions for rows 101-200>", '
                    '"subagent_type": "general-purpose"}'
                ),
            },
        ],
        observed_history_projection=(
            "Plan de découpage en cinq lots.\n\ntask\n"
            "{'type': 'reference', 'reference_ids': []}\n"
            '{"description": "<redacted instructions for rows 1-100>", '
            '"subagent_type": "general-purpose"}'
            'task{"description": "<redacted instructions for rows 101-200>", '
            '"subagent_type": "general-purpose"}'
        ),
        observed_trace_thinking_blocks=123,
        observed_trace_after_thinking=(
            'Plan de découpage en cinq lots.\n\ntask[reference]{"description": '
            '"<redacted instructions for rows 1-100>", "subagent_type": '
            '"general-purpose"}task{"description": "<redacted instructions for rows '
            '101-200>", "subagent_type": "general-purpose"}'
        ),
        native_calls=(
            {
                "name": "task",
                "args": {
                    "description": "fake instructions for rows 1-100",
                    "subagent_type": "general-purpose",
                },
            },
            {
                "name": "task",
                "args": {
                    "description": "fake instructions for rows 101-200",
                    "subagent_type": "general-purpose",
                },
            },
        ),
    ),
    _ToolCallTextIncident(
        name="list_then_update_todos",
        session_id=_REPLAY_SESSION_ID,
        history_rank=33,
        trace_id="a86c40a4722e466fd0250b80f6b86a03",
        observation_id="0ca508639fb2e1ed",
        reconstructed_content=[
            *_redacted_thinking_blocks(19),
            {"type": "text", "text": "ls"},
            _RECONSTRUCTED_REFERENCE_BLOCK,
            {
                "type": "text",
                "text": (
                    '{"path": "/"}'
                    'write_todos{"todos": ['
                    '{"content": "lot 1", "status": "completed"}, '
                    '{"content": "lot 5", "status": "in_progress"}]}'
                ),
            },
        ],
        observed_history_projection=(
            "ls\n{'type': 'reference', 'reference_ids': []}\n"
            '{"path": "/"}write_todos{"todos": ['
            '{"content": "lot 1", "status": "completed"}, '
            '{"content": "lot 5", "status": "in_progress"}]}'
        ),
        observed_trace_thinking_blocks=19,
        observed_trace_after_thinking=(
            'ls[reference]{"path": "/"}write_todos{"todos": ['
            '{"content": "lot 1", "status": "completed"}, '
            '{"content": "lot 5", "status": "in_progress"}]}'
        ),
        native_calls=(
            {"name": "ls", "args": {"path": "/"}},
            {
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "lot 1", "status": "completed"},
                        {"content": "lot 5", "status": "in_progress"},
                    ]
                },
            },
        ),
    ),
)


def _replay_tools(recorder: list[dict[str, Any]]) -> list[StructuredTool]:
    """Build no-I/O fakes for every tool named by the three incidents."""

    def read_query(sql: str, dataset_uids: list[str]) -> str:
        """Return fake query rows."""

        recorder.append(
            {"name": "read_query", "args": {"sql": sql, "dataset_uids": dataset_uids}}
        )
        return "five fake rows"

    def list_tabular_documents() -> str:
        """Return a fake tabular catalogue."""

        recorder.append({"name": "list_tabular_documents", "args": {}})
        return "one fake document"

    def task(description: str, subagent_type: str) -> str:
        """Record a fake delegated task without starting another agent."""

        recorder.append(
            {
                "name": "task",
                "args": {
                    "description": description,
                    "subagent_type": subagent_type,
                },
            }
        )
        return "fake task completed"

    def ls(path: str) -> str:
        """Return a fake directory listing."""

        recorder.append({"name": "ls", "args": {"path": path}})
        return "fake-file.md"

    def write_todos(todos: list[dict[str, str]]) -> str:
        """Record fake todo updates."""

        recorder.append({"name": "write_todos", "args": {"todos": todos}})
        return "fake todos updated"

    return [
        StructuredTool.from_function(read_query),
        StructuredTool.from_function(list_tabular_documents),
        StructuredTool.from_function(task),
        StructuredTool.from_function(ls),
        StructuredTool.from_function(write_todos),
    ]


def _sorted_invocations(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make concurrently dispatched native calls deterministic for assertions."""

    return sorted(values, key=lambda value: (str(value["name"]), repr(value["args"])))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "incident", _TOOL_CALL_TEXT_INCIDENTS, ids=lambda incident: incident.name
)
async def test_mistral_call_like_content_terminates_without_tool_invocation(
    incident: _ToolCallTextIncident,
) -> None:
    """Replay the current failure at the completed model-message boundary."""

    invocations: list[dict[str, Any]] = []
    response = AIMessage(
        content=incident.reconstructed_content,
        response_metadata={"model_name": "mistral-medium-latest"},
    )
    model = RecordingModel(script=[response])
    agent = _compile_agent(
        model,
        tools=_replay_tools(invocations),
        approval_enabled=False,
        tool_call_text_recovery_enabled=False,
    )

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("continue the analysis")]},
        f"mistral-incident-{incident.history_rank}",
    )

    assert response.tool_calls == []
    assert invocations == []
    messages = _update_messages(updates)
    assert not any(isinstance(message, ToolMessage) for message in messages)
    finals = [message for message in messages if isinstance(message, AIMessage)]
    assert len(finals) == 1
    assert finals[0].content == incident.reconstructed_content

    assert content_to_text(response.content) == incident.observed_history_projection
    assert serialize_model_output([response]) == (
        "[thinking]" * incident.observed_trace_thinking_blocks
        + incident.observed_trace_after_thinking
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "incident", _TOOL_CALL_TEXT_INCIDENTS, ids=lambda incident: incident.name
)
async def test_mistral_completed_call_text_executes_each_recovered_call_once(
    incident: _ToolCallTextIncident,
) -> None:
    invocations: list[dict[str, Any]] = []
    store, kpi = _install_recording_kpi_writer()
    model = RecordingModel(
        script=[
            AIMessage(
                content=incident.reconstructed_content,
                response_metadata={"model_name": "mistral-medium-latest"},
            ),
            AIMessage(content="recovered calls completed"),
        ]
    )
    agent = _compile_agent(
        model,
        tools=_replay_tools(invocations),
        approval_enabled=False,
        kpi=kpi,
    )

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("continue the analysis")]},
        f"mistral-recovered-{incident.history_rank}",
    )

    assert Counter(call["name"] for call in invocations) == Counter(
        call["name"] for call in incident.native_calls
    )
    messages = _update_messages(updates)
    proposed_ids = [
        call["id"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    result_ids = [
        message.tool_call_id for message in messages if isinstance(message, ToolMessage)
    ]
    assert Counter(result_ids) == Counter(proposed_ids)
    assert len(result_ids) == len(incident.native_calls)
    assert len(
        [
            event
            for event in store.events
            if event.metric and event.metric.name == "agent.tool_latency_ms"
        ]
    ) == len(incident.native_calls)


@pytest.mark.asyncio
async def test_recovered_calls_reach_compiled_hitl_before_execution() -> None:
    incident = _TOOL_CALL_TEXT_INCIDENTS[1]
    invocations: list[dict[str, Any]] = []
    model = RecordingModel(
        script=[
            AIMessage(
                content=incident.reconstructed_content,
                response_metadata={"model_name": "mistral-medium-latest"},
            )
        ]
    )
    agent = _compile_agent(
        model,
        tools=_replay_tools(invocations),
        always_require_tools=("task",),
    )

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("continue the analysis")]},
        "mistral-recovered-hitl",
    )

    values = _raw_interrupt_values(updates)
    assert len(values) == 1
    payload = cast(dict[str, Any], values[0])
    assert [call["tool_name"] for call in payload["pending_calls"]] == [
        "task",
        "task",
    ]
    assert invocations == []
    assert not any(
        isinstance(message, ToolMessage) for message in _update_messages(updates)
    )


@pytest.mark.asyncio
async def test_recovered_calls_reach_compiled_budget_and_pairing() -> None:
    incident = _TOOL_CALL_TEXT_INCIDENTS[2]
    invocations: list[dict[str, Any]] = []
    model = RecordingModel(
        script=[
            AIMessage(
                content=incident.reconstructed_content,
                response_metadata={"model_name": "mistral-medium-latest"},
            ),
            AIMessage(content="budget applied"),
        ]
    )
    agent = _compile_agent(
        model,
        tools=_replay_tools(invocations),
        approval_enabled=False,
        max_tool_calls_per_turn=1,
    )

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("continue the analysis")]},
        "mistral-recovered-budget",
    )

    messages = _update_messages(updates)
    proposed_ids = [
        call["id"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    result_ids = [
        message.tool_call_id for message in messages if isinstance(message, ToolMessage)
    ]
    assert Counter(result_ids) == Counter(proposed_ids)
    assert len(invocations) <= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "incident", _TOOL_CALL_TEXT_INCIDENTS, ids=lambda incident: incident.name
)
async def test_native_controls_execute_each_observed_fake_tool_call_once(
    incident: _ToolCallTextIncident,
) -> None:
    """Show that native calls take the tool route in the same compiled loop."""

    invocations: list[dict[str, Any]] = []
    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        str(call["name"]),
                        cast(dict[str, Any], call["args"]),
                        f"native-{index}",
                    )
                    for index, call in enumerate(incident.native_calls, start=1)
                ],
            ),
            AIMessage(content="native calls completed"),
        ]
    )
    agent = _compile_agent(
        model,
        tools=_replay_tools(invocations),
        approval_enabled=False,
    )

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("continue the analysis")]},
        f"mistral-native-control-{incident.history_rank}",
    )

    assert _sorted_invocations(invocations) == _sorted_invocations(
        [dict(call) for call in incident.native_calls]
    )
    tool_messages = [
        message
        for message in _update_messages(updates)
        if isinstance(message, ToolMessage)
    ]
    assert len(tool_messages) == len(incident.native_calls)
