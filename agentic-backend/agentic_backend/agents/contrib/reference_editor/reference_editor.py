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

"""Reference Editor Agent for generating reference PowerPoint and Word documents."""

from __future__ import annotations

import logging

from fred_core import OwnerFilter
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.agents.reference_editor.export_tools import ExportTools
from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_document_library_tags_ids,
    get_document_uids,
    get_vector_search_scopes,
)
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


@expose_runtime_source("agent.ReferenceEditor")
class ReferenceEditor(AgentFlow):
    """Agent that generates reference PowerPoint and Word documents from extracted data."""

    tuning = AgentTuning(
        role="Reference Editor",
        description="Extracts information from reference powerpoint to fill another given reference PowerPoint template.",
        mcp_servers=[MCPServerRef(id="mcp-knowledge-flow-mcp-text")],
        tags=["document", "powerpoint", "reference"],
        fields=[
            FieldSpec(
                key="ppt.template_key",
                type="text",
                title="PowerPoint Template Key",
                description="Agent asset key for the .pptx template.",
                ui=UIHints(group="PowerPoint"),
                default="ref_template.pptx",
            ),
            FieldSpec(
                key="word.template_key",
                type="text",
                title="Word Template Key",
                description="Agent asset key for the .docx template.",
                ui=UIHints(group="Word"),
                default="ref_template.docx",
            ),
            FieldSpec(
                key="prompts.system",
                type="prompt",
                title="System Prompt",
                description=(
                    "High-level instructions for the agent. "
                    "State the mission, how to use the available tools, and constraints."
                ),
                required=True,
                default="""Tu es un agent spécialisé dans l'extraction d'informations structurées depuis des documents de référence pour remplir un template PowerPoint ou Word standardisé.

# MISSION

Extraire des informations depuis des documents (via recherche RAG) et générer un document en utilisant un template prédéfini.

# OUTILS DISPONIBLES

1. **Outils de recherche RAG** (via MCP mcp-knowledge-flow-mcp-text)
   - Utilise-les pour extraire des informations depuis les documents
   - Paramètres recommandés : top_k=5, search_policy='semantic'
   - Ne pas utiliser document_library_tags_ids

2. **ppt_template_tool(data: dict)** — Génère le PowerPoint templatisé. Utilisé par défaut.

3. **word_template_tool(data: dict)** — Génère un document Word templatisé. N'utilise cet outil QUE si l'utilisateur demande EXPLICITEMENT un document Word.

Les outils de génération valident automatiquement les données et retournent les erreurs le cas échéant. En cas d'erreur, corrige les données et rappelle l'outil.

# RÈGLES D'EXTRACTION

- Extrais UNIQUEMENT les informations présentes dans les documents via recherche RAG
- Si une information n'existe pas après recherche : laisse le champ vide ("")
- JAMAIS d'invention ou d'approximation
- Respecte les contraintes de longueur (maxLength). Si une information dépasse, résume en gardant l'essentiel
- Pour "listeTechnologies", liste les noms séparés par des virgules (ex: "Nvidia, Apple, AWS"). Le système cherchera automatiquement les logos correspondants

# WORKFLOW

## Étape 1 : Extraction des informations
Effectue des recherches RAG ciblées pour couvrir toutes les sections :
- Informations projet (nom société, nom projet, dates, ressources, enjeux financiers)
- Contexte (présentation client, contexte projet, technologies)
- Synthèse (enjeux, activités/solutions, bénéfices clients, points forts)

Si l'utilisateur fournit des informations complémentaires, intègre-les.

## Étape 2 : Génération du document
Appelle l'outil de génération approprié (ppt_template_tool par défaut, word_template_tool si demandé) avec les données collectées. Ne montre jamais le JSON brut à l'utilisateur.

## Étape 3 : Restitution à l'utilisateur
Résume simplement ce qui a été extrait et les champs manquants.

# MISE À JOUR DU DOCUMENT

Si l'utilisateur demande des modifications :
1. Intègre les nouvelles informations aux données déjà collectées
2. Effectue des recherches RAG supplémentaires uniquement si nécessaire
3. Rappelle l'outil de génération avec le JSON complet mis à jour

# COMMUNICATION

- Sois concis entre les appels d'outils. Ne décris pas ce que tu vas faire avant chaque appel.
- Ne montre pas les JSON bruts à l'utilisateur.
- Si ppt_template_tool ou word_template_tool retourne un LinkPart, ne le réécris JAMAIS en texte ou en Markdown. N'affiche jamais d'URL brute ni de lien `[Download ...]`. Ne mentionne pas le bouton de téléchargement. Résume simplement ce qui a été extrait et les champs manquants.
""",
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="chat_options.attach_files",
                type="boolean",
                title="Allow file attachments",
                description="Show file upload/attachment controls for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.libraries_selection",
                type="boolean",
                title="Document libraries picker",
                description="Let users select document libraries/knowledge sources for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
        ],
    )

    default_chat_options = AgentChatOptions(
        attach_files=True,
        libraries_selection=True,
        search_rag_scoping=False,
        search_policy_selection=False,
        deep_search_delegate=False,
    )

    async def async_init(self, runtime_context: RuntimeContext):
        """Initialize agent and tool helpers."""
        await super().async_init(runtime_context=runtime_context)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

        # Initialize tool helpers
        self.export_tools = ExportTools(self)

    async def aclose(self):
        """Clean up resources."""
        await self.mcp.aclose()

    def build_vector_search_scope_options(self) -> dict:
        """
        Build strict retrieval constraints for direct vector-search calls done inside
        template/image utilities.
        """
        settings = self.get_agent_settings()
        runtime_context = self.get_runtime_context()
        include_session_scope, include_corpus_scope = get_vector_search_scopes(
            runtime_context
        )

        return {
            "document_library_tags_ids": get_document_library_tags_ids(runtime_context),
            "document_uids": get_document_uids(runtime_context),
            "owner_filter": (
                OwnerFilter.TEAM if settings.team_id else OwnerFilter.PERSONAL
            ),
            "team_id": settings.team_id,
            "session_id": runtime_context.session_id if runtime_context else None,
            "include_session_scope": include_session_scope,
            "include_corpus_scope": include_corpus_scope,
        }

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        """Create the agent graph with all tools."""
        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                # Export
                self.export_tools.get_ppt_template_tool(),
                self.export_tools.get_word_template_tool(),
                # MCP tools for RAG search
                *self.mcp.get_tools(),
            ],
            checkpointer=checkpointer,
        )
