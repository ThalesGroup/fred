# agentic_backend/core/agents/report_writer.py
# -----------------------------------------------------------------------------
# Fred Agent: ReportWriter
# Architecture notes (hover-friendly):
# - Single-node LangGraph: chat → structured report.
# - Tunables (persona/contract/behavior, style, CIR) exposed via AgentTuning.
# - System prompt is injected explicitly with AgentFlow.with_system() at the node.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 1) Structured output contract (WHY: downstream tools can consume JSON safely)
# ──────────────────────────────────────────────────────────────────────────────
class ProjectStatusReport(BaseModel):
    summary: str = Field(..., description="Snapshot of project status and outcomes.")
    risks: str = Field(..., description="Key risks or blockers.")
    next_steps: str = Field(..., description="Concrete actions for the next period.")

    # CIR hooks (optional today; visible for future evolution)
    cir_research_activities: Optional[str] = Field(
        None, description="(CIR) Activities with novelty/uncertainty, methods."
    )
    cir_outputs: Optional[str] = Field(
        None,
        description="(CIR) Tangible outputs: prototypes, PoCs, datasets, publications.",
    )
    cir_impact: Optional[str] = Field(
        None, description="(CIR) Expected impact: advances, IP, ROI signals."
    )


def _coerce_report(raw: Any) -> ProjectStatusReport:
    """Accept dict/BaseModel and normalize to our Pydantic type."""
    if isinstance(raw, ProjectStatusReport):
        return raw
    if isinstance(raw, BaseModel):
        return ProjectStatusReport.model_validate(raw.model_dump())
    if isinstance(raw, dict):
        return ProjectStatusReport.model_validate(raw)
    raise TypeError(f"Unsupported structured output type: {type(raw)}")


def _to_markdown(r: ProjectStatusReport, *, show_cir: bool) -> str:
    """Single rendering point (WHY: UI/exporters stay consistent)."""
    parts = [
        "# Project Status Report",
        "## Summary",
        r.summary,
        "## Risks",
        r.risks,
        "## Next Steps",
        r.next_steps,
    ]
    if show_cir:
        if r.cir_research_activities:
            parts += ["## CIR — Research Activities", r.cir_research_activities]
        if r.cir_outputs:
            parts += ["## CIR — Research Outputs", r.cir_outputs]
        if r.cir_impact:
            parts += ["## CIR — Expected Impact", r.cir_impact]
    return "\n\n".join(parts) + "\n"


# ──────────────────────────────────────────────────────────────────────────────
# 2) Tuning schema (WHY: the UI surfaces *why* knobs, not just raw fields)
# ──────────────────────────────────────────────────────────────────────────────
PERSONA_PROMPT = (
    "You are a concise, factual project reporter for management consumption. "
    "Prefer short, informative paragraphs over prose."
)

CONTRACT_PROMPT = (
    "Always produce a report with these sections: summary, risks, next_steps. "
    "When CIR mode is enabled, also produce: cir_research_activities, cir_outputs, cir_impact. "
    "Keep each section self-contained and actionable."
)

BEHAVIOR_PROMPT = (
    "Ask clarifying questions when critical information is missing. "
    "If risks are absent, say 'No major risks identified'. "
    "Never invent facts; keep assumptions explicit."
)

TUNING: AgentTuning = AgentTuning(
    role="report_writer",
    description="An agent that generates structured project status reports based on provided context.",
    fields=[
        # --- Prompt segments ---------------------------------------------------
        FieldSpec(
            key="prompts.persona",
            type="prompt",
            title="Agent Persona",
            description="Defines the voice/identity of the reporter.",
            required=True,
            default=PERSONA_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.contract",
            type="prompt",
            title="Report Contract",
            description="Mandatory sections and structural guarantees (incl. CIR).",
            required=True,
            default=CONTRACT_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.behavior",
            type="prompt",
            title="Behavioral Rules",
            description="Fallbacks and guardrails (questions, honesty, brevity).",
            required=True,
            default=BEHAVIOR_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        # --- Style knobs -------------------------------------------------------
        FieldSpec(
            key="style.max_paragraphs",
            type="number",
            title="Max paragraphs per section",
            description="Hard budget that forces prioritization (management-friendly).",
            required=False,
            default=2,
            min=1,
            max=6,
            ui=UIHints(group="Advanced"),
        ),
        FieldSpec(
            key="style.brevity",
            type="number",
            title="Brevity (0.0–1.0)",
            description="Higher → more compression; lower → more detail.",
            required=False,
            default=0.7,
            min=0.0,
            max=1.0,
            ui=UIHints(group="Advanced"),
        ),
        # --- CIR toggle --------------------------------------------------------
        FieldSpec(
            key="output.enable_cir",
            type="boolean",
            title="Enable CIR sections",
            description="Adds CIR sections (activities/outputs/impact) to the report.",
            required=False,
            default=False,
            ui=UIHints(group="Advanced"),
        ),
    ],
)


# ──────────────────────────────────────────────────────────────────────────────
# 3) Prompt builder
#    Returns ONLY the ChatPromptTemplate. Stores the system text on the agent.
#    WHY: avoids tuple typing and keeps a simple function contract.
# ──────────────────────────────────────────────────────────────────────────────
async def _build_prompt(agent: AgentFlow) -> ChatPromptTemplate:
    persona = agent.get_tuned_text("prompts.persona") or ""
    contract = agent.get_tuned_text("prompts.contract") or ""
    behavior = agent.get_tuned_text("prompts.behavior") or ""

    chat_context = await agent.chat_context_text()
    chat_context_block = (
        f"\n\nCHAT CONTEXT (context-only):\n{chat_context}" if chat_context else ""
    )

    # Safe token rendering; unknown tokens remain literal.
    system_text = agent.render(
        "{persona}\n\n{contract}\n\n{behavior}\n\nToday: {today}" + chat_context_block,
        persona=persona,
        contract=contract,
        behavior=behavior,
    )

    # Store for later explicit injection at the node.
    agent._system_text = system_text  # type: ignore[attr-defined]

    return ChatPromptTemplate.from_messages(
        [
            (
                "human",
                "Create a Project Status Report.\n"
                "Project: {project}\n"
                "Period: {period}\n"
                "Context: {context}\n",
            )
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4) Slot extraction (chat → prompt vars; replace later with a UI form)
# ──────────────────────────────────────────────────────────────────────────────
def _extract_slots(messages: Sequence[BaseMessage]) -> Dict[str, str]:
    ctx = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage) and isinstance(m.content, str):
            ctx = m.content.strip()
            break
    return {"project": "Untitled Project", "period": "Current Period", "context": ctx}


# ──────────────────────────────────────────────────────────────────────────────
# 5) The Agent
# ──────────────────────────────────────────────────────────────────────────────
class ReportWriter(AgentFlow):
    """
    WHY this class exists:
    - Demonstrates using AgentFlow facilities (tuning readers, explicit system injection,
      safe template rendering, compiled graph lifecycle).
    - CIR sections are controlled by a single boolean tuning field.
    """

    tuning = TUNING
    _system_text = ""

    async def async_init(self):
        """
        WHY async: model factories may allocate network clients (OpenAI/Azure/Ollama).
        Build the graph here, then controllers call get_compiled_graph() to run.
        """
        # 1) Build prompt and capture system text via _build_prompt()
        prompt = await _build_prompt(self)

        # 2) Bind model with structured output (type-safe contract)
        model = get_default_chat_model()
        self._chain = prompt | model.with_structured_output(ProjectStatusReport)

        # 3) Single-node LangGraph
        def draft_node(state: MessagesState) -> MessagesState:
            assert self._chain is not None, "Agent not initialized."

            # Inject tuned system prompt explicitly at the node boundary.
            messages = self.with_system(self._system_text, state["messages"])
            slots = _extract_slots(messages)

            raw = self._chain.invoke(slots)
            report = _coerce_report(raw)

            # Style knobs (kept for future revision nodes)
            max_paras = self.get_tuned_int(
                "style.max_paragraphs", default=2, min_value=1, max_value=6
            )
            brevity = self.get_tuned_number(
                "style.brevity", default=0.7, min_value=0.0, max_value=1.0
            )
            enable_cir = bool(self.get_tuned_any("output.enable_cir") or False)

            md = _to_markdown(report, show_cir=enable_cir)

            ai = AIMessage(
                content=md,
                additional_kwargs={
                    "fred": {
                        "project_status_report": report.model_dump(),
                        "style": {
                            "max_paragraphs": max_paras,
                            "brevity": brevity,
                            "enable_cir": enable_cir,
                        },
                    }
                },
            )
            return {"messages": [*state["messages"], ai]}

        g = StateGraph(MessagesState)
        g.add_node("draft", draft_node)
        g.add_edge(START, "draft")
        g.add_edge("draft", END)
        self._graph = g
        logger.info("ReportWriter initialized (uncompiled graph ready).")

    # Optional programmatic entry-point (non-chat usage)
    async def generate(
        self, *, project: str, period: str = "Current Period", context: str = ""
    ) -> ProjectStatusReport:
        """Tests or batch jobs can bypass chat and request the typed object directly."""
        assert self._chain is not None, "Call async_init() first."
        raw = self._chain.invoke(
            {"project": project, "period": period, "context": context}
        )
        return _coerce_report(raw)
