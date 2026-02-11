"""Jira Agent for extracting requirements and user stories from project documents."""

import logging
import os
import re
from typing import Annotated

from langchain.agents import AgentState, create_agent
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.agents.jira.batch_tools import BatchTools
from agentic_backend.agents.jira.export_tools import ExportTools
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

    Supports two operations:
    - Add: Items without __remove__ marker are appended to the list
    - Remove: Items with {"__remove__": item_id} remove that ID from the list

    Also resolves ID conflicts from parallel tool calls by reassigning IDs.
    """
    remove_ids = set()
    add_items = []

    for item in update:
        if "__remove__" in item:
            remove_ids.add(item["__remove__"])
        else:
            add_items.append(item)

    # Filter out removed items from current list
    result = [item for item in current if item.get("id") not in remove_ids]

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
    user_story_titles: Annotated[list[dict], list_reducer]
    user_stories: Annotated[list[dict], list_reducer]
    test_titles: Annotated[list[dict], list_reducer]
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

## OUTILS DE MODIFICATION

**Pour ajouter UN élément:**
- `add_user_story(title, epic_name?, requirement_ids?, context?)` - Ajoute UNE User Story
- `add_test(title, user_story_id, test_type?)` - Ajoute UN test
- `add_requirement(title, req_type?, priority?)` - Ajoute UNE exigence

**Pour supprimer:**
- `remove_item(item_type, item_id)` - Supprime UN élément par son ID

**Pour générer en masse (après recherche documentaire):**
- `generate_requirements(context_summary)` - Génère plusieurs exigences depuis le contexte
- `generate_user_stories(context_summary)` - Génère plusieurs User Stories
- `generate_tests()` - Génère plusieurs tests depuis les User Stories

**Règle de choix:**
- Utilise `add_*` pour les demandes simples ("ajoute une US pour le login", "ajoute un test pour US-01")
- Utilise `generate_*` pour les demandes complexes ("génère toutes les US du projet")

## WORKFLOW STANDARD

**1. Recherche documentaire (MCP)**
Stratégie obligatoire pour generate_* :
- D'abord découvrir : recherche "objectif projet", "contexte", "périmètre"
- Identifier le domaine métier à partir des résultats
- Puis cibler avec le vocabulaire DÉCOUVERT (jamais inventé)

**2. Génération ou ajout (selon la demande)**
- Pour ajout simple → utilise add_user_story / add_test / add_requirement
- Pour génération en masse → utilise generate_requirements / generate_user_stories / generate_tests

**3. Export (OBLIGATOIRE)**
- export_deliverables() → fichier Markdown
- export_jira_csv() → CSV pour import Jira

## RÈGLES

1. **Jamais afficher le contenu** : uniquement confirmer (ex: "User Story US-01 ajoutée")
2. **Toujours exporter** : appeler export_deliverables ou export_jira_csv à la fin
3. **Erreurs de validation** : Si un outil échoue, corrige le format et réessaie.""",
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
            FieldSpec(
                key="chat_options.search_policy_selection",
                type="boolean",
                title="Search policy selector",
                description="Expose the search policy toggle (hybrid/semantic/strict).",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.search_rag_scoping",
                type="boolean",
                title="RAG scope selector",
                description="Expose the RAG scope control (documents-only vs hybrid vs knowledge).",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.deep_search_delegate",
                type="boolean",
                title="Deep search delegate toggle",
                description="Allow delegation to a senior agent for deep search.",
                required=False,
                default=False,
                ui=UIHints(group="Chat options"),
            ),
        ],
    )
    default_chat_options = AgentChatOptions(
        attach_files=True,
        libraries_selection=True,
        search_rag_scoping=True,
        search_policy_selection=True,
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

        # Check if Langfuse is configured
        self.langfuse_enabled = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
        )
        if self.langfuse_enabled:
            logger.info("[JiraAgent] Langfuse tracing enabled")

    def _get_langfuse_handler(self) -> LangfuseCallbackHandler | None:
        """Create a Langfuse callback handler for tracing LLM calls."""
        if not self.langfuse_enabled:
            return None
        return LangfuseCallbackHandler()

    async def aclose(self):
        """Clean up resources."""
        await self.mcp.aclose()

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        """Create the agent graph with all tools."""
        # Get batch generation tools
        requirements_tool = self.batch_tools.get_requirements_tool()
        user_stories_tool = self.batch_tools.get_user_stories_tool()
        tests_tool = self.batch_tools.get_tests_tool()

        # Get single-item add/remove tools
        add_requirement_tool = self.single_item_tools.get_add_requirement_tool()
        add_user_story_tool = self.single_item_tools.get_add_user_story_tool()
        add_test_tool = self.single_item_tools.get_add_test_tool()
        remove_item_tool = self.single_item_tools.get_remove_item_tool()

        # Get export tools
        export_tool = self.export_tools.get_export_tool()
        export_jira_csv_tool = self.export_tools.get_export_jira_csv_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                # Bulk generation
                requirements_tool,
                user_stories_tool,
                tests_tool,
                # Single-item add/remove
                add_user_story_tool,
                add_test_tool,
                add_requirement_tool,
                remove_item_tool,
                # Export
                export_tool,
                export_jira_csv_tool,
                # MCP tools
                *self.mcp.get_tools(),
            ],
            checkpointer=checkpointer,
            state_schema=CustomState,
        )
