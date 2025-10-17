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
import json
from typing import Any, Dict

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

logger = logging.getLogger(__name__)


class StatisticExpert(AgentFlow):
    """
    A data science expert agent for analyzing tabular datasets.
    This assistant can plot graphs, perform statistical analysis, and train basic ML models.
    """

    # Metadata
    name: str = "StatisticExpert"
    nickname: str = "Sage"
    role: str = "Data Scientist Expert"
    description: str = "Provides an assistant to analyse data, plot graphs and train classic ML models."
    icon: str = "stats_agent"
    categories: list[str] = ["statistics", "ml", "tabular"]
    tag: str = "data"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=agent_settings,
            context_provider=(lambda: self.get_runtime_context()),
        )
        self.base_prompt = self._generate_prompt()

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    def _generate_prompt(self) -> str:
        return (
            "You are a helpful and precise data science assistant working on structured data (CSV, Excel).\n"
            "Your main tasks are to analyze datasets, generate visualizations, and build simple machine learning models.\n\n"
            "### Instructions:\n"
            "1. List available datasets and explore their schema.\n"
            "2. Apply statistical analysis or ML models when asked.\n"
            "3. Visualize data using appropriate chart types.\n"
            "4. Answer clearly and interpret your results.\n\n"
            "### Rules:\n"
            "- Use markdown to format outputs and wrap code in code blocks.\n"
            "- NEVER make up data or columns that don't exist.\n"
            "- Prefer visual explanations and graphs where applicable.\n"
            "- Format mathematical expressions using LaTeX: `$$...$$` for display or `$...$` inline.\n"
            f"\nThe current date is {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._run_reasoning_step)

        async def _refresh_and_rebind():
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,
            refresh_cb=_refresh_and_rebind,
        )
        builder.add_node("tools", tools_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "StatisticExpert: model is not initialized. Call async_init() first."
            )

        # 1) Construction du prompt système via un template custom (tuning)
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)

        # 2) Préparation de la liste des messages en injectant le message système et contexte de chat
        messages = self.with_system(system_text, state["messages"])
        messages = self.with_chat_context_text(messages)

        try:
            # 3) Appel asynchrone au modèle
            response = await self.model.ainvoke(messages)

            # 4) Extraction des sorties des outils dans les messages (ToolMessage)
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    normalized: Any = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            # Garde la chaîne brute si ce n’est pas un JSON valide
                            normalized = raw
                    tool_payloads[msg.name or "unknown_tool"] = normalized

            # 5) Fusion des métadonnées outils dans la réponse pour l’UI
            md = getattr(response, "response_metadata", None)
            if not isinstance(md, dict):
                md = {}
            tools_md = md.get("tools", {})
            if not isinstance(tools_md, dict):
                tools_md = {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md

            return {"messages": [response]}

        except Exception:
            logger.exception("StatisticExpert failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while analyzing data or training a model."
                    )
                ]
            )
            return {"messages": [fallback]}
