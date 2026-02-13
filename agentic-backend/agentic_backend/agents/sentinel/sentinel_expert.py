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
from typing import Any, Dict

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
SENTINEL_TUNING = AgentTuning(
    role="sentinel_expert",
    description="Sentinel expert for operations and monitoring using MCP tools (OpenSearch and KPIs).",
    tags=["monitoring"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Sentinel’s operating doctrine. Keep it focused on MCP tools, "
                "concise ops guidance, and actionable next steps."
            ),
            required=True,
            default=(
                "You are Sentinel, an operations and monitoring agent for the Fred platform.\n"
                "Use the available MCP tools to inspect OpenSearch health and application KPIs.\n"
                "- Use os.* tools for cluster status, shards, indices, mappings, and diagnostics.\n"
                "- Use kpi.* tools for usage, cost, latency, and error rates.\n"
                "Return clear, actionable summaries. If something is degraded, propose concrete next steps.\n"
                "When you reference data from tools, add short bracketed markers like [os_health], [kpi_query].\n"
                "Prefer structured answers with bullets and short tables when helpful.\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
    mcp_servers=[
        MCPServerRef(id="mcp-knowledge-flow-opensearch-ops"),
    ],
)


@expose_runtime_source("agent.Sammy")
class SentinelExpert(AgentFlow):
    """
    Sentinel — Ops & Monitoring agent (OpenSearch + KPIs).

    Pattern alignment with AgentFlow:
    - Class-level `tuning` (spec only; values come from YAML/DB/UI).
    - async_init(): set model, init MCP (tools), bind tools, build graph.
    - Each node chooses if/when to use the tuned prompt (no global magic).
    """

    tuning = SENTINEL_TUNING

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)

        # 1) LLM. Here we use the default chat model from backend application context.
        # In a real setup, you might want to allow tuning this per-agent.
        self.model = get_default_chat_model()

        # 2) Tools
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()  # start MCP + toolkit
        self.model = self.model.bind_tools(self.mcp.get_tools())

        # 3) Graph
        self._graph = self._build_graph()

    async def aclose(self):
        await self.mcp.aclose()

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        if self.mcp.toolkit is None:
            raise RuntimeError(
                "Sentinel: toolkit must be initialized before building the graph."
            )

        builder = StateGraph(MessagesState)

        # LLM node
        builder.add_node("reasoner", self.reasoner)

        builder.add_node("tools", self.mcp.get_tool_nodes())
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def reasoner(self, state: MessagesState):
        """
        One LLM step; may decide to call tools (kpi.* or os.*).
        After tools run, ToolMessages are present in `state["messages"]`.
        We collect their outputs and attach to the model response metadata for the UI.
        """
        if self.model is None:
            raise RuntimeError(
                "Sentinel: model is not initialized. Call async_init() first."
            )

        # 1) Build the system prompt from tuning (and tokens like {today})
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)  # keeps unknown {tokens} literal

        # 2) Ask the model with a single SystemMessage prepended
        messages = self.with_system(system_text, state["messages"])
        messages = await self.with_chat_context_text(messages)

        try:
            # self.log_message_summary(messages)
            response = await self.model.ainvoke(messages)

            # 3) Collect tool outputs (latest per tool name) from the history
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                name = getattr(msg, "name", None)
                if isinstance(msg, ToolMessage) and isinstance(name, str):
                    raw = msg.content
                    # Accept dict/list directly; try JSON decode for strings
                    normalized: Any = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw  # keep raw string if not JSON
                    tool_payloads[name] = normalized

            # 4) Attach tool results to metadata for the UI
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
            logger.exception("Sentinel: unexpected error")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while checking the system. Please try again."
                    )
                ]
            )
            return {"messages": [fallback]}
