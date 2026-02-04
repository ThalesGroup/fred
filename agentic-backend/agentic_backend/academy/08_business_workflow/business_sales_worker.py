# Copyright Thales 2025
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

import asyncio
import logging
from typing import Annotated, List, Optional, Type, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

"""
Temporal demo agent WITHOUT HITL or delegation.
- Chains three mock phases (10s each) to show heartbeat/progress.
- Finalizes with a short report. Good for showcasing Temporal orchestration.
"""


class DemoAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    project_id: Optional[str]


class SalesWorker(AgentFlow):
    """
    Long-running demo agent: three timed phases, no HITL, no delegation.
    """

    tuning = AgentTuning(
        role="Commercial Control (CMA CGM)",
        description="Simule une tour de contrôle commerciale CMA CGM : SLAs/clients sensibles, risques pénalités, priorisation slots/allocs.",
        tags=["demo", "temporal", "commercial"],
        fields=[],
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)
        self._graph = self._build_graph()

    def get_state_schema(self) -> Type:
        """State used for hydration when run via Temporal."""
        return DemoAgentState

    async def async_init(self, runtime_context: RuntimeContext) -> None:
        self.runtime_context = runtime_context

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(DemoAgentState)

        builder.add_node("phase_one", self.phase_one)
        builder.add_node("phase_two", self.phase_two)
        builder.add_node("phase_three", self.phase_three)
        builder.add_node("draft", self.draft_report)

        builder.set_entry_point("phase_one")
        builder.add_edge("phase_one", "phase_two")
        builder.add_edge("phase_two", "phase_three")
        builder.add_edge("phase_three", "draft")
        builder.add_edge("draft", END)

        return builder

    # --- Phases ---
    async def phase_one(self, state: DemoAgentState):
        project = state.get("project_id") or "Sales-CMA-CGM"
        await asyncio.sleep(10)
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"[Phase 1/3] Brief commercial pour {project} : "
                        "extraction des bookings prioritaires, SLAs clients, et volumes à risque."
                    )
                )
            ]
        }

    async def phase_two(self, state: DemoAgentState):
        project = state.get("project_id") or "Sales-CMA-CGM"
        await asyncio.sleep(10)
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"[Phase 2/3] Analyse pénalités/slots pour {project} : "
                        "risque de pénalité SLA, besoins de priorisation d'allocation conteneurs, "
                        "et propositions de reroutage client."
                    )
                )
            ]
        }

    async def phase_three(self, state: DemoAgentState):
        project = state.get("project_id") or "Sales-CMA-CGM"
        await asyncio.sleep(10)
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"[Phase 3/3] Consolidation {project} : plan d'actions clients "
                        "(notifications comptes sensibles, gestes commerciaux, propositions alternatives)."
                    )
                )
            ]
        }

    async def draft_report(self, state: DemoAgentState):
        project = state.get("project_id") or "Sales-CMA-CGM"
        original_request = state["messages"][0].content if state.get("messages") else ""
        final_text = (
            f"DEMO REPORT for {project}\n"
            f"Request: {original_request}\n"
            "Phases: 1) brief commercial/SLAs, 2) analyse pénalités & slots, "
            "3) plan d'actions clients.\n"
            "Status: Completed (no HITL).\n"
            "Note: contenu simulé pour démonstration CMA CGM (commercial)."
        )
        return {"messages": [AIMessage(content=final_text)]}
