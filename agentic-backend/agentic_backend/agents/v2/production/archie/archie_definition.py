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

"""
Archie v2 — production RAG graph agent (Thales RAO domain).

Workflow:
  retrieve → score_filter → answer

Tunable fields (visible in the settings UI):
  - system_prompt       : agent policy and tone (Prompts group)
  - with_sources_prompt : template when sources are available (Prompts group)
  - no_sources_prompt   : template when no sources are found (Prompts group)
  - top_k               : number of chunks to retrieve (Retrieval group)
  - min_score           : minimum relevance score filter (Retrieval group)

At workflow start, build_initial_state injects the current field values into
ArchieState so every step reads from state — prompts are tunable without any
code change.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import ToolRefRequirement
from agentic_backend.core.agents.v2.contracts.context import BoundRuntimeContext
from agentic_backend.core.agents.v2.graph.authoring import (
    GraphAgent,
    GraphWorkflow,
)

from .archie_state import ArchieInput, ArchieState
from .archie_steps import (
    answer_step,
    retrieve_step,
    score_filter_step,
)
from .prompt_loader import load_archie_prompt

# ── Default prompt text (loaded from prompts/ markdown files) ──────────────────
_DEFAULT_SYSTEM_PROMPT = load_archie_prompt("archie_system_prompt.md")
_DEFAULT_WITH_SOURCES_PROMPT = load_archie_prompt("archie_with_sources_prompt.md")
_DEFAULT_NO_SOURCES_PROMPT = load_archie_prompt("archie_no_sources_prompt.md")


class ArchieV2Definition(GraphAgent):
    """
    Archie v2 — RAG expert for Thales RAO domain.

    Retrieves relevant document chunks via the knowledge.search built-in tool,
    applies a score filter, and synthesises a grounded answer.

    All session-scoping (library selection, search policy, attached files,
    team / owner filter) is injected automatically by the runtime adapter.
    Prompt text and retrieval knobs are editable from the settings UI.
    """

    agent_id: str = "production.archie.rag.v2"
    role: str = "Expert RAO Thales"
    description: str = (
        "Agent RAG expert pour les réponses aux appels d'offres Thales. "
        "Archie analyse, sélectionne et synthétise les informations issues des "
        "documents techniques, administratifs et méthodologiques."
    )
    tags: tuple[str, ...] = ("rag", "graph", "production", "archie", "v2", "french")

    # ── Tunable model fields (values persisted in AgentSettings.tuning.fields) ─
    system_prompt: str = Field(default=_DEFAULT_SYSTEM_PROMPT)
    with_sources_prompt: str = Field(default=_DEFAULT_WITH_SOURCES_PROMPT)
    no_sources_prompt: str = Field(default=_DEFAULT_NO_SOURCES_PROMPT)
    top_k: int = Field(default=8)
    min_score: float = Field(default=0.6)

    # ── FieldSpec declarations (drives the settings UI) ────────────────────────
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt",
            type="prompt",
            title="System Prompt",
            description="Agent policy and tone. Applied to every response.",
            required=True,
            default=_DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="with_sources_prompt",
            type="prompt",
            title="Réponse avec sources",
            description="Template quand des sources sont disponibles. Utiliser {question} et {sources}.",
            required=True,
            default=_DEFAULT_WITH_SOURCES_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="no_sources_prompt",
            type="prompt",
            title="Réponse sans sources",
            description="Template quand aucune source pertinente n'est trouvée. Utiliser {question}.",
            required=True,
            default=_DEFAULT_NO_SOURCES_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="top_k",
            type="integer",
            title="Top-K Documents",
            description="How many chunks to retrieve per question.",
            required=False,
            default=8,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="min_score",
            type="number",
            title="Minimum Score (filter)",
            description="Filter out retrieved chunks below this relevance score (0 to disable).",
            required=False,
            default=0.6,
            ui=UIHints(group="Retrieval"),
        ),
    )

    # ── Declared tool refs (gates invoke_tool calls at runtime) ──────────────
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref="knowledge.search",
            description="Retrieve relevant document chunks from the selected libraries.",
        ),
    )

    input_schema = ArchieInput
    state_schema = ArchieState
    input_to_state = {"message": "question"}
    output_state_field = "final_text"

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> ArchieState:
        """
        Inject tunable field values from the definition into the initial state.

        Calls the base implementation first (handles input_to_state mapping),
        then overlays the current definition field values for prompts and
        retrieval config. This is how persisted settings flow into the graph:
        AgentSettings.tuning.fields → build_definition_from_settings → here → state.
        """
        base = super().build_initial_state(input_model, binding)
        return ArchieState.model_validate(
            base.model_dump()
            | {
                "system_prompt": self.system_prompt,
                "with_sources_prompt": self.with_sources_prompt,
                "no_sources_prompt": self.no_sources_prompt,
                "top_k": self.top_k,
                "min_score": self.min_score,
            }
        )

    workflow = GraphWorkflow(
        entry="retrieve",
        nodes={
            "retrieve": retrieve_step,
            "score_filter": score_filter_step,
            "answer": answer_step,
        },
        edges={
            "retrieve": "score_filter",
            "score_filter": "answer",
        },
    )
