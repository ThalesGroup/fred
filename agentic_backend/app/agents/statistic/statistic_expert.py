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

import json
import logging
from datetime import datetime

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

logger = logging.getLogger(__name__)


class StatisticExpert(AgentFlow):
    """
    An expert agent that searches and analyzes tabular documents to answer user questions.
    This agent uses MCP tools to list, inspect, and query structured data like CSV or Excel.
    """

    name: str
    role: str
    nickname: str = "Sage"
    description: str
    icon: str = "stats_agent"
    categories: list[str] = ["statistics", "ml", "tabular"]
    tag: str = "data"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.model = None
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        self.base_prompt = self._generate_prompt()
        self._graph = None
        self.categories = agent_settings.categories or ["statistics", "ml"]
        self.tag = agent_settings.tag or "data"
        self.description = agent_settings.description
        self.role = agent_settings.role

############################################################################################

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
        )

    def _generate_prompt(self) -> str:
        return (
            "You are a data science assistant capable of performing **statistical analysis** and **machine learning** "
            "on structured tabular datasets (CSV, Excel).\n\n"
            "### Instructions:\n"
            "1. ALWAYS start by listing available datasets and inspecting their schema.\n"
            "2. You can use the following abilities:\n"
            "- **Describe datasets**: mean, median, std, value counts, histograms.\n"
            "- **Statistical testing**: A/B tests, t-tests, chi-square, correlations.\n"
            "- **Machine Learning**: Train models like Linear Regression, XGBoost, Random Forest.\n"
            "- **Update data**: create or update columns, transform values.\n"
            "3. Formulate a step-by-step approach to solve the problem using available tools.\n\n"
            "### Rules:\n"
            "- Use markdown for results and code outputs.\n"
            "- Do not invent columns, datasets, or values.\n"
            "- Present statistical outputs clearly with explanations.\n"
            "- Use LaTeX (`$$...$$`) for formulas if needed.\n"
            f"\nThe current date is {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._run_reasoning_step)

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
        builder.add_conditional_edges(
            "reasoner", tools_condition
        )  # conditional → "tools"
        builder.add_edge("tools", "reasoner")

        return builder

    async def _run_reasoning_step(self, state: MessagesState):
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


