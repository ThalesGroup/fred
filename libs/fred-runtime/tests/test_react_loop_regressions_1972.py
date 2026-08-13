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
- per-operation model routing (`routing` vs `planning`) with caching
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

from typing import Any, cast

import pytest
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_runtime.react.react_model_adapter import (
    REACT_MODEL_OPERATION_PLANNING,
    REACT_MODEL_OPERATION_ROUTING,
    infer_react_model_operation_from_messages,
)
from fred_runtime.react.react_stream_adapter import extract_interrupt_request
from fred_runtime.react.react_tool_loop import (
    _V2_MAX_HISTORY_CHARS,
    _V2_MAX_HISTORY_MESSAGES,
    build_tool_loop_compiled_react_agent,
)
from fred_runtime.support.tool_loop import ChatTurnTooLargeError
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import ChatModelFactoryPort
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
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
    chat_model_factory: object | None = None,
    kpi: object | None = None,
) -> Any:
    return build_tool_loop_compiled_react_agent(
        model=model,
        tools=tools if tools is not None else [update_ticket, get_info],
        system_prompt="SYS-1972.",
        binding=_binding(language),
        approval_policy=ToolApprovalPolicy(
            enabled=approval_enabled,
            always_require_tools=always_require_tools,
        ),
        checkpointer=cast(Checkpointer, InMemorySaver()),
        chat_model_factory=cast(ChatModelFactoryPort | None, chat_model_factory),
        definition=cast(ReActAgentDefinition, _FakeDefinition()),
        infer_operation_from_messages=infer_react_model_operation_from_messages,
        default_operation=REACT_MODEL_OPERATION_ROUTING,
        available_tool_names={"update_ticket", "get_info"},
        kpi=cast(Any, kpi),
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
# (d) Per-operation model routing
# ---------------------------------------------------------------------------


class _RoutingScriptedModel(RecordingModel):
    """Scripted per-operation model: tool call on a fresh turn, else final."""

    operation: str = "default"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if isinstance(messages[-1], ToolMessage):
            msg = AIMessage(content=f"final-by-{self.operation}")
        else:
            msg = AIMessage(
                content="",
                tool_calls=[_tool_call("get_info", {"topic": "fred"}, "c-route")],
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])


class _RecordingChatModelFactory:
    """Fake ChatModelFactoryPort recording per-operation build requests."""

    def __init__(self) -> None:
        self.operations: list[str] = []
        self.models: dict[str, _RoutingScriptedModel] = {}

    def build(self, definition: object, binding: object) -> BaseChatModel:
        raise AssertionError("the tool loop must use build_for_operation")

    def build_for_operation(
        self,
        *,
        definition: object,
        binding: object,
        purpose: str,
        operation: str,
    ) -> BaseChatModel:
        assert purpose == "chat"
        self.operations.append(operation)
        model = self.models.get(operation)
        if model is None:
            model = _RoutingScriptedModel(operation=operation)
            self.models[operation] = model
        return model


@pytest.mark.asyncio
async def test_model_routing_selects_and_caches_per_operation_models() -> None:
    factory = _RecordingChatModelFactory()
    default_model = RecordingModel()
    agent = _compile_agent(
        default_model, approval_enabled=False, chat_model_factory=factory
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("what about fred?")]}, "t-routing"
    )

    # Fresh user turn → `routing`; follow-up after the tool result → `planning`.
    assert factory.operations == [
        REACT_MODEL_OPERATION_ROUTING,
        REACT_MODEL_OPERATION_PLANNING,
    ]
    routing_model = factory.models[REACT_MODEL_OPERATION_ROUTING]
    planning_model = factory.models[REACT_MODEL_OPERATION_PLANNING]
    assert len(routing_model.calls) == 1
    assert len(planning_model.calls) == 1
    assert default_model.calls == []
    finals = [
        m for m in _update_messages(updates) if isinstance(m, AIMessage) and m.content
    ]
    assert [m.content for m in finals] == ["final-by-planning"]

    # Second turn on the same thread: operations are cached, the factory is
    # not asked again.
    await _drive(agent, {"messages": [HumanMessage("and again?")]}, "t-routing")
    assert factory.operations == [
        REACT_MODEL_OPERATION_ROUTING,
        REACT_MODEL_OPERATION_PLANNING,
    ]


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
