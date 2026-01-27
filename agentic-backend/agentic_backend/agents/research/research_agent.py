from __future__ import annotations

import asyncio
import logging
from typing import Annotated, List, Type, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

"""
Sample "Researcher" agent used to show how a LangGraph agent can be run from a
Temporal workflow without pulling Temporal dependencies into agent code.

Key idea: the worker (activity) hydrates the graph state from AgentInputV1
before invoking the compiled graph. To let the worker know what to hydrate,
the agent exposes a lightweight schema via get_state_schema().
"""


# 1. Define the State
# The worker looks at this schema to know which fields from AgentInputV1
# belong in the LangGraph state (messages, parameters, context, etc.).
class ResearchAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    research_data: str
    project_id: str  # Hydrated from AgentInputV1.context.project_id
    research_depth: int  # Hydrated from AgentInputV1.parameters['research_depth']


class ResearchAgent(AgentFlow):
    """
    A minimal long-running research agent wired for Temporal, but keeping the
    agent itself free of Temporal imports.

    Why the schema matters:
    - The Temporal activity receives AgentInputV1 (request_text, context, parameters).
    - Before running the graph it "hydrates" the LangGraph state using the schema
      returned by get_state_schema().
    - This lets you add required inputs (e.g., project_id, research_depth) without
      hard-coding Temporal details inside the agent.
    """

    tuning = AgentTuning(
        role="Deep Researcher",
        description="Performs deep research tasks with automatic state hydration.",
        tags=["research", "long-running"],
        fields=[],
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)
        # Build the uncompiled graph; AgentFlow.get_compiled_graph() will compile it lazily.
        self._graph = self._build_graph()

    def get_state_schema(self) -> Type:
        """
        Advertise the expected LangGraph state shape to the worker.

        The activity uses this to map AgentInputV1 fields into the initial state:
        - request_text -> messages (as a HumanMessage)
        - context.project_id -> project_id
        - parameters['research_depth'] -> research_depth

        Keep it simple: include every state key your nodes rely on.
        """
        return ResearchAgentState

    async def async_init(self, runtime_context: RuntimeContext) -> None:
        """Required by AgentFlow to set up context (databases, APIs, etc)."""
        self.runtime_context = runtime_context

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(ResearchAgentState)

        # Define Nodes
        builder.add_node("gather", self.gather_information)
        builder.add_node("analyze", self.analyze_data)
        builder.add_node("draft", self.draft_report)

        # Define Edges
        builder.set_entry_point("gather")
        builder.add_edge("gather", "analyze")
        builder.add_edge("analyze", "draft")
        builder.add_edge("draft", END)

        return builder

    # --- Node Logic ---

    async def gather_information(self, state: ResearchAgentState):
        """
        Notice: project_id and research_depth are already present in the state
        thanks to the AgentFlow.hydrate_state call in the Activity.
        """
        p_id = state.get("project_id", "Default-Project")
        depth = state.get("research_depth", 1)

        logger.info(f"[{p_id}] Starting deep search with depth {depth}...")

        await asyncio.sleep(2)  # Simulate long-running work
        return {
            "messages": [
                AIMessage(content=f"Gathered data for project {p_id} at depth {depth}.")
            ],
            "research_data": "raw_html_content_mock",
        }

    async def analyze_data(self, state: ResearchAgentState):
        """Simulates CPU intensive analysis."""
        logger.info(f"[{state.get('project_id')}] Analyzing content...")
        await asyncio.sleep(2)
        return {
            "messages": [AIMessage(content="Analyzed data. Key trend: AI is growing.")]
        }

    async def draft_report(self, state: ResearchAgentState):
        """Finalizes the output using the initial human request."""
        logger.info(f"[{state.get('project_id')}] Drafting output...")
        await asyncio.sleep(1)

        # state['messages'][0] is the HumanMessage hydrated from input_data.request_text
        original_request = state["messages"][0].content

        final_text = (
            f"RESEARCH REPORT for Project: {state.get('project_id')}\n"
            f"Based on request: {original_request}\n"
            f"Findings: Validated successfully."
        )

        return {"messages": [AIMessage(content=final_text)]}
