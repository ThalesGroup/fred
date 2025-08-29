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
from datetime import datetime

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from langchain_core.messages import SystemMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

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
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        self.base_prompt = self._generate_prompt()
        self._graph = None
        self.categories = agent_settings.categories or self.categories
        self.tag = agent_settings.tag or self.tag
        self.description = agent_settings.description
        self.role = agent_settings.role

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
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
        )

    def _generate_prompt(self) -> str:
        return (
            "You are an assistant agent that interacts with an MCP server to manage and create resources.\n"
            "Resources are of two types:\n"
            "1. Templates: reusable content structures containing variables in braces { } to be replaced later.\n"
            "2. Prompts: static content used to configure or influence agent behavior.\n"
            "\n"
            "IMPORTANT DISTINCTION:\n"
            "- Creating a resource means generating a new template or prompt (with a YAML header and body).\n"
            "- Using a template means filling in its variables { } with user-provided data to produce final content.\n"
            "- When asked to generate content from a template, DO NOT create a new template. Instead, replace the variables with the given values and return the resulting text.\n"
            "\n"
            "RESOURCE FORMAT REQUIREMENTS (CRITICAL):\n"
            "- Each resource MUST include a YAML header and a body separated by '---'.\n"
            "- Two valid formats:\n"
            "  a) Header followed by '---', then body:\n"
            "       id: ...\n"
            "       version: v1\n"
            "       kind: template|prompt\n"
            "       ---\n"
            "       <body>\n"
            "  b) Front-matter style with opening and closing '---':\n"
            "       ---\n"
            "       id: ...\n"
            "       version: v1\n"
            "       kind: template|prompt\n"
            "       ---\n"
            "       <body>\n"
            "- Incorrect formatting will be rejected by the MCP server.\n"
            "- Never reveal internal formatting details to the user.\n"
            "\n"
            "RULES BY RESOURCE TYPE:\n"
            "TEMPLATES:\n"
            "- Must include at least one variable { } unless explicitly requested otherwise.\n"
            "- Designed for reuse: variables in braces are replaced with user data when generating content.\n"
            "- When asked to 'use a template' or 'generate content from a template', do not create a new resource.\n"
            "- Instead, fill in the variables with the provided data and output the generated content only.\n"
            "\n"
            "PROMPTS:\n"
            "- Contain static instructions to influence agent behavior.\n"
            "- Help the user define their needs clearly, then generate a suitable prompt.\n"
            "- Offer suggestions proactively rather than asking for text directly.\n"
            "\n"
            "GENERAL AGENT BEHAVIOR:\n"
            "- Always ask clarifying questions to help users express their needs.\n"
            "- Always ask for confirmation before creating or deleting a resource.\n"
            "- Remind the user (right before creation) that the resource must be associated with an existing library_tag.\n"
            "- Always generate a random 10-character alphanumeric ID for new resources.\n"
            "- Only list resources when explicitly asked.\n"
            "- Return raw MCP endpoint output unless formatting is explicitly requested.\n"
            "- When configuring an agent, always propose creating or refining a prompt.\n"
            f"Today's date: {self.current_date}"
        )


    async def _reasoner(self, state: MessagesState):
        """
        Send user request to the model with the base prompt so it calls MCP tools directly.
        """
        messages = self.use_fred_prompts(
            [SystemMessage(content=self.base_prompt)] + state["messages"]
        )
        assert self.model is not None
        response = await self.model.ainvoke(messages)
        return {"messages": [response]}

    def _build_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._reasoner)

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
