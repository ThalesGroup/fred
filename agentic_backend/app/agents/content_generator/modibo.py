# app/core/agents/prompt_probe.py
# -----------------------------------------------------------------------------
# Fred Agent: PromptProbe (skeleton)
# Goal: expose REQUIRED prompt fields in the UI so you can edit/test them.
# Behavior: a tiny LangGraph that simply acknowledges and prints back the
# composed system prompt (and short fields) so you can verify wiring.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging

from fred_core import get_model
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, MessagesState, StateGraph

from app.common.mcp_runtime import MCPRuntime
from app.common.structures import AgentSettings
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

logger = logging.getLogger(__name__)

# Default texts (these will be visible/editable in the UI)
DEFAULT_SYSTEM = "You are PromptProbe, a minimal test agent. Keep replies brief."
DEFAULT_TASK = "Acknowledge initialization and show the active prompt knobs."
DEFAULT_STYLE = "Terse, bullet-like, no fluff."

# -----------------------------------------------------------------------------
# AgentTuning: REQUIRED prompt fields so they appear in the UI
# Keys are consistent everywhere as `system.prompt`, `task.prompt`, `style.prompt`.
# -----------------------------------------------------------------------------
TUNING: AgentTuning = AgentTuning(
    fields=[
        FieldSpec(
            key="system.prompt",
            type="prompt",
            title="System Prompt",
            description="High-level behavior (system role).",
            required=True,
            default=DEFAULT_SYSTEM,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="task.prompt",
            type="prompt",
            title="Task Prompt",
            description="What the agent is tasked to do right now.",
            required=True,
            default=DEFAULT_TASK,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="style.prompt",
            type="prompt",
            title="Style Prompt",
            description="Tone/format guidance.",
            required=True,
            default=DEFAULT_STYLE,
            ui=UIHints(group="Prompts", multiline=False, markdown=False),
        ),
    ]
)


class Modibo(AgentFlow):
    """A near-empty AgentFlow that exposes required prompt knobs.

    - `async_init()` builds a trivial chain so the agent is runnable.
    - Graph has one node that emits a short confirmation containing the
      active prompts (useful to verify live edits in the UI).
    """

    tuning = TUNING
    _system_text: str = ""

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=agent_settings,
            context_provider=lambda: self.get_runtime_context(),
        )

    def _compose_system(self) -> str:
        """Compose the final system text from tuned knobs."""
        system = self.get_tuned_text("system.prompt") or ""
        task = self.get_tuned_text("task.prompt") or ""
        style = self.get_tuned_text("style.prompt") or ""
        chat_context = self.chat_context_text()
        chat_block = (
            f"\n\nCHAT CONTEXT (context-only):\n{chat_context}" if chat_context else ""
        )
        text = self.render(
            "{system}\n\nTask: {task}\nStyle: {style}{chat}",
            system=system,
            task=task,
            style=style,
            chat=chat_block,
        )
        return text

    def _build_prompt(self) -> ChatPromptTemplate:
        # Keep _build_prompt consistent with async_init usage
        self._system_text = self._compose_system()
        return ChatPromptTemplate.from_messages([("system", self._system_text)])

    async def async_init(self):
        await self.mcp.init()

        # Build the prompts once at init. (UI edits at runtime will be pulled
        # via get_tuned_text inside _compose_system() when we rebuild.)
        self._system_text = self._compose_system()
        self.model = get_model(self.agent_settings.model)
        self._graph = self._build_graph()
        logger.info("PromptProbe initialized (prompts exposed).")

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("expert", self.node)
        builder.add_edge(START, "expert")
        builder.add_edge("expert", END)
        return builder

    async def node(self, state: MessagesState) -> MessagesState:
        # Echo the currently tuned prompts so you can see them in chat.
        sys_p = self.get_tuned_text("system.prompt") or ""
        task_p = self.get_tuned_text("task.prompt") or ""
        style_p = self.get_tuned_text("style.prompt") or ""
        msg = (
            "PromptProbe ready.\n"
            f"• system.prompt: {sys_p[:160]}{'…' if len(sys_p) > 160 else ''}\n"
            f"• task.prompt: {task_p[:160]}{'…' if len(task_p) > 160 else ''}\n"
            f"• style.prompt: {style_p[:160]}{'…' if len(style_p) > 160 else ''}"
        )
        ai = AIMessage(content=msg)
        # ✅ FIX: Return *only the new message* in a list.
        # This is the correct pattern when defining a node in LangGraph
        # that doesn't rely on the node to handle state aggregation.
        return {"messages": [ai]}
