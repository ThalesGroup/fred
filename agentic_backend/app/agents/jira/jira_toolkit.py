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

from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field
from langchain_mcp_adapters.client import MultiServerMCPClient


class JiraExpertToolkit(BaseToolkit):
    """
    Toolkit for Jira tools
    """

    tools: List[BaseTool] = Field(
        default_factory=list, description="List of the tools."
    )

    def __init__(self, mcp_client: MultiServerMCPClient):
        super().__init__()
        self.tools = self._fetch_tools(mcp_client)

    def _fetch_tools(self, mcp_client: MultiServerMCPClient) -> List[BaseTool]:
        raw_tools = mcp_client.get_tools()
        if not raw_tools:
            raise ValueError("❌ MCP server returned no tools. Check server config or availability.")
        return raw_tools

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
