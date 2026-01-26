"""
Temporal test agent used by Temporal scheduler smoke tests.

This agent emits a few deterministic progress updates without calling any LLMs or MCP servers.
It exists to validate Temporal wiring before wiring a full Rico-like workflow.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, List, TypedDict

from langchain_core.messages import AIMessage
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


class TemporalTestState(TypedDict):
    """State tracked by the Temporal test agent graph."""

    messages: Annotated[List[AIMessage], add_messages]
    step: int


class TemporalTestAgent(AgentFlow):
    """Agent used to validate Temporal workflows."""

    TOTAL_STEPS = 3

    tuning = AgentTuning(
        role="Temporal Smoke Test Agent",
        description="Simulates a simple multi-step run and reports progress without external calls.",
        tags=["test", "temporal"],
        fields=[
            FieldSpec(
                key="tuning.step_count",
                type="integer",
                title="Simulated step count",
                description="How many progress steps this agent should emit during a run.",
                default=TOTAL_STEPS,
            )
        ],
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)
        self._graph = self._build_graph()

    async def async_init(self, runtime_context: RuntimeContext) -> None:
        self.runtime_context = runtime_context

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TemporalTestState)
        builder.add_node("step_one", self._step_one)
        builder.add_node("step_two", self._step_two)
        builder.add_node("finalize", self._finalize)
        builder.set_entry_point("step_one")
        builder.add_edge("step_one", "step_two")
        builder.add_edge("step_two", "finalize")
        builder.add_edge("finalize", END)
        return builder

    async def _step_one(self, state: TemporalTestState) -> TemporalTestState:
        await self._simulate_work()
        return self._build_progress_update(
            step=1, text="Establishing Temporal test context."
        )

    async def _step_two(self, state: TemporalTestState) -> TemporalTestState:
        await self._simulate_work()
        return self._build_progress_update(
            step=2, text="Executing simulated processing."
        )

    async def _finalize(self, state: TemporalTestState) -> TemporalTestState:
        await self._simulate_work()
        return self._build_progress_update(
            step=self.TOTAL_STEPS,
            text="Temporal smoke test completed successfully.",
            finished=True,
        )

    def _build_final_answer(self) -> AIMessage:
        return AIMessage(
            content=(
                "Temporal smoke test finished after running three steps. "
                "All progress updates have been streamed."
            ),
            response_metadata={
                "force_final": True,
                "thought": "Temporal smoke test completed summary.",
                "extras": {"task": "temporal-test", "status": "final"},
            },
        )

    async def _simulate_work(self) -> None:
        await asyncio.sleep(0.01)

    def _build_progress_update(
        self, *, step: int, text: str, finished: bool = False
    ) -> TemporalTestState:
        progress_text = f"[{step}/{self.TOTAL_STEPS}] {text}"
        message = AIMessage(
            content=progress_text,
            response_metadata={
                "thought": text,
                "extras": {"task": "temporal-test", "step": step},
                "force_observation": True,
            },
        )
        messages: List[AIMessage] = [message]
        if finished:
            messages.append(
                AIMessage(
                    content="Temporal smoke test agent finished.",
                    response_metadata={
                        "extras": {"task": "temporal-test", "status": "done"},
                        "force_observation": True,
                    },
                )
            )
            messages.append(self._build_final_answer())
        return {"messages": messages, "step": step}
