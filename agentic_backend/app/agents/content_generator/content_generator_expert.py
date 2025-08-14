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

from app.agents.content_generator.content_generator_toolkit import ContentGeneratorToolkit
from app.common.mcp_utils import get_mcp_client_for_agent
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)


class ContentGeneratorExpert(AgentFlow):
    """
    An expert agent that searches and analyzes tabular documents to answer user questions.
    This agent uses MCP tools to list, inspect, and query structured data like CSV or Excel.
    """

    name: str
    role: str
    nickname: str = "Brontë"
    description: str
    icon: str = "content_generator"
    categories: list[str] = ["blog", "content", "cir"]
    tag: str = "content generator"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.model = None
        self.mcp_client = None
        self.toolkit = None
        self.base_prompt = self._generate_prompt()
        self._graph = None
        self.categories = agent_settings.categories or self.categories
        self.tag = agent_settings.tag or self.tag
        self.description = agent_settings.description
        self.role = agent_settings.role

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)
        self.toolkit = ContentGeneratorToolkit(self.mcp_client)
        self.model = self.model.bind_tools(self.toolkit.get_tools())
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
            toolkit=self.toolkit,
        )

    def _generate_prompt(self) -> str:
        return (
            "You are a simple agent that interacts with an MCP server.\n"
            "First, call the MCP tool to list available resources.\n"
            "Then, if a template is chosen, call the content-generation tool using that template.\n"
            "Return only what the MCP endpoint provides, no extra formatting unless asked.\n"
            "You can also create resources, if so, provide an example and guide the user based on the request payload you can send the MCP endpoint.\n"
            "You MUST ask for the user’s approval before creating or deleting resources.\n"
            "Before sending any value to the MCP endpoint, ensure it is properly formatted: "
            "if it contains a resource file, split it into a YAML header (dict) and body (str) "
            "according to one of the supported forms:\n"
            "1) Header first, then a single line '---' separator, then body\n"
            "   id: ...\n"
            "   version: v1\n"
            "   kind: template\n"
            "   ---\n"
            "   <body>\n"
            "2) Classic front-matter with opening and closing '---'\n"
            "   ---\n"
            "   id: ...\n"
            "   version: v1\n"
            "   kind: template\n"
            "   ---\n"
            "   <body>\n"
            f"Today's date: {self.current_date}"
        )


    async def _reasoner(self, state: MessagesState):
        """
        Send user request to the model with the base prompt so it calls MCP tools directly.
        """
        response = await self.model.ainvoke([self.base_prompt] + state["messages"])
        return {"messages": [response]}


    def _build_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._reasoner)
        assert self.toolkit is not None, (
            "Toolkit must be initialized before building graph"
        )
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder