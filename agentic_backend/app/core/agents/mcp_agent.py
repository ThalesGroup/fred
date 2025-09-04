from typing import List
from app.common.mcp_utils import get_mcp_client_for_agent
from app.common.structures import AgentSettings
from app.core.agents.mcp_agent_toolkit import McpAgentToolkit
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model
from langgraph.graph import StateGraph, MessagesState
from langgraph.constants import START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage
import logging

logger = logging.getLogger(__name__)


class MCPAgent(AgentFlow):
    """
    Agent dynamically created to use MCP-based tools
    """

    # Class-level metadata
    name: str | None = "MCPExpert"
    nickname: str | None = "Mitch"
    role: str | None = "MCP Expert"
    description: (
        str | None
    ) = "Agent dynamically created to use MCP-based tools."
    icon: str = "agent_generic"
    categories: List[str] = ["MCP"]
    tag: str = "mcp"

    def __init__(
        self,
        agent_settings: AgentSettings,
    ):
        super().__init__(agent_settings=agent_settings)
        self.base_prompt = agent_settings.base_prompt
        self.description = (
            agent_settings.description
            or "Agent dynamically created to use MCP-based tools."
        )

        # Will be set in async_init
        self.mcp_client = None
        self.toolkit = None

    async def async_init(self):
        """
        Performs async initialization of the agent (tool loading, model, graph).
        """
        self.model = get_model(self.agent_settings.model)
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)
        self.toolkit = McpAgentToolkit(self.mcp_client)
        self.model = self.model.bind_tools(self.toolkit.get_tools())
        self._graph = self.get_graph()

    def build_base_prompt(self) -> str:
        return f"{self.base_prompt}\n\nThe current date is {self.current_date}."

    async def reasoner(self, state: MessagesState):
        try:
            assert self.model
            response = await self.model.ainvoke(
                [self.build_base_prompt()] + state["messages"]
            )
            return {"messages": [response]}
        except Exception:
            logger.exception(f"Error in MCPAgent.reasoner for agent {self.name}")
            assert self.model
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred.")]
            )
            return {"messages": [fallback]}

    def get_graph(self):
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)
        assert self.toolkit is not None, (
            "Toolkit must be initialized before building graph"
        )
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "base_prompt": self.base_prompt,
            "role": self.role,
            "nickname": self.nickname,
            "description": self.description,
            "icon": self.icon,
            "categories": self.categories,
            "tag": self.tag,
        }
