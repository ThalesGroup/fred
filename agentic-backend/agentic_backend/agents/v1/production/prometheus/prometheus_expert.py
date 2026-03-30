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
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
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

_METRICS_INVENTORY_LIMIT = 5000

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
                "You are Spot, a senior SRE assistant specialized in Prometheus and PromQL.\n\n"
                "Your mission is to investigate incidents and anomalies across the full cluster.\n\n"
                "### Mandatory workflow:\n"
                "- Before any prometheus_query or prometheus_query_range, rely on the full metric inventory that has already been preloaded outside the prompt.\n"
                "- Never invent, approximate, or guess a metric name.\n"
                "- First identify candidate metrics from the preloaded inventory.\n"
                "- The full raw inventory is not printed in the prompt to save tokens.\n"
                "- Use prometheus_metrics(search=...) one or more times to inspect small relevant subsets before choosing exact metric names.\n"
                "- Once you have candidate exact names, validate them with prometheus_metadata(metric=exact_metric_name) and, if needed, prometheus_series(matchers=[exact_metric_name]).\n"
                "- Only after that, build and execute PromQL using exact metric names that exist in the inventory or in prometheus_metrics(search=...) results.\n"
                "- When you answer, always show the exact PromQL you executed.\n"
                "- If you cannot identify an exact metric name, do not query Prometheus yet: continue discovery.\n\n"
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
        logger.info(
            "[SPOT] async_init start agent_id=%s agent_name=%s",
            self.agent_settings.id,
            self.agent_settings.name,
        )
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()
        tools = self.mcp.get_tools()
        self.model = self.model.bind_tools(tools)
        self._graph = self._build_graph()
        logger.info(
            "[SPOT] async_init complete agent_id=%s tool_count=%s",
            self.agent_settings.id,
            len(tools),
        )

    async def aclose(self):
        if self.mcp is not None:
            await self.mcp.aclose()

    def _build_graph(self) -> StateGraph:
        if self.mcp is None:
            raise RuntimeError(
                "Spot: MCP runtime must be initialized before building the graph."
            )
        logger.info("[SPOT] building agent graph")
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

    def _known_metric_names(self, state: PrometheusState) -> set[str]:
        metrics_data = (
            state.get("prometheus_context", {}).get("metrics", {}).get("data", [])
        )
        if not isinstance(metrics_data, list):
            return set()
        return {str(metric) for metric in metrics_data if isinstance(metric, str)}

    def _truncate(self, value: Any, limit: int = 240) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _latest_human_message(self, state: PrometheusState) -> str | None:
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage) and isinstance(message.content, str):
                content = message.content.strip()
                if content:
                    return content
        return None

    def _summarize_context(self, context: dict[str, Any]) -> str:
        metrics_count = 0

        metrics_data = context.get("metrics", {}).get("data")
        if isinstance(metrics_data, list):
            metrics_count = len(metrics_data)

        return f"metrics={metrics_count}"

    def _compact_inventory_context(self, metric_names: list[str]) -> list[str]:
        return [
            f"- Full metric inventory preloaded outside the prompt: {len(metric_names)} exact metric names.",
            "- The raw inventory is intentionally hidden to avoid polluting the LLM context.",
            "- Use prometheus_metrics(search=...) to inspect only the relevant subset before metadata or PromQL.",
        ]

    def _summarize_tool_calls(self, response: AIMessage) -> str:
        summaries: list[str] = []
        for tool_call in getattr(response, "tool_calls", []):
            name = tool_call.get("name", "unknown")
            args = tool_call.get("args", {})
            if isinstance(args, dict):
                arg_summary = ", ".join(
                    f"{key}={self._truncate(value, 120)}"
                    for key, value in sorted(args.items())
                )
            else:
                arg_summary = self._truncate(args, 120)
            summaries.append(f"{name}({arg_summary})")
        return "; ".join(summaries) if summaries else "no_tool_calls"

    def _summarize_tool_payload(self, payload: dict[str, Any] | None) -> str:
        if not payload:
            return "empty"
        return ", ".join(
            f"{key}={self._truncate(value, 120)}"
            for key, value in sorted(payload.items())
        )

    def _summarize_tool_result(self, payload: Any) -> str:
        if isinstance(payload, dict):
            status = payload.get("status", "unknown")
            data = payload.get("data")
            result_type = None
            result_count = None
            if isinstance(data, dict):
                result_type = data.get("resultType")
                result = data.get("result")
                if isinstance(result, list):
                    result_count = len(result)
            elif isinstance(data, list):
                result_count = len(data)

            parts = [f"status={status}"]
            if result_type:
                parts.append(f"result_type={result_type}")
            if result_count is not None:
                parts.append(f"result_count={result_count}")
            if isinstance(data, dict) and "activeTargets" in data:
                active_targets = data.get("activeTargets")
                if isinstance(active_targets, list):
                    parts.append(f"active_targets={len(active_targets)}")
            return " ".join(parts)
        if isinstance(payload, list):
            return f"list_count={len(payload)}"
        return self._truncate(payload, 120)

    def _selector_metric_name(self, selector: str) -> str:
        base = selector.strip()
        if "{" in base:
            base = base.split("{", 1)[0]
        if "[" in base:
            base = base.split("[", 1)[0]
        return base

    def _query_references_known_metric(
        self,
        query: str,
        known_metric_names: set[str],
    ) -> bool:
        return any(metric_name in query for metric_name in known_metric_names)

    def _invalid_metric_usage_instruction(
        self,
        response: AIMessage,
        state: PrometheusState,
    ) -> str | None:
        known_metric_names = self._known_metric_names(state)
        if not known_metric_names:
            return None

        for tool_call in getattr(response, "tool_calls", []):
            name = tool_call.get("name")
            args = tool_call.get("args", {})
            if not isinstance(args, dict):
                continue

            if name == "prometheus_metadata":
                metric = args.get("metric")
                if (
                    isinstance(metric, str)
                    and metric
                    and metric not in known_metric_names
                ):
                    suggestions = [
                        candidate
                        for candidate in sorted(known_metric_names)
                        if metric.lower() in candidate.lower()
                    ][:8]
                    suggestion_text = (
                        " Candidate exact metrics: " + ", ".join(suggestions) + "."
                        if suggestions
                        else ""
                    )
                    return (
                        f"'{metric}' is not an exact metric name. "
                        "Use the full inventory or prometheus_metrics(search=...) to find exact metric names first."
                        + suggestion_text
                    )

            if name == "prometheus_series":
                matchers = args.get("matchers")
                if not isinstance(matchers, list):
                    continue
                invalid_matchers = [
                    matcher
                    for matcher in matchers
                    if isinstance(matcher, str)
                    and self._selector_metric_name(matcher) not in known_metric_names
                ]
                if invalid_matchers:
                    return (
                        "prometheus_series must use exact metric selectors from the inventory, not "
                        + ", ".join(repr(matcher) for matcher in invalid_matchers)
                        + "."
                    )

            if name in {"prometheus_query", "prometheus_query_range"}:
                query = args.get("query")
                if isinstance(query, str) and not self._query_references_known_metric(
                    query,
                    known_metric_names,
                ):
                    return (
                        "This PromQL query does not reference any exact metric name from the inventory. "
                        "Do not guess. Use the full inventory or prometheus_metrics(search=...) to identify exact metric names first."
                    )

        return None

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
            logger.info(
                "[SPOT] tool call name=%s payload=%s",
                tool_name,
                self._summarize_tool_payload(payload),
            )
            result = self._maybe_parse_json(await tool.ainvoke(payload or {}))
            logger.info(
                "[SPOT] tool result name=%s summary=%s",
                tool_name,
                self._summarize_tool_result(result),
            )
            return result
        except Exception:
            logger.exception("Spot failed to call tool '%s'.", tool_name)
            return None

    async def _ensure_prometheus_context(
        self,
        state: PrometheusState,
    ) -> dict[str, Any]:
        cached = state.get("prometheus_context")
        if cached:
            logger.info(
                "[SPOT] using cached Prometheus context %s",
                self._summarize_context(cached),
            )
            return cached

        logger.info("[SPOT] prefetching Prometheus discovery context")

        metrics = await self._call_tool(
            "prometheus_metrics",
            {"limit": _METRICS_INVENTORY_LIMIT},
        )

        context = {"metrics": metrics}
        state["prometheus_context"] = context
        logger.info(
            "[SPOT] Prometheus context loaded %s",
            self._summarize_context(context),
        )
        return context

    def _format_context_for_prompt(self, context: dict[str, Any]) -> str:
        if not context:
            return "\nPrometheus discovery context is currently unavailable."

        lines = ["", "Prometheus discovery context:"]

        metrics_data = context.get("metrics", {}).get("data", [])
        if isinstance(metrics_data, list) and metrics_data:
            metric_names = sorted(
                str(metric) for metric in metrics_data if isinstance(metric, str)
            )
            lines.extend(self._compact_inventory_context(metric_names))

        if len(lines) == 2:
            lines.append("- No discovery data loaded yet.")

        return "\n".join(lines)

    async def reasoner(self, state: PrometheusState):
        if self.model is None:
            raise RuntimeError(
                "Spot: model is not initialized. Call async_init() first."
            )

        logger.info(
            "[SPOT] reasoner start message_count=%s latest_user=%s",
            len(state["messages"]),
            self._truncate(self._latest_human_message(state) or "<none>", 200),
        )

        tpl = self.get_tuned_text("prompts.system") or ""
        prometheus_context = await self._ensure_prometheus_context(state)
        system_text = self.render(
            tpl + self._format_context_for_prompt(prometheus_context)
        )
        logger.info(
            "[SPOT] reasoner using context %s",
            self._summarize_context(prometheus_context),
        )

        messages = self.with_system(
            system_text,
            self.recent_messages(state["messages"], max_messages=5),
        )
        messages = await self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)
            if isinstance(response, AIMessage):
                logger.info(
                    "[SPOT] model response tool_calls=%s",
                    self._summarize_tool_calls(response),
                )
            invalid_metric_usage = None
            if isinstance(response, AIMessage):
                invalid_metric_usage = self._invalid_metric_usage_instruction(
                    response,
                    state,
                )
            if invalid_metric_usage:
                logger.warning(
                    "[SPOT] retrying because model used a non exact metric name: %s",
                    invalid_metric_usage,
                )
                response = await self.model.ainvoke(
                    messages + [HumanMessage(content=invalid_metric_usage)]
                )
                if isinstance(response, AIMessage):
                    logger.info(
                        "[SPOT] retry response tool_calls=%s",
                        self._summarize_tool_calls(response),
                    )
            if isinstance(response, AIMessage):
                logger.info(
                    "[SPOT] reasoner complete tool_calls=%s content_preview=%s",
                    self._summarize_tool_calls(response),
                    self._truncate(response.content, 200),
                )

            return {
                "messages": [response],
                "prometheus_context": prometheus_context,
            }

        except Exception:
            logger.exception("[SPOT] reasoning failure")
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
