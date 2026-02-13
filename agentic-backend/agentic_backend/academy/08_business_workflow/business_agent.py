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
from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.messages import ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.integrations.temporal import (
    get_temporal_tool_node,
    get_temporal_tools,
)

logger = logging.getLogger(__name__)


class BusinessAgent(AgentFlow):
    """
    This sample business agent illustrate how an interactive agent can use tools to delegate long running tasks
    to worker agents. Typically these ar long running tasks that must run in the background and be monitored for
    status updates.

    Temporal is the preferred backend for long running workflows in Fred, and this agent uses Temporal tools
    to submit and monitor such workflows. This said as you can see, there is no tight coupling to Temporal itself,
    as the agent simply uses tools exposed by the Temporal integration layer.

    """

    tuning = AgentTuning(
        role="CMA Control Tower",
        description="Simule un agent CMA de type Control Tower capable d'invoquer des workflows applicatifs de longue durée.",
        tags=["temporal", "tools"],
        fields=[],
    )

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        tools = get_temporal_tools()
        self.model = get_default_chat_model().bind_tools(tools)
        self.tool_node = get_temporal_tool_node()
        self._graph = self._build_graph()

    async def aclose(self):
        # No persistent resources to close
        pass

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", self.tool_node)
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    async def reasoner(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError("TemporalMCPClient: model non initialisé")

        system_prompt = (
            "Tu es l'agent interactif BusinessAgent. "
            "Pour déléguer une tâche longue, appelle temporal_submit(request_text, target_agent, project_id?). "
            "Choisis target_agent parmi: OpsWorker (ops longues) ou SalesWorker (commercial longues). "
            "Utilise temporal_status(workflow_id?) pour suivre l'état du dernier workflow (ou préciser un id). "
            "Réponds en français, de façon concise."
        )
        messages = self.with_system(system_prompt, state["messages"])
        response = await self.model.ainvoke(messages)
        # Collect tool outputs (like Sentinel)
        tool_outputs: Dict[str, Any] = {}
        for msg in state["messages"]:
            name = getattr(msg, "name", None)
            if isinstance(msg, ToolMessage) and isinstance(name, str):
                tool_outputs[name] = msg.content
        md = getattr(response, "response_metadata", None)
        if not isinstance(md, dict):
            md = {}
        if tool_outputs:
            md.setdefault("tools", {}).update(tool_outputs)
            response.response_metadata = md
        return {"messages": [response]}
