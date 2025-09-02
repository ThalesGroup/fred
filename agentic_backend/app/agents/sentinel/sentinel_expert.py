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

# app/agents/sentinel/sentinel.py

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition
from pydantic import TypeAdapter

from app.common.mcp_runtime import MCPRuntime

from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

logger = logging.getLogger(__name__)


class SentinelExpert(AgentFlow):
    """
    Sentinel — Ops & Monitoring agent (OpenSearch + KPIs).

    Design goals:
    - Keep the agent focused on reasoning/presentation.
    - Push all MCP client/tool refresh logic into MCPRuntime.
    - Use a resilient ToolNode so transient 401/stream issues turn into
      structured ToolMessages (not hard failures), then refresh MCP and continue.
    """

    # Class-level metadata
    name: str = "SentinelExpert"
    nickname: str = "Samy"
    role: str = "Ops & Monitoring Expert"
    description: str = "Watches your instance, providing real-time monitoring and alerts for performance issues."
    icon: str = "ops_agent"
    categories: list[str] = []
    tag: str = "ops"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        # Generic adapter that tolerates list/dict tool payloads (we won't enforce a single schema)
        self._any_list_adapter: TypeAdapter[List[Any]] = TypeAdapter(List[Any])

    async def async_init(self):
        # LLM
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def aclose(self):
        # Let AgentManager call this on shutdown if it supports it.
        await self.mcp.aclose()

    def _generate_prompt(self) -> str:
        return (
            "You are Sentinel, an operations and monitoring agent for the Fred platform.\n"
            "Use the available MCP tools to inspect OpenSearch health and application KPIs.\n"
            "- Use os.* tools for cluster status, shards, indices, mappings, and diagnostics.\n"
            "- Use kpi.* tools for usage, cost, latency, and error rates.\n"
            "Return clear, actionable summaries. If something is degraded, propose concrete next steps.\n"
            "When you reference data from tools, add short bracketed markers like [os_health], [kpi_query].\n"
            "Prefer structured answers with bullets and short tables when helpful.\n"
            f"Current date: {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        if self.mcp.toolkit is None:
            raise RuntimeError("Toolkit must be initialized before building graph")

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

    async def reasoner(self, state: MessagesState):
        """
        One LLM step; may call tools (kpi.* or os.*). After tools run, we collect their
        outputs (JSON/objects) from ToolMessages and attach to response metadata for the UI.

        Fred rationale:
        - Run MCP preflight *before* the LLM decides to call tools. This ensures the
          underlying httpx Auth minted a fresh token (client-credentials) for this turn.
        - Preflight should be cheap and non-fatal: if it fails, we log and keep going.
        """
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        # if self.toolkit is not None:
        #     await self._preflight_mcp(timeout_seconds=2.0)

        try:
            response = self.model.invoke([self.base_prompt] + state["messages"])

            # Collect tool outputs by tool name, keep last result per tool call
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    # Normalize content: accept list/dict directly, else try JSON parse
                    normalized = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw  # keep raw string if not JSON
                    if msg.name is not None:
                        tool_payloads[msg.name] = normalized

            # Attach tool results to metadata for the UI
            existing = response.response_metadata.get("tools", {})
            existing.update(tool_payloads)
            response.response_metadata["tools"] = existing

            return {"messages": [response]}

        except Exception as e:
            logger.exception("Sentinel: unexpected error: %s", e)
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while checking the system. Please try again."
                    )
                ]
            )
            return {"messages": [fallback]}
