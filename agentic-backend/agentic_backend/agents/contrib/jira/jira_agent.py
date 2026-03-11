"""Jira Agent for extracting requirements and user stories from project documents."""

import logging
import re
from typing import Annotated

from langchain.agents import AgentState, create_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.agents.jira.batch_tools import BatchTools
from agentic_backend.agents.jira.discovery_tools import DiscoveryTools
from agentic_backend.agents.jira.export_tools import ExportTools
from agentic_backend.agents.jira.import_tools import ImportTools
from agentic_backend.agents.jira.quality_tools import QualityTools
from agentic_backend.agents.jira.single_item_tools import SingleItemTools
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
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


def list_reducer(current: list[dict], update: list[dict]) -> list[dict]:
    """
    Custom reducer for list state that handles concurrent updates.

    Supports three operations:
    - Add: Items without special markers are appended to the list
    - Remove: Items with {"__remove__": item_id} remove that ID from the list
    - Update: Items with {"__update__": item_id, ...fields} merge fields into existing item

    Also resolves ID conflicts from parallel tool calls by reassigning IDs.
    """
    remove_ids = set()
    add_items = []
    update_items = {}  # id -> fields to merge

    for item in update:
        if "__remove__" in item:
            remove_ids.add(item["__remove__"])
        elif "__update__" in item:
            item_id = item["__update__"]
            fields = {k: v for k, v in item.items() if k != "__update__"}
            update_items[item_id] = fields
        else:
            add_items.append(item)

    # Apply updates and filter removed items
    result = []
    applied_updates = set()
    for item in current:
        item_id = item.get("id")
        if item_id in remove_ids:
            continue
        if item_id in update_items:
            fields = update_items[item_id]
            if "id" in fields:
                logger.warning(
                    "[list_reducer] __update__ should not change item ID (got id=%s for %s)",
                    fields["id"],
                    item_id,
                )
                fields = {k: v for k, v in fields.items() if k != "id"}
            result.append({**item, **fields})
            applied_updates.add(item_id)
        else:
            result.append(item)

    # Warn about updates that targeted non-existent items
    missed = set(update_items.keys()) - applied_updates
    if missed:
        logger.warning("[list_reducer] __update__ targets not found: %s", missed)

    # Track existing IDs to detect conflicts
    existing_ids = {item.get("id") for item in result if item.get("id")}

    # Append new items one by one, resolving ID conflicts
    for item in add_items:
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id in existing_ids:
            # ID conflict - extract prefix (e.g., "US-", "EX-FON-", "SC-")
            match = re.match(r"^(.+-)\d+$", item_id)
            if match:
                prefix = match.group(1)
                # Find max number with this prefix
                max_num = 0
                for existing in result:
                    eid = existing.get("id", "")
                    if eid.startswith(prefix):
                        m = re.search(r"-(\d+)$", eid)
                        if m:
                            max_num = max(max_num, int(m.group(1)))
                new_id = f"{prefix}{max_num + 1:02d}"
                item = {**item, "id": new_id}
        existing_ids.add(item.get("id"))
        result.append(item)

    return result


class CustomState(AgentState):
    """Custom state for Jira agent with requirements, user stories, and tests."""

    requirements: Annotated[list[dict], list_reducer]
    user_stories: Annotated[list[dict], list_reducer]
    tests: Annotated[list[dict], list_reducer]


@expose_runtime_source("agent.Jim")
class JiraAgent(AgentFlow):
    """Jira agent for backlog and test generation."""

    tuning = AgentTuning(
        role="Jira backlog and test builder",
        description="Extracts requirements and user stories from project documents to fill a Jira board and build Zephyr tests.",
        mcp_servers=[MCPServerRef(id="mcp-knowledge-flow-mcp-text")],
        tags=[],
        fields=[
            FieldSpec(
                key="prompts.system",
                type="prompt",
                title="System Prompt",
                description="You extract requirements, user stories and build tests from project documents",
                required=True,
                default="""Tu es un Business Analyst et Product Owner expert. Tu génères des exigences, user stories et cas de tests à partir de documents projet.

## OUTILS

**Pour découvrir le projet (OBLIGATOIRE avant génération) :**
- `discover_project()` - Analyse automatiquement les documents du projet et retourne un résumé structuré avec le contexte, vocabulaire métier et fonctionnalités identifiées

**Pour générer en masse (après discover_project) :**
- `generate_requirements(context_summary)` - Génère plusieurs exigences depuis le contexte
- `generate_user_stories(context_summary, quantity?)` - Génère plusieurs User Stories
- `generate_tests(quantity?)` - Génère plusieurs tests depuis les User Stories

**Pour consulter (READ):**
- `read_items(item_type, ids)` - Récupère des éléments. item_type = "requirements", "user_stories" ou "tests". ids = liste d'IDs (ex: ["US-01", "US-02"]) ou "all"

**Pour ajouter UN élément:**
- `add_requirement(title, req_type?, priority?, description?)` - Ajoute UNE exigence.
- `add_user_story(title, epic_name?, requirement_ids?, context?, description?, priority?, issue_type?, story_points?, labels?, dependencies?, acceptance_criteria?, clarification_questions?)` - Ajoute UNE User Story.
- `add_test(title, user_story_id, test_type?, description?, preconditions?, steps?, test_data?, priority?, expected_result?)` - Ajoute UN test.

**Pour modifier UN élément:**
- `update_requirement(item_id, title?, description?, priority?, regenerate?)` - Modifie une exigence. regenerate=True régénère la description depuis le nouveau titre.
- `update_user_story(item_id, summary?, description?, epic_name?, priority?, story_points?, labels?, requirement_ids?, dependencies?, acceptance_criteria?, regenerate?)` - Modifie une User Story
- `update_test(item_id, name?, user_story_id?, description?, preconditions?, steps?, test_data?, priority?, test_type?, expected_result?, regenerate?)` - Modifie un test

**Pour supprimer:**
- `remove_item(item_type, item_id)` - Supprime UN élément par son ID. item_type = "requirements", "user_stories" ou "tests"

**Pour importer depuis un fichier Markdown:**
- `import_markdown(markdown_content, mode?)` - Importe les exigences, User Stories et tests depuis un fichier Markdown exporté. mode="merge" (défaut) fusionne avec l'existant, mode="overwrite" remplace tout.

**Pour analyser la qualité:**
- `assess_user_story(story_id)` - Analyse la qualité d'une User Story (checklists analyse US + critères d'acceptation)
- `assess_test(test_id)` - Analyse la qualité d'un test (checklist cas de test et jeux de données)

**Règle de choix:**
- Utilise `generate_*` pour les demandes complexes ("génère toutes les US du projet")
- Utilise `add_*` pour les demandes simples ("ajoute une US pour le login", "ajoute un test pour US-01")

## WORKFLOW STANDARD

**1. Découverte du projet**
- TOUJOURS appeler `discover_project()` en premier pour obtenir un résumé structuré du projet
- Utiliser le contexte retourné (section "Contexte complet") comme `context_summary` pour generate_requirements / generate_user_stories
- N'utiliser les outils MCP de recherche directe QUE pour des recherches complémentaires ciblées sur un point précis APRÈS discover_project

**2. Génération ou ajout (selon la demande)**
- Pour génération en masse → utilise generate_requirements / generate_user_stories / generate_tests
- Pour ajout simple → utilise add_user_story / add_test / add_requirement

**3. Export (OBLIGATOIRE)**
- export_deliverables() → fichier Markdown (par défaut)
- export_jira_csv() → CSV pour import Jira (UNIQUEMENT si l'utilisateur demande explicitement un CSV ou un export Jira)
- export_zephyr_csv() → CSV pour import Zephyr Scale (UNIQUEMENT si l'utilisateur demande explicitement un export Zephyr)

## RÈGLES

1. **Jamais afficher le contenu** : uniquement confirmer (ex: "User Story US-01 ajoutée")
2. **Export par défaut en Markdown** : à la fin, appeler UNIQUEMENT export_deliverables(). N'appeler export_jira_csv() QUE si l'utilisateur demande explicitement un CSV ou un fichier pour Jira. N'appeler export_zephyr_csv() QUE si l'utilisateur demande explicitement un export Zephyr
3. **Liens de téléchargement** : Si un outil d'export retourne un LinkPart, ne le réécris JAMAIS en texte ou en Markdown. N'affiche jamais d'URL brute ni de lien `[Download ...]` ou `[Télécharger ...]`. Le bouton de téléchargement s'affiche automatiquement. Résume simplement ce qui a été généré.
4. **Erreurs de validation** : Si un outil échoue, corrige le format et réessaie.""",
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
            # FieldSpec(
            #     key="chat_options.search_policy_selection",
            #     type="boolean",
            #     title="Search policy selector",
            #     description="Expose the search policy toggle (hybrid/semantic/strict).",
            #     required=False,
            #     default=True,
            #     ui=UIHints(group="Chat options"),
            # ),
            # FieldSpec(
            #     key="chat_options.search_rag_scoping",
            #     type="boolean",
            #     title="RAG scope selector",
            #     description="Expose the RAG scope control (documents-only vs hybrid vs knowledge).",
            #     required=False,
            #     default=True,
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
        self.batch_tools = BatchTools(self)
        self.single_item_tools = SingleItemTools(self)
        self.export_tools = ExportTools(self)
        self.import_tools = ImportTools(self)
        self.quality_tools = QualityTools(self)
        self.discovery_tools = DiscoveryTools(self)

    async def aclose(self):
        """Clean up resources."""
        await self.mcp.aclose()

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        """Create the agent graph with all tools."""
        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                # Project discovery
                self.discovery_tools.get_discover_project_tool(),
                # Bulk generation
                self.batch_tools.get_requirements_tool(),
                self.batch_tools.get_user_stories_tool(),
                self.batch_tools.get_tests_tool(),
                # Single-item add/remove
                self.single_item_tools.get_add_requirement_tool(),
                self.single_item_tools.get_add_user_story_tool(),
                self.single_item_tools.get_add_test_tool(),
                self.single_item_tools.get_remove_item_tool(),
                # Single-item update
                self.single_item_tools.get_update_requirement_tool(),
                self.single_item_tools.get_update_user_story_tool(),
                self.single_item_tools.get_update_test_tool(),
                # Read/inspect
                self.single_item_tools.get_read_items_tool(),
                # Export
                self.export_tools.get_export_tool(),
                self.export_tools.get_export_jira_csv_tool(),
                self.export_tools.get_export_zephyr_csv_tool(),
                # Import
                self.import_tools.get_import_markdown_tool(),
                # Quality assessment
                self.quality_tools.get_assess_user_story_tool(),
                self.quality_tools.get_assess_test_tool(),
                # MCP tools
                *self.mcp.get_tools(),
            ],
            checkpointer=checkpointer,
            state_schema=CustomState,
        )
