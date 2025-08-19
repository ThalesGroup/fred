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

from app.agents.content_generator.content_generator_toolkit import ContentGeneratorToolkit
from app.common.mcp_utils import get_mcp_client_for_agent
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_template_libraries_ids
from app.core.model.model_factory import get_model
from app.common.resources.resource_client import ResourceClient
from app.common.resources.structures import ResourceKind
from langchain_core.messages import SystemMessage
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
        self.knowledge_flow_url = agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1"
        )
        self.tag = agent_settings.tag or self.tag
        self.description = agent_settings.description
        self.role = agent_settings.role

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)
        self.toolkit = ContentGeneratorToolkit(self.mcp_client)
        self.search_client = ResourceClient(self.knowledge_flow_url, timeout_s=10)
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
        return  (
            "You are an agent that interacts with an MCP server.\n"
            "You manage two types of resources with the same format:\n"
            "1. Templates: content must contain variables in braces { } to be filled.\n"
            "2. Prompts: static content to modify agent behavior (no variables required).\n"
            "\n"
            "RESOURCE FORMAT IS CRITICAL:\n"
            "- You MUST split content into a YAML header and body before sending to the MCP endpoint.\n"
            "- The separator '---' between header and body is REQUIRED.\n"
            "- Supported formats:\n"
            "  1) Header first, then a single '---', then body:\n"
            "       id: ...\n"
            "       version: v1\n"
            "       kind: template|prompt\n"
            "       ---\n"
            "       <body>\n"
            "  2) Front-matter style with opening and closing '---':\n"
            "       ---\n"
            "       id: ...\n"
            "       version: v1\n"
            "       kind: template|prompt\n"
            "       ---\n"
            "       <body>\n"
            "- FAILURE TO FOLLOW THIS FORMAT WILL RESULT IN REJECTION BY THE MCP SERVER.\n"
            "\n"
            "Rules:\n"
            "- Ask for user approval before creating or deleting resources.\n"
            "- Do not proceed with template creation if it contains no variables, unless explicitly requested.\n"
            "- Ensure the resource is associated with an existing library_tag.\n"
            "- Only list resources if explicitly asked.\n"
            "- Provide guidance/examples for creation based on user input.\n"
            "- Return only the raw output from the MCP endpoint unless formatting is requested.\n"
            "- Always wait for user input specifying the resource to create.\n"
            "- Generate a 10 characters alphanumerical value as the resource unique identifier when you create it.\n"
            f"Today's date: {self.current_date}"
)

    async def _reasoner(self, state: MessagesState):
        """
        Send user request to the model with the base prompt so it calls MCP tools directly.
        """
        template_tags = get_template_libraries_ids(self.get_runtime_context()) or []

        selected_templates = []
        if template_tags:
            selected_templates = self.search_client.list_resources(
                kind=ResourceKind.TEMPLATE,
                tags=template_tags,
            )
            # @TODO find out what to do with this list of templates (selected_templates)

        messages = self.use_fred_prompts(
            [SystemMessage(content=self.base_prompt)] + state["messages"]
        )
        assert self.model is not None
        response = await self.model.ainvoke(messages)
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