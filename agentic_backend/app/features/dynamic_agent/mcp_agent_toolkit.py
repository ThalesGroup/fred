from typing import override, List
from langchain_core.tools import BaseTool, BaseToolkit
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import Field

from app.application_context import get_mcp_agent_tools
from app.monitoring.tool_monitoring.monitor_tool import monitor_tool

class McpAgentToolkit(BaseToolkit):
    """
    A generic toolkit that loads all available tools from MCP endpoints.
    Suitable for dynamically created agents that use arbitrary MCP URLs.
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self, mcp_client: MultiServerMCPClient):
        super().__init__()
        raw_tools = get_mcp_agent_tools(mcp_client)
        self.tools = [monitor_tool(tool) for tool in raw_tools]

    @override
    def get_tools(self) -> list[BaseTool]:
        return self.tools
