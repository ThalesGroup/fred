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

from datetime import datetime

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model
from langgraph.graph import MessagesState, StateGraph
from langgraph.constants import START
from langgraph.prebuilt import tools_condition


class JiraExpert(AgentFlow):
    """
    Expert to execute actions on a a Jira Instance.
    """

    # Class-level attributes for metadata
    name: str = "JiraExpert"
    nickname: str = "Josh"
    role: str = "Jira Expert"
    description: str = "An expert that has access to Jira API and can perform issues queries and aggregate data in a clear and concise manner"
    icon: str = "jira_agent"
    categories: list[str] = ["Jira"]
    tag: str = "jira operator"  # Défini au niveau de la classe

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.model = get_model(self.agent_settings.model)
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        self.base_prompt = self._generate_prompt()

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self.get_graph()

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Jira expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        lines = [
            "You are a Jira expert with access to tools for retrieving and analyzing data from Jira APIs. You are equipped with MCP server tools.",
            "### Your Primary Responsibilities:",
            "1. **Retrieve Data**: Use the provided tools, including MCP server tools, to fetch data for:",
            "   - Ongoing issues associated to the API key user.",
            "   - Summarize the worklog",
            "   - Give an overview of the issues events and potential comments",
            "   - Provide the resolution field & status of the issue everytime you mention it"
            "2. **Aggregate Data**: Execute appropriate commands using the MCP server in order to:",
            "   - Give a concise status of the work the API key user has.",
            "   - Summarize key insights in a user-friendly manner.",
            "   - Provide the title of the Jira ticket everytime since the ticket Identifier is not really easy to understand",
            "### Key Instructions:",
            "1. Always use tools to fetch data before providing answers. Avoid generating generic guidance or assumptions.",
            "2. Aggregate and analyze the data to directly answer the user's query.",
            "3. Present the results clearly, with summaries, breakdowns, and trends where applicable.",
            "4. Everytime you mention a ticket, indicate who created it, the creation date and time, the status, who it is assigned to and a summary of the issue.",
            "5. Always summarize the comments of the tickets if there are any.",
            "6. When listing tickets, provide its title as a bold clickable link that redirects to the issue in Jira (not the API link, the actual link.)."
            f"The current date is {datetime.now().strftime('%Y-%m-%d')}.",
        ]
        return "\n".join(lines)

    async def reasoner(self, state: MessagesState):
        response = self.model.invoke([self.base_prompt] + state["messages"])

        return {"messages": [response]}

    def get_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self.reasoner)

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
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder
