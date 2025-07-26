# app/agents/dynamic/mcp_agent.py
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

from typing import List, Optional
from datetime import datetime
from app.common.mcp_utils import get_mcp_client_for_agent
from app.core.agents.mcp_agent_toolkit import McpAgentToolkit
from app.core.agents.flow import AgentFlow
from app.core.monitoring.node_monitoring import monitor_node
from langgraph.graph import StateGraph, MessagesState
from langgraph.constants import START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage
from app.application_context import get_agent_settings, toremove_get_model_for_agent

import logging

logger = logging.getLogger(__name__)


class MCPAgent(AgentFlow):
    def __init__(
        self,
        cluster_fullname: str,
        name: str,
        base_prompt: str,
        role: Optional[str] = None,
        nickname: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tag: Optional[str] = None,
    ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.name = name
        self.cluster_fullname = cluster_fullname
        self.agent_settings = get_agent_settings(self.name)
        self.model = toremove_get_model_for_agent(self.agent_settings)
        self.mcp_client = get_mcp_client_for_agent(self.agent_settings)
        self.toolkit = McpAgentToolkit(self.mcp_client)
        self.role = role or "Agent using external MCP tools"
        self.nickname = nickname or name
        self.description = description or "Agent dynamically created to use MCP-based tools."
        self.icon = icon or "agent_generic"
        self.categories = categories or []
        self.tag = tag or "mcp"
        self.base_prompt = base_prompt

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self.build_base_prompt(),
            categories=self.categories,
            tag=self.tag,
            toolkit=self.toolkit,
        )
        
    def build_base_prompt(self) -> str:
        return f"{self.base_prompt}\n\nThe current date is {datetime.now().strftime('%Y-%m-%d')}."

    async def reasoner(self, state: MessagesState):
        try:
            response = await self.model.ainvoke([self.build_base_prompt()] + state["messages"])
            return {"messages": [response]}
        except Exception as e:
            logger.exception(f"Error in MCPAgent.reasoner for agent {self.name}")
            fallback = await self.model.ainvoke([HumanMessage(content="An error occurred.")])
            return {"messages": [fallback]}

    def get_graph(self):
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", monitor_node(self.reasoner))
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cluster_fullname": self.cluster_fullname,
            "base_prompt": self.base_prompt,
            "role": self.role,
            "nickname": self.nickname,
            "description": self.description,
            "icon": self.icon,
            "categories": self.categories,
            "tag": self.tag,
        }