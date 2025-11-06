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
from langgraph.prebuilt import ToolNode, tools_condition

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
MCP_TUNING = AgentTuning(
    role="Define here the high-level role of the MCP agent.",
    description="Define here a detailed description of the MCP agent's purpose and behavior.",
    tags=["mcp"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "High-level instructions for the MCP agent. "
                "State the mission, how to use the available tools, and constraints."
            ),
            required=True,
            default=(
                "You are an MCP-enabled assistant. Use the available MCP tools to solve the user's request:\n"
                "- ALWAYS use the tools at your disposal before providing any answer.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- When you reference tool results, keep short inline markers (e.g., [tool_name]).\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class MCPAgent(AgentFlow):
    """
    Dynamically-created agent that uses MCP-based tools.
    Pattern alignment with AgentFlow:
    - Class-level `tuning` (spec only; values come from YAML/DB/UI)
    - async_init(): set model, init MCP, bind tools, build graph
    - Nodes opt-in to prepend tuned prompt (no global magic)
    """

    tuning = MCP_TUNING

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)
        # Initialize MCP runtime and bind tools to the model.
        self.mcp = MCPRuntime(
            agent=self,
        )
        self.model = get_default_chat_model()
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def aclose(self):
        await self.mcp.aclose()

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        if self.mcp.toolkit is None:
            raise RuntimeError(
                "MCPAgent: toolkit must be initialized before building the graph."
            )

        builder = StateGraph(MessagesState)

        # LLM node
        builder.add_node("reasoner", self.reasoner)
        tools = self.mcp.get_tools()
        # Configure tool node to surface human-readable errors to the user instead of raising
        def _friendly_tool_error(e: Exception) -> str:
            # Try to identify common connection/timeout errors from MCP HTTP client stack
            try:
                import httpx  # type: ignore
                import httpcore  # type: ignore
            except Exception:  # pragma: no cover - best effort import
                httpx = None  # type: ignore
                httpcore = None  # type: ignore

            conn_like = (
                ConnectionError,
                TimeoutError,
            )
            if httpx is not None:
                conn_like = conn_like + (
                    getattr(httpx, "ConnectError", Exception),
                    getattr(httpx, "ReadTimeout", Exception),
                    getattr(httpx, "WriteTimeout", Exception),
                    getattr(httpx, "PoolTimeout", Exception),
                )
            if httpcore is not None:
                conn_like = conn_like + (
                    getattr(httpcore, "ConnectError", Exception),
                )

            # Connection or timeout to MCP server → clear human message
            if isinstance(e, conn_like):
                return (
                    "The MCP server appears unreachable. Please ensure it is running "
                    "and accessible, then try again."
                )

            # Generic tool failure fallback (short, user-friendly)
            return (
                "A tool error occurred while using the MCP integration. "
                "Please try again or contact support if it persists."
            )

        tool_node = ToolNode(tools=tools, handle_tool_errors=_friendly_tool_error)
        builder.add_node("tools", tool_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges(
            "reasoner", tools_condition
        )  # → "tools" when tool calls are requested
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def reasoner(self, state: MessagesState):
        """
        One LLM step; the model may decide to call MCP tools.
        After tool calls, collect ToolMessages and surface their outputs for the UI.
        """
        if self.model is None:
            raise RuntimeError(
                "MCPAgent: model is not initialized. Call async_init() first."
            )

        # 1) Build the system prompt from tuning and render tokens (e.g., {today})
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)

        # 2) Ask the model (prepend a single SystemMessage)
        messages = self.with_system(system_text, state["messages"])
        messages = self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)

            # 3) Harvest tool outputs from ToolMessages → attach to response metadata for the UI
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    normalized: Any = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw  # keep raw string if not JSON
                    if msg.name is not None:
                        tool_payloads[msg.name] = normalized

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
            logger.exception("MCPAgent: unexpected error during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content=(
                            "Sorry, I hit an unexpected error while reasoning. "
                            "Please try again. If it persists, ensure any required "
                            "external tools (MCP servers) are running."
                        )
                    )
                ]
            )
            return {"messages": [fallback]}
