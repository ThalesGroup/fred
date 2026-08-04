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
Upstream-semantics test for LangGraph's `Interrupt.id` (#2216 P1).

Why this file exists:
- an earlier draft of #2216's fix assumed `Interrupt.id` is universally
  occurrence-unique. That is FALSE for the installed LangGraph version: two
  sequential `interrupt()` calls within the SAME node execution (LangGraph
  re-executes a paused node from the top on resume — see
  `langgraph.types.interrupt`'s own docstring) reuse the identical id,
  matched by call ORDER instead
  (`langgraph/pregel/_algo.py::_scratchpad`'s `task_resume_write` list).
- this test pins that fact directly against the installed LangGraph
  package, independent of any FRED code, so a future LangGraph upgrade
  that changes this behavior is caught here rather than silently
  invalidating the narrower claim FRED actually relies on.
- the narrower, FRED-specific claim — that `FredHitlMiddleware` never
  raises more than one `interrupt()` per task, so two DISTINCT FRED HITL
  prompts always get different ids — is proven separately in
  `test_react_loop_regressions_1972.py::test_hitl_resume_two_sequential_prompts_get_different_interrupt_ids`,
  against FRED's real tool loop rather than a toy graph.
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from fred_runtime.runtime_support.checkpoints import checkpoint_config
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class _State(TypedDict):
    foo: str


def _node_two_sequential_interrupts(state: _State) -> _State:
    first = interrupt("question-1")
    second = interrupt("question-2")
    return {"foo": f"{first}-{second}"}


@pytest.mark.asyncio
async def test_two_sequential_interrupts_in_the_same_task_share_an_id() -> None:
    builder = StateGraph(_State)
    builder.add_node("node", _node_two_sequential_interrupts)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = checkpoint_config(thread_id="t1")

    first_result = await graph.ainvoke({"foo": "x"}, config)
    first_interrupts = first_result["__interrupt__"]
    assert len(first_interrupts) == 1
    first_id = first_interrupts[0].id

    second_result = await graph.ainvoke(Command(resume="answer-1"), config)
    second_interrupts = second_result["__interrupt__"]
    assert len(second_interrupts) == 1
    second_id = second_interrupts[0].id

    # The defining, counter-intuitive fact: same task (LangGraph re-executes
    # the node from the top on resume), same Interrupt.id — even though the
    # two interrupt() calls carry different values ("question-1" vs
    # "question-2") and this is the SECOND ainvoke (a different pregel
    # step). Resume matching for this shape relies on call ORDER within the
    # task (`scratchpad.resume` list), not on the id.
    assert first_id == second_id
