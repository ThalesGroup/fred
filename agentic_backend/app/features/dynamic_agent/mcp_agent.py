# app/agents/dynamic/mcp_agent.py

from typing import List, Optional
from datetime import datetime
from app.features.dynamic_agent.mcp_agent_toolkit import McpAgentToolkit
from app.flow import AgentFlow
from langgraph.graph import StateGraph, MessagesState
from langgraph.constants import START
from langgraph.prebuilt import ToolNode, tools_condition
from app.monitoring.node_monitoring.monitor_node import monitor_node
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

import logging

logger = logging.getLogger(__name__)

class MCPAgent(AgentFlow):
    def __init__(
        self,
        name: str,
        prompt: str,
        mcp_urls: List[str],
        role: Optional[str] = None,
        nickname: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tag: Optional[str] = None,
    ):
        self.name = name
        self.role = role or "Agent using external MCP tools"
        self.nickname = nickname or name
        self.description = description or "Agent dynamically created to use MCP-based tools."
        self.icon = icon or "agent_generic"
        self.categories = categories or []
        self.tag = tag or "mcp"
        self.current_date = datetime.now().strftime("%Y-%m-%d")

        self.prompt = prompt
        self.mcp_client = MultiServerMCPClient(mcp_urls)  # handle multiple URLs
        self.toolkit = McpAgentToolkit(self.mcp_client)

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
        return f"{self.prompt}\n\nThe current date is {self.current_date}."

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
