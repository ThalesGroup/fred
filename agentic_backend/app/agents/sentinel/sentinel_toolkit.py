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

from typing import List, override

from langchain_core.tools import BaseTool, BaseToolkit
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import Field

from app.core.agents.context_aware_tool import ContextAwareTool
from app.core.agents.runtime_context import RuntimeContextProvider


class SentinelToolkit(BaseToolkit):
    """
    Toolkit for MCP documents expert tools with runtime context support.

    This toolkit wraps MCP tools with context awareness, allowing them to
    automatically inject runtime parameters like library filtering.
    """

    tools: List[BaseTool] = Field(
        default_factory=list, description="List of the tools."
    )

    def __init__(
        self,
        mcp_client: MultiServerMCPClient,
        context_provider: RuntimeContextProvider | None = None,
    ):
        super().__init__()
        base_tools = mcp_client.get_tools()

        if context_provider:
            # Wrap tools with context awareness
            self.tools = [
                ContextAwareTool(tool, context_provider) for tool in base_tools
            ]
        else:
            self.tools = base_tools

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
