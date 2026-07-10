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
  sequential per-call interrupts, and the `Command(resume=...)` flow
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

from fred_runtime.react.react_model_adapter import (
    REACT_MODEL_OPERATION_PLANNING,
    REACT_MODEL_OPERATION_ROUTING,
    infer_react_model_operation_from_messages,
)
from fred_runtime.react.react_stream_adapter import extract_interrupt_request
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@tool
def update_ticket(ticket_id: str) -> str:
    """Update one ticket (mutating prefix → requires approval)."""

    return f"updated {ticket_id}"


@tool
def get_info(topic: str) -> str:
    """Read a piece of information (read-only prefix → no approval)."""

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
        chat_model_factory=cast("ChatModelFactoryPort | None", chat_model_factory),
        definition=cast(ReActAgentDefinition, _FakeDefinition()),
        infer_operation_from_messages=infer_react_model_operation_from_messages,
        default_operation=REACT_MODEL_OPERATION_ROUTING,
        available_tool_names={"update_ticket", "get_info"},
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
        "The agent wants to execute `update_ticket`. "
        "This may modify state or trigger an external action. "
        "Do you want to continue?"
    ),
    "choices": [
        {
            "id": "proceed",
            "label": "Proceed",
            "description": "Run this tool now.",
            "default": True,
        },
        {
            "id": "cancel",
            "label": "Cancel",
            "description": "Do not run this tool; let the agent replan.",
            "default": False,
        },
    ],
    "free_text": True,
    "metadata": {
        "tool_name": "update_ticket",
        "tool_args_preview": '{"ticket_id": "INC-42"}',
    },
    "checkpoint_id": None,
}

_EXPECTED_PAYLOAD_FR: dict[str, Any] = {
    "stage": "tool_approval",
    "title": "Confirmer l'exécution de l'outil",
    "question": (
        "L'agent souhaite exécuter `update_ticket`. "
        "Cette action peut modifier un état ou déclencher une action externe. "
        "Veux-tu continuer ?"
    ),
    "choices": [
        {
            "id": "proceed",
            "label": "Continuer",
            "description": "Exécuter cet outil maintenant.",
            "default": True,
        },
        {
            "id": "cancel",
            "label": "Annuler",
            "description": "Ne pas exécuter cet outil et laisser l'agent se replanifier.",
            "default": False,
        },
    ],
    "free_text": True,
    "metadata": {
        "tool_name": "update_ticket",
        "tool_args_preview": '{"ticket_id": "INC-42"}',
    },
    "checkpoint_id": None,
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
    agent = _compile_agent(model)

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
    assert parsed[0].metadata["tool_name"] == "update_ticket"


@pytest.mark.asyncio
async def test_hitl_interrupt_payload_french_byte_for_byte() -> None:
    model = RecordingModel(script=_ticket_call_script())
    agent = _compile_agent(model, language="fr-FR")

    updates = await _drive(
        agent, {"messages": [HumanMessage("mets à jour INC-42")]}, "t-payload-fr"
    )

    assert _raw_interrupt_values(updates) == [_EXPECTED_PAYLOAD_FR]


@pytest.mark.asyncio
async def test_hitl_resume_proceed_executes_tool_and_answers() -> None:
    model = RecordingModel(script=_ticket_call_script())
    agent = _compile_agent(model)

    await _drive(agent, {"messages": [HumanMessage("update INC-42")]}, "t-proceed")
    updates = await _drive(
        agent, Command(resume={"choice_id": "proceed"}), "t-proceed"
    )

    assert _raw_interrupt_values(updates) == []
    messages = _update_messages(updates)
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.content for m in tool_messages] == ["updated INC-42"]
    finals = [m for m in messages if isinstance(m, AIMessage) and m.content]
    assert [m.content for m in finals] == ["ticket updated, all done"]


@pytest.mark.asyncio
async def test_hitl_sequential_interrupts_one_per_gated_call() -> None:
    model = RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("update_ticket", {"ticket_id": "INC-1"}, "c-1"),
                    _tool_call("update_ticket", {"ticket_id": "INC-2"}, "c-2"),
                ],
            ),
            AIMessage(content="both updated"),
        ]
    )
    agent = _compile_agent(model)

    first = await _drive(
        agent, {"messages": [HumanMessage("update INC-1 and INC-2")]}, "t-seq"
    )
    first_values = _raw_interrupt_values(first)
    assert len(first_values) == 1
    first_payload = cast(dict[str, Any], first_values[0])
    assert first_payload["metadata"]["tool_args_preview"] == '{"ticket_id": "INC-1"}'

    second = await _drive(agent, Command(resume={"choice_id": "proceed"}), "t-seq")
    second_values = _raw_interrupt_values(second)
    assert len(second_values) == 1
    second_payload = cast(dict[str, Any], second_values[0])
    assert second_payload["metadata"]["tool_args_preview"] == '{"ticket_id": "INC-2"}'

    third = await _drive(agent, Command(resume={"choice_id": "proceed"}), "t-seq")
    assert _raw_interrupt_values(third) == []
    tool_messages = [
        m for m in _update_messages(third) if isinstance(m, ToolMessage)
    ]
    assert sorted(str(m.content) for m in tool_messages) == [
        "updated INC-1",
        "updated INC-2",
    ]


@pytest.mark.asyncio
async def test_hitl_read_only_prefix_skips_gate() -> None:
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
    tool_messages = [
        m for m in _update_messages(updates) if isinstance(m, ToolMessage)
    ]
    assert [m.content for m in tool_messages] == ["info about fred"]


@pytest.mark.asyncio
async def test_hitl_operator_policy_overrides_read_only_prefix() -> None:
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
    assert payload["metadata"]["tool_name"] == "get_info"


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Latent legacy bug (#1972): LangGraph drops the gate's `skip_tools` "
        "write (undeclared MessagesState key), so a cancelled approval still "
        "executes the tool. The create_agent migration fixes this; the marker "
        "is removed in the migration commit."
    ),
)
async def test_hitl_resume_cancel_skips_tool_batch() -> None:
    """Cancel must not execute the tool; the agent replans (RFC §5.4).

    The legacy 4-node graph intended this via a `skip_tools` state key, but
    LangGraph drops writes to undeclared `MessagesState` keys, so the tool ran
    anyway. This asserts the documented contract, fixed by the migration.
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
    agent = _compile_agent(model)

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

    history: list[BaseMessage] = []
    for i in range(1, 7):  # H1 A1 ... H6 A6
        history.append(HumanMessage(f"question {i}"))
        history.append(AIMessage(content=f"answer {i}"))
    history.append(HumanMessage("question 7"))  # 13 messages total

    await _drive(agent, {"messages": history}, "t-trim")

    assert len(model.calls) == 1
    model_input = model.calls[0]
    non_system = [m for m in model_input if not isinstance(m, SystemMessage)]
    # 13 messages → last 10 → advanced to the first HumanMessage → H3..H7.
    assert [m.content for m in non_system] == [
        "question 3",
        "answer 3",
        "question 4",
        "answer 4",
        "question 5",
        "answer 5",
        "question 6",
        "answer 6",
        "question 7",
    ]


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
        m
        for m in _update_messages(updates)
        if isinstance(m, AIMessage) and m.content
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
