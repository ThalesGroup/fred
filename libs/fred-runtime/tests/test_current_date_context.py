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

"""Date context at supported Graph model boundaries."""

from typing import Any

import pytest
from fred_runtime.graph.node_context import NodeContext
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field


class _Route(BaseModel):
    route: str


class _RecordingModel(FakeListChatModel):
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    async def astream(self, input: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        self.calls.append(list(input))
        yield AIMessageChunk(content="done")

    def with_structured_output(  # type: ignore[override]
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[Any, Any]:
        def answer(messages: list[BaseMessage]) -> dict[str, Any]:
            self.calls.append(list(messages))
            return {
                "raw": AIMessage(content="{}"),
                "parsed": _Route(route="done"),
                "parsing_error": None,
            }

        async def async_answer(messages: list[BaseMessage]) -> dict[str, Any]:
            return answer(messages)

        return RunnableLambda(answer, afunc=async_answer)


def _context(model: _RecordingModel) -> NodeContext:
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s", user_id="u", team_id="t"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
            team_id="t",
        ),
    )
    return NodeContext(
        binding=binding,
        services=RuntimeServices(),
        model=model,
        graph_agent_id="graph-agent",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools={},
        tuning_values={},
        sink=lambda _event: None,
    )


@pytest.mark.asyncio
async def test_graph_stream_and_structured_calls_receive_date_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = iter(("2026-11-25", "2026-11-26"))
    monkeypatch.setattr(
        "fred_runtime.graph.node_context.current_date_instruction",
        lambda: f"The current UTC date is {next(dates)}.",
    )
    model = _RecordingModel(responses=["done"])
    context = _context(model)
    original = [
        SystemMessage(content="Authored {today}"),
        SystemMessage(content="Today is 2022-01-01."),
        HumanMessage(content="date?"),
    ]

    await context.invoke_model(original)
    plain: list[BaseMessage] = [HumanMessage(content="route?")]
    assert await context.invoke_structured_model(_Route, plain) == _Route(route="done")

    assert original[0].content == "Authored {today}"
    assert original[1].content == "Today is 2022-01-01."
    assert len(plain) == 1
    assert model.calls[0][0].content == "Authored {today}"
    assert (
        model.calls[0][1].content
        == "Today is 2022-01-01.\n\nThe current UTC date is 2026-11-25."
    )
    assert model.calls[1][0].content == "The current UTC date is 2026-11-26."
    assert isinstance(model.calls[1][0], SystemMessage)
