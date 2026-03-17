# Copyright Thales 2026
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

import json
import logging
from collections import Counter
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentSettings
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

SPOT_TUNING = AgentTuning(
    role="Cluster Prometheus Investigator",
    description=(
        "Investigates cluster-wide Prometheus metrics with PromQL and MCP tools."
    ),
    tags=["monitoring", "promql"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Spot operating instructions: discover metrics and labels, then "
                "build PromQL queries to investigate cluster issues."
            ),
            required=True,
            default=(
                "You are a senior SRE assistant specialized in Prometheus and PromQL.\n\n"
                "Your mission is to investigate incidents and anomalies across the full cluster, "
                "not just the application namespace.\n\n"
                "### Investigation rules:\n"
                "- Default to cluster-wide discovery unless the user explicitly narrows the scope.\n"
                "- Start with discovery: inspect targets, metric metadata, labels, and series before writing expensive PromQL.\n"
                "- Validate that metrics and labels exist before relying on them in queries.\n"
                "- Prefer bounded range queries and aggregation by labels such as cluster, namespace, pod, node, container, job, or instance.\n"
                "- When you execute PromQL, always show the exact query you used in your answer.\n"
                "- Never invent metrics, labels, values, namespaces, or pods.\n"
                "- When the evidence is insufficient, say so and propose the next PromQL checks.\n\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
    mcp_servers=[
        MCPServerRef(id="mcp-knowledge-flow-prometheus-ops"),
    ],
)


class PrometheusState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    prometheus_context: dict[str, Any]


@expose_runtime_source("agent.Spot")
class Spot(AgentFlow):
    tuning = SPOT_TUNING

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp: MCPRuntime | None = None

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def aclose(self):
        if self.mcp is not None:
            await self.mcp.aclose()

    def _build_graph(self) -> StateGraph:
        if self.mcp is None:
            raise RuntimeError(
                "Spot: MCP runtime must be initialized before building the graph."
            )
        builder = StateGraph(PrometheusState)
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", self.mcp.get_tool_nodes())
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    def _maybe_parse_json(self, payload: Any) -> Any:
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:
                return payload
        return payload

    async def _call_tool(
        self,
        tool_name: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if self.mcp is None:
            raise RuntimeError(
                "Spot: MCP runtime is not initialized. Call async_init() first."
            )
        tool = next(
            (
                candidate
                for candidate in self.mcp.get_tools()
                if candidate.name == tool_name
            ),
            None,
        )
        if tool is None:
            logger.warning("Spot could not find MCP tool '%s'.", tool_name)
            return None

        try:
            return self._maybe_parse_json(await tool.ainvoke(payload or {}))
        except Exception:
            logger.exception("Spot failed to call tool '%s'.", tool_name)
            return None

    async def _ensure_prometheus_context(
        self,
        state: PrometheusState,
    ) -> dict[str, Any]:
        cached = state.get("prometheus_context")
        if cached:
            return cached

        context = {
            "metadata": await self._call_tool("prometheus_metadata", {"limit": 50}),
            "labels": await self._call_tool("prometheus_labels"),
            "targets": await self._call_tool("prometheus_targets"),
        }
        state["prometheus_context"] = context
        return context

    def _format_context_for_prompt(self, context: dict[str, Any]) -> str:
        if not context:
            return "\nPrometheus discovery context is currently unavailable."

        lines = ["", "Prometheus discovery context:"]

        metadata_data = context.get("metadata", {}).get("data", {})
        if isinstance(metadata_data, dict) and metadata_data:
            metric_names = sorted(str(metric) for metric in metadata_data.keys())
            lines.append("- Sample known metrics: " + ", ".join(metric_names[:25]))

        labels_data = context.get("labels", {}).get("data", [])
        if isinstance(labels_data, list) and labels_data:
            labels = [str(label) for label in labels_data[:30]]
            lines.append("- Known labels: " + ", ".join(labels))

        targets_data = context.get("targets", {}).get("data", {})
        if isinstance(targets_data, dict):
            active_targets = targets_data.get("activeTargets", [])
            if isinstance(active_targets, list) and active_targets:
                health_counts = Counter(
                    str(target.get("health", "unknown"))
                    for target in active_targets
                    if isinstance(target, dict)
                )
                health_summary = ", ".join(
                    f"{health}: {count}"
                    for health, count in sorted(health_counts.items())
                )
                lines.append(
                    f"- Active scrape targets: {len(active_targets)} ({health_summary})"
                )

            dropped_targets = targets_data.get("droppedTargets", [])
            if isinstance(dropped_targets, list) and dropped_targets:
                lines.append(f"- Dropped scrape targets: {len(dropped_targets)}")

        if len(lines) == 2:
            lines.append("- No discovery data loaded yet.")

        return "\n".join(lines)

    async def reasoner(self, state: PrometheusState):
        if self.model is None:
            raise RuntimeError(
                "Spot: model is not initialized. Call async_init() first."
            )

        tpl = self.get_tuned_text("prompts.system") or ""
        prometheus_context = await self._ensure_prometheus_context(state)
        system_text = self.render(
            tpl + self._format_context_for_prompt(prometheus_context)
        )

        messages = self.with_system(
            system_text,
            self.recent_messages(state["messages"], max_messages=5),
        )
        messages = await self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)

            tool_payloads: dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    tool_payloads[msg.name or "unknown_tool"] = self._maybe_parse_json(
                        msg.content
                    )

            md = getattr(response, "response_metadata", None)
            if not isinstance(md, dict):
                md = {}
            tools_md = md.get("tools", {})
            if not isinstance(tools_md, dict):
                tools_md = {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md

            return {
                "messages": [response],
                "prometheus_context": prometheus_context,
            }

        except Exception:
            logger.exception("Spot failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content=(
                            "An error occurred while investigating cluster metrics "
                            "with Prometheus."
                        )
                    )
                ]
            )
            return {
                "messages": [fallback],
                "prometheus_context": prometheus_context,
            }
