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

import json
import logging
from datetime import datetime
from typing import Optional

from app.agents.tabular.toolkit import TabularToolkit
from app.flow import AgentFlow
from app.application_context import (
    get_agent_settings,
    get_mcp_client_for_agent,
    get_model_for_agent,
)
from app.monitoring.node_monitoring.monitor_node import monitor_node
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)


class TabularExpert(AgentFlow):
    """
    An expert agent that searches and analyzes documents to answer user questions.
    This agent uses a vector search service to find relevant documents and generates
    responses based on the document content.
    """

    name: str = "TabularExpert"
    role: str = "Tabular Data Expert"
    nickname: str = "Tessa"
    description: str = """
        An agent specialized in searching and analyzing structured 
        tabular data (e.g. CSV, XLSX).
        """
    icon: str = "tabulat_agent"
    categories: list[str] = ["tabular", "sql"]
    tag: str = "data"

    def __init__(self, cluster_fullname: Optional[str] = None):
        """
        Initialize the TabularExpert agent with settings and configuration.
        Loads settings from agent configuration and sets up connections to the
        knowledge base service.
        """
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.agent_settings = get_agent_settings(self.name)
        self.model = get_model_for_agent(self.name)
        self.mcp_client = get_mcp_client_for_agent(self.name)
        self.toolkit = TabularToolkit(self.mcp_client)
        self.categories = (
            self.agent_settings.categories
            if self.agent_settings.categories
            else ["documents"]
        )
        self.base_prompt = self._generate_prompt()
        if self.agent_settings.tag:
            self.tag = self.agent_settings.tag

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
            toolkit=self.toolkit,
        )

    def _generate_prompt(self) -> str:
        return (
            "You are a data analyst agent tasked with answering user questions based on structured tabular data "
            "such as CSV or Excel files. Use the available tools to **list, inspect, and query datasets** to answer questions.\n"
            "### Instructions:\n"
            "1. ALWAYS start by invoking the tool to **list all available datasets**.\n"
            "2. For each dataset you think might be relevant, invoke the tool to **get its schema**.\n"
            "   - If you're unsure, get schemas for **all datasets**.\n"
            "3. Decide which dataset(s) to use.\n"
            "4. Formulate an SQL-like query using the relevant schema.\n"
            "5. Invoke the query tool to get the answer.\n"
            "6. Derive your final answer from the actual data you retrieved.\n"
            "\n"
            "### Rules:\n"
            "- Use markdown tables in your answer if you want to present tabular results.\n"
            "- Do NOT invent columns or data that you haven't seen in the schema.\n"
            "- If you use mathematical formulas, **always format them using LaTeX enclosed in `$$...$$` for block math, or `$...$` for inline math**.\n"
            "   - ❌ Do NOT use `\\[...\\]` or `\\(...\\)`\n"
            "   - ✅ Example block: `$$\\frac{a}{b}$$`\n"
            f"\nThe current date is {self.current_date}.\n"
        )

    async def reasoner(self, state: MessagesState):
        try:
            response = await self.model.ainvoke([self.base_prompt] + state["messages"])

            for msg in state["messages"]:
                if isinstance(msg, ToolMessage):
                    try:
                        datasets = json.loads(msg.content)
                        summaries = self.extract_datasets_from_tool_response(datasets)

                        if summaries:
                            dataset_text = "\n".join(summaries)
                            response.content += (
                                "\n\n### Available Datasets:\n" + dataset_text
                            )
                    except Exception as e:
                        logger.warning(f"Failed to parse tool result: {e}")
            return {"messages": [response]}

        except Exception as e:
            logger.exception("Error in TabularExpert.reasoner")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while processing tabular data."
                    )
                ]
            )
            return {"messages": [fallback]}

    def extract_datasets_from_tool_response(self, data: list[dict]) -> list[str]:
        """
        Create short markdown summaries from the list of dataset entries.
        """
        summaries = []
        for entry in data:
            try:
                title = entry.get("title", "Untitled")
                uid = entry.get("document_uid", "")
                rows = entry.get("row_count", "?")
                summaries.append(f"- **{title}** (`{uid}`), {rows} rows")
            except Exception as e:
                logger.warning(f"Failed to summarize entry: {e}")
        return summaries

    def get_graph(self):
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", monitor_node(self.reasoner))
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder
