from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field
from langchain_mcp_adapters.client import MultiServerMCPClient

class DocumentsToolkit(BaseToolkit):
    """
    Toolkit for MCP documents expert tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self, mcp_client: MultiServerMCPClient):
        super().__init__()
        self.tools = mcp_client.get_tools()

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
