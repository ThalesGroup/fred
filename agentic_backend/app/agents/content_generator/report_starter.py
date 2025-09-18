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

# app/core/agents/ReportStarterAgent.py
# -----------------------------------------------------------------------------
# Goal: a tiny but production-shaped agent that drafts a "Project Status Report".
# It shows exactly where to put:
#   - the typed contract (Pydantic model),
#   - the prompt (swap later for user templates),
#   - the single LangGraph node (extend later with retrieval/validators/revisions),
#   - the chat bridge (MessagesState -> AIMessage),
#   - an optional programmatic entrypoint (generate()).
#
# Keep it simple now so it’s obvious how to grow it for real use-cases.
# -----------------------------------------------------------------------------
# app/core/agents/ReportStarterAgent.py
# -----------------------------------------------------------------------------
# Goal: a tiny but production-shaped agent that drafts a "Project Status Report".
# It shows exactly where to put:
#   - the typed contract (Pydantic model),
#   - the prompt (swap later for user templates),
#   - the single LangGraph node (extend later with retrieval/validators/revisions),
#   - the chat bridge (MessagesState -> AIMessage),
#   - an optional programmatic entrypoint (generate()).
#
# Keep it simple now so it’s obvious how to grow it for real use-cases.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from fred_core import get_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field

from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 1) Typed contract (WHY: one source of truth; downstream code stays type-safe)
# ──────────────────────────────────────────────────────────────────────────────
class ProjectStatusReport(BaseModel):
    summary: str = Field(
        ..., description="Short snapshot of current project status and outcomes."
    )
    risks: str = Field(
        ..., description="Key risks or blockers (technical, schedule, resources)."
    )
    next_steps: str = Field(
        ..., description="Concrete actions planned for the next period."
    )


def _coerce_report(raw: Any) -> ProjectStatusReport:
    """Normalize dict | BaseModel | ProjectStatusReport -> ProjectStatusReport.
    WHY: `with_structured_output` may return dict or BaseModel depending on provider/version."""
    if isinstance(raw, ProjectStatusReport):
        return raw
    if isinstance(raw, BaseModel):
        return ProjectStatusReport.model_validate(raw.model_dump())
    if isinstance(raw, dict):
        return ProjectStatusReport.model_validate(raw)
    raise TypeError(f"Unsupported structured output type: {type(raw)}")


def _to_markdown(r: ProjectStatusReport) -> str:
    """Single place to render for the UI/exporters."""
    return (
        "# Project Status Report\n\n"
        "## Summary\n"
        f"{r.summary}\n\n"
        "## Risks\n"
        f"{r.risks}\n\n"
        "## Next Steps\n"
        f"{r.next_steps}\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2) Prompt (WHY: clear intent; drop-in replacement for user templates later)
# ──────────────────────────────────────────────────────────────────────────────
def _build_prompt() -> ChatPromptTemplate:
    # Keep it minimal, factual, concise → good defaults for status docs.
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a concise, factual project reporter. Avoid fluff. Use short paragraphs.",
            ),
            (
                "human",
                "Create a Project Status Report with three sections: summary, risks, next_steps.\n"
                "Project: {project}\n"
                "Period: {period}\n"
                "Context (free text from user): {context}",
            ),
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3) Chat bridge (WHY: chat sends free text; we need slots for the prompt)
#    Minimal approach: treat the last human message as 'context'. Defaults handle blanks.
#    Replace later with: UI form, slot-filler node, or a dedicated 'template loader' tool.
# ──────────────────────────────────────────────────────────────────────────────
def _extract_slots(messages: Sequence[BaseMessage]) -> Dict[str, str]:
    ctx = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage) and isinstance(m.content, str):
            ctx = m.content.strip()
            break
    return {"project": "Untitled Project", "period": "Current Period", "context": ctx}


# ──────────────────────────────────────────────────────────────────────────────
# 4) The Agent (WHY: single-node LangGraph → trivially extensible later)
#
# Example prompts you can type in chat to see this agent work:
#   1. Minimal free text:
#      "Project Phoenix is on track overall. Prototype delivered, database unstable.
#       Next sprint focus: performance tests."
#
#   2. Short, structured:
#      "Status for Project Orion: velocity dropping, vendor API is a blocker,
#       adding 2 developers next month."
#
#   3. Emphasize risks:
#      "Migration to cloud. Risk: unexpected costs and lack of skills.
#       Next: training program."
#
#   4. Emphasize achievements:
#      "Project Aurora: Integration tests passed. Minor bugs left.
#       Next sprint: deploy to staging."
#
#   5. Narrative style:
#      "Project Neptune: finished UI redesign, better feedback scores.
#       Risk: backend under load. Next: A/B test + infra scaling."
#
# Each input → agent forces answer into 3 sections: Summary, Risks, Next Steps.
# ──────────────────────────────────────────────────────────────────────────────
class ReportStarter(AgentFlow):
    """
    Hover-notes for new devs:
    - In Fred, an Agent is a small LangGraph + lifecycle. One node today; add more later.
    - We return BOTH: a human-friendly Markdown message (for chat) and
      a machine-friendly JSON copy in `additional_kwargs` (for exports/revisions).
    """

    name: str = "ReportStarter"
    nickname: str = "Scribo"
    role: str = "Generates a simple Project Status Report"
    description: str = (
        "Drafts a status report (summary, risks, next steps) as structured output."
    )
    icon: str = "report"
    categories = ["Reports"]
    tag: str = "report-starter"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self._graph: Optional[StateGraph] = None
        self._chain: Optional[Runnable] = None

    async def async_init(self):
        """
        WHY async: model factories may perform I/O (OpenAI/Azure/Ollama). Keep __init__ pure.
        Build the LCEL chain + the uncompiled graph.
        """
        model = get_model(self.agent_settings.model)
        self._chain = _build_prompt() | model.with_structured_output(
            ProjectStatusReport
        )

        def draft_node(state: MessagesState) -> MessagesState:
            # Single responsibility: turn "chat message(s)" into a typed report + markdown reply.
            assert self._chain is not None, "Agent not initialized."
            slots = _extract_slots(state["messages"])
            raw = self._chain.invoke(slots)
            report = _coerce_report(raw)
            md = _to_markdown(report)

            # Append one assistant message (Markdown for humans, JSON in metadata for machines).
            ai = AIMessage(
                content=md,
                additional_kwargs={
                    "fred": {"project_status_report": report.model_dump()}
                },
            )
            return {"messages": [*state["messages"], ai]}

        g = StateGraph(MessagesState)
        g.add_node("draft", draft_node)
        g.add_edge(START, "draft")
        g.add_edge("draft", END)

        self._graph = g
        logger.info(
            "ReportStarter initialized (MessagesState; uncompiled graph ready)."
        )

    # Optional programmatic entry-point (useful in tests or non-chat flows)
    async def generate(
        self, *, project: str, period: str = "Current Period", context: str = ""
    ) -> ProjectStatusReport:
        """Explicit inputs → typed report. Bypasses chat, returns the Pydantic object."""
        assert self._chain is not None, "Call async_init() first."
        raw = self._chain.invoke(
            {"project": project, "period": period, "context": context}
        )
        return _coerce_report(raw)

    @staticmethod
    def to_markdown(report: ProjectStatusReport) -> str:
        return _to_markdown(report)
