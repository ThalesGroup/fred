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

import logging
from pydantic import TypeAdapter
from typing import List, Any

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

logger = logging.getLogger(__name__)


class StatisticExpert(AgentFlow):
    """
    An expert agent that searches and analyzes tabular documents to answer user questions.
    This agent uses MCP tools to list, inspect, and query structured data like CSV or Excel.
    """

    name: str = "StatisticExpert"
    nickname: str = "Sage"
    role: str = "Data Scientist Expert"
    description: str = "Provides an assistant to analyse data, plot graphs and train classic ML models."
    icon: str = "stats_agent"
    categories: list[str] = ["statistics", "ml", "tabular"]
    tag: str = "data"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        self._any_list_adapter: TypeAdapter[List[Any]] = TypeAdapter(List[Any])

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    def _generate_prompt(self) -> str:
        return (
            "You are a data science assistant for structured tabular data (CSV, Excel)\n"
            "Your purpose is to respond precisely to the user's questions and orders.\n"
            "### Rules:\n"
            "- Only use existing datasets and columns.\n"
            "- Use markdown for outputs and code blocks.\n"
            "- Present results clearly and explain them.\n"
            "- Use LaTeX (`$$...$$`) for formulas if needed.\n"
            f"\nThe current date is {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self.reasoner)

        async def _refresh_and_rebind():
            # Refresh MCP (new client + toolkit) and rebind tools into the model.
            # MCPRuntime handles snapshot logging + safe old-client close.
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,  # always returns the latest tool instances
            refresh_cb=_refresh_and_rebind,  # on timeout/401/stream close, refresh + rebind
        )
        builder.add_node("tools", tools_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    async def reasoner(self, state: MessagesState):
        try:
            prompt = SystemMessage(content=self.base_prompt)
            assert self.model is not None, (
                "Model must be initialized before building graph"
            )
            response = await self.model.ainvoke([prompt] + state["messages"])

            return {"messages": [response]}

        except Exception:
            logger.exception("TabularExpert failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while analyzing tabular data."
                    )
                ]
            )
            return {"messages": [fallback]}
