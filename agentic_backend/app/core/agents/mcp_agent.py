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

from fred_core import get_model
from langchain_core.messages import HumanMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow

logger = logging.getLogger(__name__)


class MCPAgent(AgentFlow):
    """
    Agent dynamically created to use MCP-based tools.
    Provides generic reasoning and tool-driven capabilities using the MCP runtime.
    """

    # Class-level metadata
    name: str = "MCPExpert"
    nickname: str = "Mitch"
    role: str = "MCP Expert"
    description: str = (
        "Agent dynamically created to use MCP-based tools for reasoning "
        "and invoking custom MCP capabilities."
    )
    icon: str = "agent_generic"
    categories: list[str] = ["MCP"]
    tag: str = "mcp"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=agent_settings,
            context_provider=lambda: self.get_runtime_context(),
        )
        self.base_prompt = self._generate_prompt()

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    def _generate_prompt(self) -> str:
        return (
            f"{self.agent_settings.base_prompt}\n\n"
            f"The current date is {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._run_reasoning_step)

        async def _refresh_and_rebind():
            # Refresh MCP runtime and rebind the tools in case of failure/timeouts.
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,
            refresh_cb=_refresh_and_rebind,
        )
        builder.add_node("tools", tools_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    async def _run_reasoning_step(self, state: MessagesState):
        try:
            assert self.model is not None, "Model must be initialized before reasoning"
            response = await self.model.ainvoke(
                [self._generate_prompt()] + state["messages"]
            )
            return {"messages": [response]}
        except Exception:
            logger.exception("MCPExpert failed during reasoning.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred.")]
            )
            return {"messages": [fallback]}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "nickname": self.nickname,
            "role": self.role,
            "description": self.description,
            "icon": self.icon,
            "categories": self.categories,
            "tag": self.tag,
            "base_prompt": self.base_prompt,
            "current_date": self.current_date,
        }