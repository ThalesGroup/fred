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

"""Verify `fred_sdk.testing.FakeGraphNodeContext` against the real authoring API.

These tests deliberately drive the fake through `structured_model_step` and
`invoke_agent` themselves rather than asserting on the fake in isolation —
the point of shipping this double is that it stays wire-compatible with the
real authoring surface as that surface evolves.
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest
from fred_sdk import AgentInvocationResult, GraphNodeContext
from fred_sdk.graph.authoring.api import structured_model_step
from fred_sdk.testing import FakeGraphNodeContext
from pydantic import BaseModel


class _Decision(BaseModel):
    route: str


def test_structured_model_step_replays_configured_result() -> None:
    context = FakeGraphNodeContext(
        structured_results={"route": "specialist"},
    )

    result = asyncio.run(
        structured_model_step(
            cast(GraphNodeContext, context),
            output_model=_Decision,
            user_prompt="Where should this go?",
        )
    )

    assert result == _Decision(route="specialist")
    assert context.structured_model_calls == 1


def test_structured_model_step_unconfigured_result_fails_loudly() -> None:
    context = FakeGraphNodeContext()

    with pytest.raises(AssertionError):
        asyncio.run(
            structured_model_step(
                cast(GraphNodeContext, context),
                output_model=_Decision,
                user_prompt="Where should this go?",
            )
        )


def test_structured_model_step_still_honours_no_model_fallback() -> None:
    # `model=None` exercises structured_model_step's own pre-existing
    # no-bound-model path — the fake never intercepts this, it only fakes
    # `invoke_structured_model`, which that path never calls.
    context = FakeGraphNodeContext(model=None)

    result = asyncio.run(
        structured_model_step(
            cast(GraphNodeContext, context),
            output_model=_Decision,
            user_prompt="Where should this go?",
            fallback_output={"route": "specialist"},
        )
    )

    assert result == _Decision(route="specialist")
    assert context.structured_model_calls == 0


def test_invoke_agent_records_call_and_replays_result() -> None:
    context = FakeGraphNodeContext(
        agent_result=AgentInvocationResult(
            agent_id="tessa", content="", structured={"trust": "high"}
        ),
    )

    result = asyncio.run(
        cast(GraphNodeContext, context).invoke_agent(
            "tessa", "Check the CMDB for this component."
        )
    )

    assert result.structured == {"trust": "high"}
    assert context.agent_calls == [
        {
            "agent_id": "tessa",
            "message": "Check the CMDB for this component.",
            "output_schema": None,
            "scope": None,
            "prior_turns": (),
            "system_prompt": None,
        }
    ]


def test_invoke_agent_can_be_scripted_per_agent_id() -> None:
    context = FakeGraphNodeContext(
        agent_result={
            "tessa": AgentInvocationResult(agent_id="tessa", structured={"a": 1}),
            "rico": AgentInvocationResult(agent_id="rico", structured={"b": 2}),
        },
    )

    tessa_result = asyncio.run(
        cast(GraphNodeContext, context).invoke_agent("tessa", "hello")
    )
    rico_result = asyncio.run(
        cast(GraphNodeContext, context).invoke_agent("rico", "hello")
    )

    assert tessa_result.structured == {"a": 1}
    assert rico_result.structured == {"b": 2}


def test_invoke_agent_unconfigured_fails_loudly() -> None:
    context = FakeGraphNodeContext()

    with pytest.raises(AssertionError):
        asyncio.run(cast(GraphNodeContext, context).invoke_agent("tessa", "hello"))
