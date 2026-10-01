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

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from deepagents.backends import StateBackend
from fred_runtime.deep.deep_runtime import (
    _build_deepagent_runtime_middleware,
    _create_compiled_deep_agent,
)
from fred_runtime.react.react_tool_binding import ReActToolBinder
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_runtime.react.react_tool_resolution import ReActRuntimeToolResolver
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer, Command, Interrupt
from pydantic import Field


class _Model(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "question-test"

    def bind_tools(self, tools: Any, **kwargs: Any) -> _Model:
        return self

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


class _Definition:
    agent_id = "question-test"


def _compile(kind: str, model: _Model, language: str | None = None) -> Any:
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(ask_user=True, language=language),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )
    specs = ReActRuntimeToolResolver(
        declared_tool_refs=(),
        toolset_key=None,
        services=RuntimeServices(),
        binding=binding,
    ).resolve_tools()
    tools = [
        item.tool
        for item in ReActToolBinder(
            runtime_tools=specs, tracer=None, binding=binding
        ).build_tools()
    ]
    policy = ToolApprovalPolicy(enabled=False)
    saver = cast(Checkpointer, InMemorySaver())
    if kind == "react":
        return build_tool_loop_compiled_react_agent(
            model=model,
            tools=tools,
            system_prompt="Ask the user.",
            binding=binding,
            approval_policy=policy,
            checkpointer=saver,
            definition=cast(ReActAgentDefinition, _Definition()),
            available_tool_names={"ask_user"},
        )
    middleware = _build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=binding,
        approval_policy=policy,
        available_tool_names={"ask_user"},
    )
    child = _build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=binding,
        approval_policy=policy,
        available_tool_names={"ask_user"},
        child=True,
    )
    return _create_compiled_deep_agent(
        model=model,
        tools=tools,
        subagent_tools=[],
        system_prompt="Ask the user.",
        checkpointer=saver,
        middleware=middleware,
        subagent_middleware=child,
        backend=StateBackend(),
        permissions=[],
    )


async def _drive(agent: Any, payload: object, thread: str) -> list[Interrupt]:
    pending: list[Interrupt] = []
    async for mode, update in agent.astream(
        payload,
        config={"configurable": {"thread_id": thread}},
        stream_mode=["messages", "updates"],
    ):
        if mode == "updates" and isinstance(update, dict) and "__interrupt__" in update:
            value = update["__interrupt__"]
            pending.extend(value if isinstance(value, (list, tuple)) else (value,))
    return pending


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["react", "deep"])
@pytest.mark.parametrize(
    "answer, expected, language",
    [
        ({"choice_id": "yes"}, {"status": "answered", "choice_id": "yes"}, None),
        ({"text": "Maybe later"}, {"status": "answered", "text": "Maybe later"}, None),
        (
            {"choice_id": "yes", "text": "Please"},
            {"status": "answered", "choice_id": "yes", "text": "Please"},
            None,
        ),
        (
            {"skipped": True},
            {
                "status": "skipped",
                "instruction": "The user chose not to answer this question. Continue this turn using your own assumptions and state them in your response, without asking the same question again.",
            },
            "en-US",
        ),
        (
            {"skipped": True},
            {
                "status": "skipped",
                "instruction": "L'utilisateur n'a pas souhaité répondre à cette question. Continue ce tour avec tes propres hypothèses et explicite-les dans ta réponse, sans reposer la même question.",
            },
            "fr-FR",
        ),
    ],
)
async def test_question_resumes_its_tool_call(
    kind: str, answer: dict[str, object], expected: dict[str, str], language: str | None
) -> None:
    model = _Model(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {
                            "question": "Proceed?",
                            "choices": [{"id": "yes", "label": "Yes"}],
                            "allow_free_text": True,
                        },
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="continued"),
        ]
    )
    agent = _compile(kind, model, language)
    thread = f"{kind}-{answer}-{language}"
    pending = await _drive(agent, {"messages": [HumanMessage("Ask me")]}, thread)
    assert len(pending) == 1
    assert pending[0].value["stage"] == "agent_question"
    assert pending[0].value["occurrence_id"] == "call-1"
    assert await _drive(agent, Command(resume={pending[0].id: answer}), thread) == []
    results = [
        message
        for call in model.calls
        for message in call
        if isinstance(message, ToolMessage)
    ]
    assert any(
        message.tool_call_id == "call-1"
        and json.loads(str(message.content)) == expected
        for message in results
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["react", "deep"])
async def test_multiple_choices_allow_text_even_when_agent_disables_it(
    kind: str,
) -> None:
    model = _Model(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {
                            "question": "Which destination?",
                            "choices": [
                                {"id": "city", "label": "City"},
                                {"id": "beach", "label": "Beach"},
                            ],
                            "allow_free_text": False,
                        },
                        "id": "call-other",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="continued"),
        ]
    )
    agent = _compile(kind, model)
    thread = f"other-answer-{kind}"
    pending = await _drive(agent, {"messages": [HumanMessage("Ask me")]}, thread)

    assert len(pending) == 1
    assert pending[0].value["free_text"] is True
    assert (
        await _drive(
            agent, Command(resume={pending[0].id: {"text": "Mountains"}}), thread
        )
        == []
    )
    assert any(
        message.tool_call_id == "call-other"
        and json.loads(str(message.content))
        == {"status": "answered", "text": "Mountains"}
        for call in model.calls
        for message in call
        if isinstance(message, ToolMessage)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["react", "deep"])
async def test_marked_mistral_question_pauses_after_an_answer(kind: str) -> None:
    model = _Model(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {"question": "Destination?", "allow_free_text": True},
                        "id": "first-question",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content=[
                    {"type": "text", "text": "ask_user"},
                    {"type": "reference", "reference_ids": []},
                    {
                        "type": "text",
                        "text": '{"question":"\nWhich island?","allow_free_text":true}',
                    },
                ],
                response_metadata={"model_name": "mistral-medium-latest"},
            ),
            AIMessage(content="continued"),
        ]
    )
    agent = _compile(kind, model)
    thread = f"marked-followup-{kind}"

    first = await _drive(agent, {"messages": [HumanMessage("Plan a trip")]}, thread)
    assert len(first) == 1
    second = await _drive(
        agent,
        Command(resume={first[0].id: {"text": "Canaries"}}),
        thread,
    )

    assert len(second) == 1
    assert second[0].value["question"] == "\nWhich island?"
    assert second[0].value["occurrence_id"].startswith("recovered-")
    assert (
        await _drive(
            agent,
            Command(resume={second[0].id: {"text": "Tenerife"}}),
            thread,
        )
        == []
    )
    assert any(
        message.tool_call_id == second[0].value["occurrence_id"]
        and json.loads(str(message.content))
        == {"status": "answered", "text": "Tenerife"}
        for call in model.calls
        for message in call
        if isinstance(message, ToolMessage)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["react", "deep"])
async def test_sibling_questions_keep_distinct_tool_call_ids(kind: str) -> None:
    model = _Model(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {"question": "First?", "allow_free_text": True},
                        "id": "call-1",
                        "type": "tool_call",
                    },
                    {
                        "name": "ask_user",
                        "args": {"question": "Second?", "allow_free_text": True},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="continued"),
        ]
    )
    agent = _compile(kind, model)
    thread = f"siblings-{kind}"
    first = await _drive(agent, {"messages": [HumanMessage("Ask twice")]}, thread)
    assert {item.value["occurrence_id"] for item in first} == {"call-1", "call-2"}
    by_call = {item.value["occurrence_id"]: item for item in first}
    second = await _drive(
        agent, Command(resume={by_call["call-1"].id: {"text": "one"}}), thread
    )
    assert [item.value["occurrence_id"] for item in second] == ["call-2"]
    assert (
        await _drive(
            agent, Command(resume={by_call["call-2"].id: {"text": "two"}}), thread
        )
        == []
    )
    results = {
        message.tool_call_id: json.loads(str(message.content))
        for call in model.calls
        for message in call
        if isinstance(message, ToolMessage)
        and message.tool_call_id in {"call-1", "call-2"}
    }
    assert results == {
        "call-1": {"status": "answered", "text": "one"},
        "call-2": {"status": "answered", "text": "two"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["react", "deep"])
async def test_sibling_questions_resume_together_in_one_graph_invocation(
    kind: str,
) -> None:
    model = _Model(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {"question": "First?", "allow_free_text": True},
                        "id": "call-1",
                        "type": "tool_call",
                    },
                    {
                        "name": "ask_user",
                        "args": {"question": "Second?", "allow_free_text": True},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="continued"),
        ]
    )
    agent = _compile(kind, model)
    thread = f"batch-siblings-{kind}"
    pending = await _drive(agent, {"messages": [HumanMessage("Ask twice")]}, thread)
    by_call = {item.value["occurrence_id"]: item for item in pending}
    assert (
        await _drive(
            agent,
            Command(
                resume={
                    by_call["call-1"].id: {"text": "one"},
                    by_call["call-2"].id: {"text": "two"},
                }
            ),
            thread,
        )
        == []
    )
    results = {
        message.tool_call_id: json.loads(str(message.content))
        for call in model.calls
        for message in call
        if isinstance(message, ToolMessage)
        and message.tool_call_id in {"call-1", "call-2"}
    }
    assert results == {
        "call-1": {"status": "answered", "text": "one"},
        "call-2": {"status": "answered", "text": "two"},
    }
