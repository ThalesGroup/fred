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
from typing import Any, Type

try:
    from langchain.agents import create_agent
except Exception:  # pragma: no cover - runtime/version compatibility fallback
    create_agent = None

from langgraph.graph import END, MessagesState
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, interrupt

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.structural_graph_builder import (
    StructuralConditional,
    StructuralEdge,
    StructuralGraphSpec,
    build_structural_state_graph,
)
from agentic_backend.core.interrupts.tool_approval import (
    is_truthy as _is_truthy_hitl,
)
from agentic_backend.core.interrupts.tool_approval import (
    parse_approval_required_tools,
    requires_tool_approval,
    tool_approval_policy_text,
    tool_approval_tuning_fields,
    tool_approval_ui_payload,
)
from agentic_backend.core.prompts import append_mermaid_rendering_policy
from agentic_backend.core.runtime_source import expose_runtime_source
from agentic_backend.core.tools.tool_loop import build_tool_loop

logger = logging.getLogger(__name__)

# Append citation guidance only when document-search tools are available.
_CITATION_POLICY = (
    "\n\n"
    "Citations for document search tools:\n"
    "- If a tool returns document search results (vector hits with title/content/rank), "
    "cite sources with bracketed numbers like [1], [2]. Use the hit rank when available; "
    "otherwise use list order.\n"
    "- If multiple sources support a statement, include multiple citations (e.g., [1][3])."
)

_NO_TOOLS_POLICY = (
    "\n\n"
    "Tool availability:\n"
    "- No external tool is available in this session.\n"
    "- Do NOT claim you searched the web, queried a database, or called any tool.\n"
    "- Do NOT write fake tool markers such as [web search], [tool], or similar.\n"
    "- Answer normally without repeating capability disclaimers.\n"
    "- Mention the limitation only when the user's request explicitly requires unavailable external lookup.\n"
    "- When needed, keep that limitation note short and only once in the answer."
)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
BASIC_REACT_TUNING = AgentTuning(
    role="Define here the high-level role of the MCP agent.",
    description="Define here a detailed description of the MCP agent's purpose and behavior.",
    tags=[],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "High-level instructions for the agent. "
                "State the mission, how to use the available tools, and constraints."
            ),
            required=True,
            default=(
                "You are a general assistant with tools. Use the available instructions and tools to solve the user's request.\n"
                "If tools are available:\n"
                "- Use only the tools that are explicitly available in this session.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- Never claim any tool result that was not actually returned by a tool call.\n"
                "- When a tool returns document search results (vector hits with title/content/rank), cite sources with\n"
                "  bracketed numbers like [1], [2]. Use the hit rank when available; otherwise use list order.\n"
                "- If multiple sources support a statement, include multiple citations (e.g., [1][3]).\n"
                "If no tool is available:\n"
                "- Answer directly without proactive capability disclaimers.\n"
                "- Only mention missing external lookup capability when it is strictly necessary for the request.\n"
                "- Never mention fake tools such as [web search].\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Show file upload/attachment controls for this agent.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document libraries picker",
            description="Let users select document libraries/knowledge sources for this agent.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        *tool_approval_tuning_fields(),
        # FieldSpec(
        #     key="chat_options.search_policy_selection",
        #     type="boolean",
        #     title="Search policy selector",
        #     description="Expose the search policy toggle (hybrid/semantic/strict).",
        #     required=False,
        #     default=False,
        #     ui=UIHints(group="Chat options"),
        # ),
        # FieldSpec(
        #     key="chat_options.search_rag_scoping",
        #     type="boolean",
        #     title="RAG scope selector",
        #     description="Expose the RAG scope control (documents-only vs hybrid vs knowledge).",
        #     required=False,
        #     default=False,
        #     ui=UIHints(group="Chat options"),
        # ),
        # FieldSpec(
        #     key="chat_options.deep_search_delegate",
        #     type="boolean",
        #     title="Deep search delegate toggle",
        #     description="Allow delegation to a senior agent for deep search.",
        #     required=False,
        #     default=False,
        #     ui=UIHints(group="Chat options"),
        # ),
    ],
)


@expose_runtime_source("agent.BasicReActAgent")
class BasicReActAgent(AgentFlow):
    """Simple ReAct agent used for dynamic UI-created agents."""

    tuning = BASIC_REACT_TUNING
    mcp: MCPRuntime | None = None
    default_chat_options = AgentChatOptions(
        search_policy_selection=False,
        libraries_selection=False,
        search_rag_scoping=False,
        deep_search_delegate=False,
        attach_files=False,
    )

    def build_runtime_structure(self) -> None:
        if self._tool_approval_enabled():
            spec = StructuralGraphSpec(
                state_schema=MessagesState,
                nodes=("reasoner", "approval", "tools"),
                start_node="reasoner",
                edges=(StructuralEdge(source="tools", target="reasoner"),),
                conditionals=(
                    StructuralConditional(
                        source="reasoner",
                        routes={
                            "final": END,
                            "approval": "approval",
                        },
                        default_choice="final",
                    ),
                    StructuralConditional(
                        source="approval",
                        routes={
                            "cancel": END,
                            "approve": "tools",
                        },
                        default_choice="cancel",
                    ),
                ),
            )
        else:
            spec = StructuralGraphSpec(
                state_schema=MessagesState,
                nodes=("reasoner", "tools"),
                start_node="reasoner",
                edges=(StructuralEdge(source="tools", target="reasoner"),),
                conditionals=(
                    StructuralConditional(
                        source="reasoner",
                        routes={
                            "final": END,
                            "tools": "tools",
                        },
                        default_choice="final",
                    ),
                ),
            )

        self._graph = build_structural_state_graph(
            spec=spec,
            owner_name=type(self).__name__,
        )

    async def activate_runtime(self) -> None:
        # Initialize MCP runtime
        self.mcp = MCPRuntime(
            agent=self,
        )
        await self.mcp.init()

    async def aclose(self):
        if self.mcp is not None:
            await self.mcp.aclose()

    def get_state_schema(self) -> Type:
        """Minimal state schema for LangGraph/Temporal hydration compatibility."""
        return MessagesState

    def get_graph_mermaid_preview(self) -> str:
        """
        Return a compact conceptual graph for UI inspection without requiring MCP init.
        The compiled LangGraph for create_agent() is verbose and may require runtime tools.
        """
        if self._tool_approval_enabled():
            return (
                "flowchart TD;\n"
                "User([User message]) --> Reasoner[LLM reasoner];\n"
                "Reasoner --> Decision{Tool needed?};\n"
                "Decision -->|No| Final[Final response];\n"
                "Decision -->|Yes| Approval{HITL approval required?};\n"
                "Approval -->|Cancel| Final;\n"
                "Approval -->|Approve| Tools[(MCP tools)];\n"
                "Tools --> Reasoner;\n"
            )
        return (
            "flowchart TD;\n"
            "User([User message]) --> Reasoner[LLM reasoner];\n"
            "Reasoner --> Decision{Tool needed?};\n"
            "Decision -->|No| Final[Final response];\n"
            "Decision -->|Yes| Tools[(MCP tools)];\n"
            "Tools --> Reasoner;\n"
        )

    def _build_system_prompt(self, tools: list[Any]) -> str:
        base_prompt = self.render(self.get_tuned_text("prompts.system") or "")
        base_prompt = append_mermaid_rendering_policy(
            base_prompt,
            language=getattr(getattr(self, "runtime_context", None), "language", None),
        )
        tool_names = [tool.name for tool in tools]

        if tool_names:
            listed_tools = "\n".join(f"- {name}" for name in tool_names)
            tool_policy = (
                "\n\n"
                "Available tools (exact names):\n"
                f"{listed_tools}\n"
                "Rules:\n"
                "- You may only call tools listed above.\n"
                "- Never invent tool names.\n"
                "- Never present tool output unless a tool actually returned it."
            )
            system_prompt = f"{base_prompt}{tool_policy}{_CITATION_POLICY}"
            if self._tool_approval_enabled():
                system_prompt = f"{system_prompt}{self._hitl_policy_text()}"
            return system_prompt
        return f"{base_prompt}{_NO_TOOLS_POLICY}"

    @staticmethod
    def _dedupe_tools_by_name(tools: list[Any]) -> list[Any]:
        deduped: list[Any] = []
        seen: set[str] = set()
        for tool in tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
            if not isinstance(name, str):
                deduped.append(tool)
                continue
            if name in seen:
                logger.warning(
                    "[BasicReActAgent] Duplicate tool name ignored: %s", name
                )
                continue
            seen.add(name)
            deduped.append(tool)
        return deduped

    def _hitl_policy_text(self) -> str:
        return tool_approval_policy_text(self)

    def _hitl_ui_text(self, tool_name: str) -> dict[str, Any]:
        return tool_approval_ui_payload(self, tool_name)

    def _tool_approval_enabled(self) -> bool:
        raw = self.get_tuned_any("safety.enable_tool_approval")
        return _is_truthy_hitl(raw)

    def _configured_approval_required_tools(self) -> set[str]:
        raw = self.get_tuned_any("safety.approval_required_tools")
        return parse_approval_required_tools(raw)

    def _requires_tool_approval(self, tool_name: str) -> bool:
        return requires_tool_approval(
            tool_name,
            approval_enabled=self._tool_approval_enabled(),
            exact_required_tools=self._configured_approval_required_tools(),
        )

    @staticmethod
    def _truncate_for_hitl(value: Any, max_chars: int = 1200) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
        return text if len(text) <= max_chars else text[: max_chars - 3] + "..."

    def _build_hitl_react_graph(self, *, system_prompt: str, tools: list[Any]):
        bound_model = get_default_chat_model().bind_tools(tools)

        def system_builder(_: MessagesState) -> str:
            return system_prompt

        def requires_hitl(tool_name: str) -> bool:
            return self._requires_tool_approval(tool_name)

        async def hitl_callback(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
            payload = self._hitl_ui_text(tool_name)
            decision = interrupt(
                {
                    **payload,
                    "free_text": True,
                    "metadata": {
                        "tool_name": tool_name,
                        "tool_args_preview": self._truncate_for_hitl(args),
                    },
                }
            )

            choice = None
            if isinstance(decision, dict):
                choice = decision.get("choice_id") or decision.get("answer")
            if isinstance(choice, str) and choice.strip().lower() == "cancel":
                return {"cancel": True}
            return {}

        return build_tool_loop(
            model=bound_model,
            tools=tools,
            system_builder=system_builder,
            requires_hitl=requires_hitl,
            hitl_callback=hitl_callback,
        )

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        if self.mcp is None:
            raise RuntimeError(
                f"{type(self).__name__}: runtime not activated (MCPRuntime unavailable)."
            )
        tools = self._dedupe_tools_by_name(self.mcp.get_tools())
        system_prompt = self._build_system_prompt(tools)

        if self._tool_approval_enabled():
            logger.info(
                "[BasicReActAgent] HITL tool approval enabled for agent=%s",
                self.get_id(),
            )
            graph = self._build_hitl_react_graph(
                system_prompt=system_prompt, tools=tools
            )
            return graph.compile(checkpointer=checkpointer)

        if create_agent is None:
            logger.warning(
                "[BasicReActAgent] langchain.agents.create_agent unavailable; "
                "falling back to internal tool loop without HITL gating"
            )
            graph = self._build_hitl_react_graph(
                system_prompt=system_prompt, tools=tools
            )
            return graph.compile(checkpointer=checkpointer)

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=system_prompt,
            tools=tools,
            checkpointer=checkpointer,
        )
