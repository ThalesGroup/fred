import csv
import io
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import cast

from langchain.agents import AgentState, create_agent
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agentic_backend.agents.jira.pydantic_models import (
    QuickRequirement,
    QuickTest,
    QuickUserStory,
    Requirement,
    RequirementsList,
    Test,
    TestsList,
    TestTitlesList,
    UserStoriesList,
    UserStory,
    UserStoryTitlesList,
)
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
from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


# Centralized ID generation helpers for consistent ID formats


def _get_next_user_story_id(state: dict) -> str:
    """Generate next US-XX ID based on existing stories and titles."""
    existing_stories = state.get("user_stories") or []
    existing_titles = state.get("user_story_titles") or []
    all_ids = [s.get("id", "") for s in existing_stories + existing_titles]

    max_num = 0
    for id_str in all_ids:
        match = re.search(r"US-(\d+)", id_str)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"US-{max_num + 1:02d}"


def _get_next_test_id(state: dict) -> str:
    """Generate next SC-XX ID based on existing tests and titles."""
    existing_tests = state.get("tests") or []
    existing_titles = state.get("test_titles") or []
    all_ids = [t.get("id", "") for t in existing_tests + existing_titles]

    max_num = 0
    for id_str in all_ids:
        match = re.search(r"SC-(\d+)", id_str)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"SC-{max_num + 1:02d}"


def _get_next_requirement_id(state: dict, req_type: str) -> str:
    """Generate next EX-FON-XX or EX-NFON-XX ID based on existing requirements."""
    existing_reqs = state.get("requirements") or []
    prefix = "EX-FON-" if req_type == "fonctionnelle" else "EX-NFON-"

    max_num = 0
    for req in existing_reqs:
        id_str = req.get("id", "")
        if id_str.startswith(prefix):
            match = re.search(r"-(\d+)$", id_str)
            if match:
                max_num = max(max_num, int(match.group(1)))
    return f"{prefix}{max_num + 1:02d}"


class CustomState(AgentState):
    requirements: list[dict]  # Validated against requirementsSchema
    user_story_titles: list[dict]  # List of {id, title, epic_name} for batch gen
    user_stories: list[dict]  # Validated against userStoriesSchema
    test_titles: list[dict]  # List of {id, title, us_id, test_type} for batch gen
    tests: list[dict]  # Validated against testsSchema


@expose_runtime_source("agent.Jim")
class JiraAgent(AgentFlow):
    tuning = AgentTuning(
        role="Jira backlog and test builder",
        description="Extracts requirements and user stories from project documents to fill a Jira board and build Zephyr tests.",
        mcp_servers=[MCPServerRef(name="mcp-knowledge-flow-mcp-text")],
        tags=[],
        fields=[
            FieldSpec(
                key="prompts.system",
                type="prompt",
                title="System Prompt",
                description="You extract requirements, user stories and build tests from project documents",  # to fill a Jira board and build Zephyr tests.",
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
- D'abord découvrir : recherche "objectif projet", "contexte", "périmètre", "acteurs"
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
        await super().async_init(runtime_context=runtime_context)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()
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
        await self.mcp.aclose()

    # Batch generation tools

    def get_requirements_tool(self):
        """Tool that generates requirements using a separate LLM call"""

        @tool
        async def generate_requirements(runtime: ToolRuntime, context_summary: str):
            """
            Génère une liste d'exigences formelles (fonctionnelles et non-fonctionnelles)
            à partir du contexte projet fourni par les recherches documentaires.

            IMPORTANT:
            - AVANT d'appeler cet outil, tu DOIS faire une recherche documentaire avec les outils MCP
            - Le context_summary doit contenir les informations extraites des documents (min 200 caractères)

            Args:
                context_summary: Résumé du contexte projet extrait des documents (min 200 caractères)

            Returns:
                Message de confirmation que les exigences ont été générées
            """
            # Validate context_summary has meaningful content
            if len(context_summary.strip()) < 200:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Le contexte fourni est trop court (minimum 200 caractères). "
                                "Tu dois d'abord faire une recherche documentaire avec les outils MCP "
                                "(search_documents, get_document_content) pour extraire les informations "
                                "du projet, puis fournir un résumé détaillé en paramètre.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            requirements_prompt = """Tu es un Business Analyst expert. Génère une liste d'exigences formelles basée sur le contexte projet suivant.

Contexte projet extrait des documents:
{context_summary}

Consignes :
1. **Génère des exigences fonctionnelles et non-fonctionnelles**
2. **Formalisme :** Exigences claires, concises, non ambiguës et testables
3. **ID Unique :** Ex: EX-FON-01 (fonctionnelle), EX-NFON-01 (non-fonctionnelle)
4. **Priorisation :** Haute, Moyenne ou Basse

Règles:
- id: Identifiant unique (EX-FON-XX pour fonctionnelle, EX-NFON-XX pour non-fonctionnelle)
- title: Titre concis
- description: Description détaillée et testable
- priority: "Haute", "Moyenne" ou "Basse" """

            model = get_default_chat_model().with_structured_output(
                RequirementsList, method="json_schema"
            )
            messages = [
                SystemMessage(
                    content=requirements_prompt.format(context_summary=context_summary)
                )
            ]

            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = cast(
                RequirementsList, await model.ainvoke(messages, config=config)
            )
            requirements = [r.model_dump() for r in response.items]

            return Command(
                update={
                    "requirements": requirements,
                    "messages": [
                        ToolMessage(
                            f"✓ {len(requirements)} exigences générées avec succès. "
                            f"Si tu as terminé de générer tous les livrables demandés par l'utilisateur, "
                            f"appelle maintenant export_deliverables() pour fournir le lien de téléchargement.",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return generate_requirements

    async def _generate_user_story_titles(
        self,
        runtime: ToolRuntime,
        context_summary: str,
        quantity: int | None = None,
    ) -> list[dict]:
        """Internal helper to generate user story titles."""
        titles_prompt = """Tu es un Product Owner expert. Génère une liste de titres de User Stories.

Contexte projet extrait des documents:
{context_summary}

{requirements_section}

{existing_stories_section}

**Objectif:** Créer une liste cohérente de titres de User Stories qui:
- Couvrent l'ensemble du périmètre fonctionnel
- Évitent les doublons et chevauchements
- Sont regroupées par Epic logique
- Suivent une progression fonctionnelle cohérente
- **Sont liées aux exigences correspondantes via requirement_ids**

**Règles:**
- Chaque titre doit être concis (max 80 caractères)
- Utiliser des verbes d'action (Créer, Afficher, Modifier, Supprimer, etc.)
- Regrouper les stories liées sous le même Epic
- **OBLIGATOIRE: Chaque User Story doit avoir au moins un requirement_id si des exigences existent**
- **NE PAS générer de titres pour des fonctionnalités déjà couvertes par les User Stories existantes**
- Les IDs doivent continuer la séquence existante (commencer à US-{next_id_hint})

{quantity_instruction}"""

        # Build requirements section
        requirements_section = ""
        requirements = runtime.state.get("requirements")
        if requirements:
            requirements_section = f"""
Exigences à respecter:
{json.dumps(requirements, ensure_ascii=False, indent=2)}
"""

        # Build existing stories section to avoid duplicates
        existing_stories_section = ""
        existing_stories = runtime.state.get("user_stories") or []
        existing_titles = runtime.state.get("user_story_titles") or []

        # Determine the next ID hint based on existing stories/titles
        next_id_hint = "01"
        all_existing_ids = [s.get("id", "") for s in existing_stories] + [
            t.get("id", "") for t in existing_titles
        ]
        if all_existing_ids:
            max_num = 0
            for id_str in all_existing_ids:
                match = re.search(r"US-(\d+)", id_str)
                if match:
                    max_num = max(max_num, int(match.group(1)))
            next_id_hint = f"{max_num + 1:02d}"

        if existing_stories or existing_titles:
            existing_info = []
            for story in existing_stories:
                existing_info.append(
                    {
                        "id": story.get("id"),
                        "title": story.get("summary"),
                        "epic_name": story.get("epic_name"),
                    }
                )
            existing_story_ids = {s.get("id") for s in existing_stories}
            for title in existing_titles:
                if title.get("id") not in existing_story_ids:
                    existing_info.append(title)

            if existing_info:
                existing_stories_section = f"""
**User Stories DÉJÀ EXISTANTES (NE PAS DUPLIQUER):**
{json.dumps(existing_info, ensure_ascii=False, indent=2)}

Tu dois générer des User Stories COMPLÉMENTAIRES qui n'existent pas encore.
"""

        if quantity is not None:
            quantity_instruction = f"Génère exactement {quantity} NOUVEAUX titres de User Stories (en plus des existantes)."
        else:
            quantity_instruction = "Génère le nombre approprié de User Stories pour couvrir l'ensemble du périmètre fonctionnel du projet."

        model = get_default_chat_model().with_structured_output(
            UserStoryTitlesList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=titles_prompt.format(
                    context_summary=context_summary,
                    requirements_section=requirements_section,
                    existing_stories_section=existing_stories_section,
                    quantity_instruction=quantity_instruction,
                    next_id_hint=next_id_hint,
                )
            )
        ]

        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )

        response = cast(
            UserStoryTitlesList, await model.ainvoke(messages, config=config)
        )
        new_titles = [t.model_dump() for t in response.items]
        logger.info(f"US TITLES: {existing_titles + new_titles}")
        return existing_titles + new_titles

    async def _generate_user_story_batch(
        self,
        titles_to_process: list[dict],
        context_summary: str,
        requirements: list[dict] | None,
    ) -> list[dict]:
        """
        Internal helper to generate a single batch of user stories.

        Args:
            titles_to_process: List of user story titles to generate stories for
            context_summary: Project context summary
            requirements: Optional list of requirements

        Returns:
            List of generated user story dicts
        """
        stories_prompt = """Tu es un Product Owner expert. Génère des User Stories COMPLÈTES pour les titres suivants.

{context_section}

{requirements_section}

**TITRES À DÉVELOPPER:**
{titles_json}

**Structure de base :**
- **Format :** "En tant que [persona], je veux [action], afin de [bénéfice]"
- Stories atomiques, verticales et testables
- **Couverture complète :** Happy path + cas d'erreur + tous les personas

**Critères d'Acceptation Exhaustifs (Format Gherkin)** - OBLIGATOIRE pour CHAQUE story :

1. **Cas Nominaux (Happy Path)** - Scénario idéal
2. **Validations de Données** - Formats invalides, champs manquants, limites
3. **Cas d'Erreur** - Erreurs techniques et métier
4. **Cas Limites** - Valeurs frontières, listes vides/longues
5. **Feedback Utilisateur** - Messages de succès/erreur EXACTS

**Format Gherkin:** "Étant donné que [contexte], Quand [action], Alors [résultat attendu]"

**Aspects Transverses :** aspects de sécurité (OWASP), d'accessibilité (WCAG - navigation clavier, lecteurs d'écran) et de conformité (RGPD) si pertinent.

**Métadonnées:**
- **Estimation:** Fibonacci (1, 2, 3, 5, 8, 13, 21)
- **Priorisation:** High, Medium, Low

Génère EXACTEMENT {count} User Stories correspondant aux titres fournis.
Utilise les mêmes IDs, epic_name et requirement_ids que dans les titres."""

        # Build context section
        context_section = ""
        if context_summary:
            context_section = f"Contexte projet:\n{context_summary}"

        # Build requirements section
        requirements_section = ""
        if requirements:
            requirements_section = f"""
Exigences à respecter:
{json.dumps(requirements, ensure_ascii=False, indent=2)}
"""

        model = get_default_chat_model().with_structured_output(
            UserStoriesList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=stories_prompt.format(
                    context_section=context_section,
                    requirements_section=requirements_section,
                    titles_json=json.dumps(
                        titles_to_process, ensure_ascii=False, indent=2
                    ),
                    count=len(titles_to_process),
                )
            )
        ]

        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )

        response = cast(UserStoriesList, await model.ainvoke(messages, config=config))
        return [s.model_dump() for s in response.items]

    def get_user_stories_tool(self):
        """Tool that generates user stories with automatic title generation"""

        @tool
        async def generate_user_stories(
            runtime: ToolRuntime,
            context_summary: str,
            batch_size: int = 10,
            quantity: int | None = None,
        ):
            """
            Génère TOUTES les User Stories complètes à partir du contexte projet en une seule invocation.

            Cet outil génère automatiquement les titres de User Stories puis génère toutes les stories
            par lots internes jusqu'à complétion. Il retourne uniquement quand toutes les stories
            sont générées.

            IMPORTANT:
            - AVANT d'appeler cet outil, tu DOIS faire une recherche documentaire avec les outils MCP
            - Le context_summary doit contenir les informations extraites des documents (min 200 caractères)
            - Cet outil peut prendre du temps si beaucoup de stories sont à générer

            Args:
                context_summary: Résumé du contexte projet extrait des documents (min 200 caractères)
                batch_size: Nombre de User Stories à générer par lot interne (défaut: 10)
                quantity: Nombre total de User Stories à générer (optionnel)

            Returns:
                Message de confirmation avec le nombre total de stories générées
            """
            # Validate context_summary has meaningful content
            if len(context_summary.strip()) < 200:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Le contexte fourni est trop court (minimum 200 caractères). "
                                "Tu dois d'abord faire une recherche documentaire avec les outils MCP "
                                "(search_documents, get_document_content) pour extraire les informations "
                                "du projet, puis fournir un résumé détaillé en paramètre.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Get titles and existing stories
            all_titles = runtime.state.get("user_story_titles") or []
            existing_stories = runtime.state.get("user_stories") or []
            requirements = runtime.state.get("requirements")

            # Auto-generate titles if none exist
            state_updates = {}
            if not all_titles:
                all_titles = await self._generate_user_story_titles(
                    runtime, context_summary, quantity
                )
                state_updates["user_story_titles"] = all_titles

            # Get all unprocessed titles
            existing_ids = {s.get("id") for s in existing_stories}
            pending_titles = [t for t in all_titles if t["id"] not in existing_ids]

            if not pending_titles:
                return Command(
                    update={
                        **state_updates,
                        "messages": [
                            ToolMessage(
                                f"✓ Toutes les User Stories ont déjà été générées ({len(existing_stories)} au total). "
                                f"Appelle export_deliverables() pour exporter les livrables.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Internal batching loop - generate all stories without LLM re-invocation
            all_generated_stories = list(existing_stories)
            total_to_generate = len(pending_titles)
            batches_completed = 0

            logger.info(
                f"[JiraAgent] Starting internal batch generation: {total_to_generate} user stories in batches of {batch_size}"
            )

            while pending_titles:
                # Get next batch
                titles_batch = pending_titles[:batch_size]
                pending_titles = pending_titles[batch_size:]

                # Generate this batch
                try:
                    new_stories = await self._generate_user_story_batch(
                        titles_batch, context_summary, requirements
                    )
                    all_generated_stories.extend(new_stories)
                    batches_completed += 1

                    logger.info(
                        f"[JiraAgent] Batch {batches_completed} complete: "
                        f"{len(all_generated_stories)}/{len(all_titles)} user stories generated"
                    )
                except Exception as e:
                    logger.error(f"[JiraAgent] Error generating user story batch: {e}")
                    # Return partial results on error
                    return Command(
                        update={
                            **state_updates,
                            "user_stories": all_generated_stories,
                            "messages": [
                                ToolMessage(
                                    f"⚠️ Erreur lors de la génération du lot {batches_completed + 1}: {str(e)}. "
                                    f"{len(all_generated_stories)} User Stories générées sur {len(all_titles)} prévues. "
                                    f"Tu peux réappeler generate_user_stories() pour continuer.",
                                    tool_call_id=runtime.tool_call_id,
                                ),
                            ],
                        }
                    )

            # All stories generated successfully
            stories_generated_this_call = len(all_generated_stories) - len(
                existing_stories
            )
            msg = (
                f"✓ {stories_generated_this_call} User Stories générées en {batches_completed} lots. "
                f"Total: {len(all_generated_stories)} User Stories complètes! "
                f"Appelle export_deliverables() pour exporter les livrables."
            )

            return Command(
                update={
                    **state_updates,
                    "user_stories": all_generated_stories,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_user_stories

    async def _generate_test_titles(
        self,
        runtime: ToolRuntime,
        quantity: int | None = None,
    ) -> list[dict]:
        """Internal helper to generate test titles."""
        user_stories = runtime.state.get("user_stories") or []
        existing_titles = runtime.state.get("test_titles") or []
        existing_tests = runtime.state.get("tests") or []

        # Determine the next ID hint based on existing tests/titles
        next_id_hint = "01"
        all_existing_ids = [t.get("id", "") for t in existing_tests] + [
            t.get("id", "") for t in existing_titles
        ]
        if all_existing_ids:
            max_num = 0
            for id_str in all_existing_ids:
                match = re.search(r"SC-(\d+)", id_str)
                if match:
                    max_num = max(max_num, int(match.group(1)))
            next_id_hint = f"{max_num + 1:02d}"

        # Build existing titles section to avoid duplicates
        existing_titles_section = ""
        if existing_titles:
            existing_titles_section = f"""
**Titres de tests DÉJÀ EXISTANTS (NE PAS DUPLIQUER):**
{json.dumps(existing_titles, ensure_ascii=False, indent=2)}

Tu dois générer des titres de tests COMPLÉMENTAIRES qui n'existent pas encore.
"""

        titles_prompt = """Tu es un expert en tests logiciels. Génère une liste de titres de tests pour les User Stories suivantes.

## User Stories à couvrir

{user_stories_json}

{existing_titles_section}

## Instructions

Pour chaque User Story, génère des titres de tests couvrant:
- **Nominal**: Cas de test du parcours nominal (happy path)
- **Limite**: Cas de test aux limites (valeurs frontières, listes vides/longues)
- **Erreur**: Cas de test d'erreur (validations, erreurs techniques)

**Règles:**
- Chaque titre doit être concis et descriptif (max 80 caractères)
- Les IDs doivent suivre le format SC-XX (commencer à SC-{next_id_hint})
- Chaque titre doit référencer sa User Story via user_story_id

{quantity_instruction}"""

        if quantity is not None:
            quantity_instruction = (
                f"Génère exactement {quantity} titres de tests au total."
            )
        else:
            quantity_instruction = "Génère environ 3 titres de tests par User Story (minimum 2, maximum 5 selon la complexité)."

        model = get_default_chat_model().with_structured_output(
            TestTitlesList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=titles_prompt.format(
                    user_stories_json=json.dumps(
                        user_stories, ensure_ascii=False, indent=2
                    ),
                    existing_titles_section=existing_titles_section,
                    next_id_hint=next_id_hint,
                    quantity_instruction=quantity_instruction,
                )
            )
        ]

        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )

        response = cast(TestTitlesList, await model.ainvoke(messages, config=config))
        new_titles = [t.model_dump() for t in response.items]
        return existing_titles + new_titles

    async def _generate_test_batch(
        self,
        titles_to_process: list[dict],
        stories_by_id: dict[str, dict],
        jdd: str,
    ) -> list[dict]:
        """
        Internal helper to generate a single batch of tests.

        Args:
            titles_to_process: List of test titles to generate tests for
            stories_by_id: Map of user story ID -> user story dict
            jdd: Test data (Jeu de Données) string

        Returns:
            List of generated test dicts
        """
        # Get the relevant user stories for the titles being processed
        relevant_story_ids = {t.get("user_story_id") for t in titles_to_process}
        relevant_stories = [
            stories_by_id[sid] for sid in relevant_story_ids if sid in stories_by_id
        ]

        tests_prompt = """## Rôle

Tu es un expert en tests logiciels. Génère des scénarios de tests COMPLETS pour les titres de tests suivants.

## Titres de tests à développer

{TITLES_JSON}

## User Stories associées (pour contexte)

{USER_STORIES}

## Jeu de Données (JDD)

{JDD}

## Instructions

Pour chaque titre de test fourni, génère le test complet avec:
- Les étapes détaillées en format Gherkin
- Les préconditions nécessaires
- Les données de test spécifiques
- Le résultat attendu

Règles:
- Génère EXACTEMENT {count} tests correspondant aux titres fournis
- Utilise les mêmes IDs, user_story_id et test_type que dans les titres
- priority: "Haute", "Moyenne" ou "Basse" """

        model = get_default_chat_model().with_structured_output(
            TestsList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=tests_prompt.format(
                    TITLES_JSON=json.dumps(
                        titles_to_process, ensure_ascii=False, indent=2
                    ),
                    USER_STORIES=json.dumps(
                        relevant_stories, ensure_ascii=False, indent=2
                    ),
                    JDD=jdd if jdd else "Aucun JDD fourni",
                    count=len(titles_to_process),
                )
            )
        ]

        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )

        response = cast(TestsList, await model.ainvoke(messages, config=config))
        return [t.model_dump() for t in response.items]

    def get_tests_tool(self):
        """Tool that generates test scenarios with automatic title generation"""

        @tool
        async def generate_tests(
            runtime: ToolRuntime,
            batch_size: int = 10,
            quantity: int | None = None,
            jdd: str = "",
        ):
            """
            Génère TOUS les tests complets à partir des User Stories en une seule invocation.

            Cet outil génère automatiquement les titres de tests puis génère tous les tests
            par lots internes jusqu'à complétion. Il retourne uniquement quand tous les
            tests sont générés.

            IMPORTANT:
            - Des User Stories doivent avoir été générées avant d'appeler cet outil
            - Cet outil peut prendre du temps si beaucoup de tests sont à générer

            Args:
                batch_size: Nombre de tests à générer par lot interne (défaut: 10)
                quantity: Nombre total de tests à générer (optionnel)
                jdd: Jeu de Données pour les personas (optionnel)

            Returns:
                Message de confirmation avec le nombre total de tests générés
            """
            # Get test titles and existing tests
            all_titles = runtime.state.get("test_titles") or []
            existing_tests = runtime.state.get("tests") or []
            all_stories = runtime.state.get("user_stories") or []

            # Check if user stories exist
            if not all_stories:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Aucune User Story n'a été générée. "
                                "Appelle d'abord generate_user_stories() pour créer les User Stories.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Auto-generate titles if none exist
            state_updates = {}
            if not all_titles:
                all_titles = await self._generate_test_titles(runtime, quantity)
                state_updates["test_titles"] = all_titles

            # Create a map of stories by ID for quick lookup
            stories_by_id = {s.get("id"): s for s in all_stories}

            # Get all unprocessed titles
            existing_test_ids = {t.get("id") for t in existing_tests}
            pending_titles = [t for t in all_titles if t["id"] not in existing_test_ids]

            if not pending_titles:
                return Command(
                    update={
                        **state_updates,
                        "messages": [
                            ToolMessage(
                                f"✓ Tous les tests ont déjà été générés ({len(existing_tests)} au total). "
                                f"Appelle export_deliverables() pour exporter les livrables.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Internal batching loop - generate all tests without LLM re-invocation
            all_generated_tests = list(existing_tests)
            total_to_generate = len(pending_titles)
            batches_completed = 0

            logger.info(
                f"[JiraAgent] Starting internal batch generation: {total_to_generate} tests in batches of {batch_size}"
            )

            while pending_titles:
                # Get next batch
                titles_batch = pending_titles[:batch_size]
                pending_titles = pending_titles[batch_size:]

                # Generate this batch
                try:
                    new_tests = await self._generate_test_batch(
                        titles_batch, stories_by_id, jdd
                    )
                    all_generated_tests.extend(new_tests)
                    batches_completed += 1

                    logger.info(
                        f"[JiraAgent] Batch {batches_completed} complete: "
                        f"{len(all_generated_tests)}/{len(all_titles)} tests generated"
                    )
                except Exception as e:
                    logger.error(f"[JiraAgent] Error generating test batch: {e}")
                    # Return partial results on error
                    return Command(
                        update={
                            **state_updates,
                            "tests": all_generated_tests,
                            "messages": [
                                ToolMessage(
                                    f"⚠️ Erreur lors de la génération du lot {batches_completed + 1}: {str(e)}. "
                                    f"{len(all_generated_tests)} tests générés sur {len(all_titles)} prévus. "
                                    f"Tu peux réappeler generate_tests() pour continuer.",
                                    tool_call_id=runtime.tool_call_id,
                                ),
                            ],
                        }
                    )

            # All tests generated successfully
            tests_generated_this_call = len(all_generated_tests) - len(existing_tests)
            msg = (
                f"✓ {tests_generated_this_call} tests générés en {batches_completed} lots. "
                f"Total: {len(all_generated_tests)} tests complets! "
                f"Appelle export_deliverables() pour exporter les livrables."
            )

            return Command(
                update={
                    **state_updates,
                    "tests": all_generated_tests,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_tests

    # Single-item add/remove tools

    async def _expand_requirement(
        self,
        title: str,
        req_type: str,
    ) -> dict:
        """
        Use internal LLM call with structured output to expand a title into a full requirement.

        This is for SINGLE item generation only (1 LLM call).
        For bulk generation, use generate_requirements() which has batching.
        """
        type_label = (
            "fonctionnelle" if req_type == "fonctionnelle" else "non-fonctionnelle"
        )

        prompt = f"""Génère une exigence {type_label} complète à partir de ce titre.

Titre: {title}

Génère une description détaillée de l'exigence qui:
- Explique clairement ce qui est requis
- Est mesurable et testable
- Est cohérente avec le titre fourni
"""

        model = get_default_chat_model().with_structured_output(
            QuickRequirement, method="json_schema"
        )
        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )
        result = cast(
            QuickRequirement,
            await model.ainvoke([SystemMessage(content=prompt)], config=config),
        )
        return result.model_dump()

    async def _expand_user_story(
        self,
        title: str,
        epic_name: str,
        requirement_ids: list[str] | None,
        context: str | None,
    ) -> dict:
        """
        Use internal LLM call with structured output to expand a title into a full user story.

        This is for SINGLE item generation only (1 LLM call).
        For bulk generation, use generate_user_stories() which has batching.
        """
        prompt = f"""Génère une User Story complète à partir de ce titre.

Titre: {title}
Epic: {epic_name}
{f"Exigences liées: {requirement_ids}" if requirement_ids else ""}
{f"Contexte additionnel: {context}" if context else ""}

Génère:
- Description au format "En tant que [rôle], je veux [action], afin de [bénéfice]"
- 2-4 critères d'acceptation avec étapes Gherkin (Given/When/Then)
- Story points (Fibonacci: 1, 2, 3, 5, 8, 13)
- Priorité (High/Medium/Low)
"""

        model = get_default_chat_model().with_structured_output(
            QuickUserStory, method="json_schema"
        )
        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )
        result = cast(
            QuickUserStory,
            await model.ainvoke([SystemMessage(content=prompt)], config=config),
        )
        return result.model_dump()

    async def _expand_test(
        self,
        title: str,
        user_story_id: str,
        test_type: str,
        user_story_context: dict | None,
    ) -> dict:
        """
        Use internal LLM call with structured output to expand a title into a full test.

        This is for SINGLE item generation only (1 LLM call).
        For bulk generation, use generate_tests() which has batching.
        """
        story_context = ""
        if user_story_context:
            story_context = f"""
User Story associée:
- ID: {user_story_context.get("id")}
- Résumé: {user_story_context.get("summary")}
- Description: {user_story_context.get("description")}
"""

        prompt = f"""Génère un scénario de test complet à partir de ce titre.

Titre du test: {title}
User Story liée: {user_story_id}
Type de test: {test_type}
{story_context}

Génère:
- Description du test
- Préconditions nécessaires
- Étapes détaillées en format Gherkin (Given/When/Then)
- Données de test si pertinent
- Résultat attendu
- Priorité (Haute/Moyenne/Basse)
"""

        model = get_default_chat_model().with_structured_output(
            QuickTest, method="json_schema"
        )
        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )
        result = cast(
            QuickTest,
            await model.ainvoke([SystemMessage(content=prompt)], config=config),
        )
        return result.model_dump()

    def get_add_user_story_tool(self):
        """Tool to add a single user story from a title."""

        @tool
        async def add_user_story(
            runtime: ToolRuntime,
            title: str,
            epic_name: str | None = None,
            requirement_ids: list[str] | None = None,
            context: str | None = None,
        ):
            """
            Ajoute UNE User Story à partir d'un titre.

            Utilise cet outil pour les demandes simples comme "ajoute une US pour le login".
            Pour générer PLUSIEURS User Stories, utilise generate_user_stories().

            Args:
                title: Titre de la User Story (ex: "Permettre la connexion SSO")
                epic_name: Nom de l'Epic parent (défaut: "Backlog")
                requirement_ids: Liste des IDs d'exigences liées (optionnel)
                context: Contexte supplémentaire pour guider la génération
            """
            # Generate ID
            next_id = _get_next_user_story_id(runtime.state)
            epic = epic_name or "Backlog"

            # Expand title into full story using internal LLM
            expanded = await self._expand_user_story(
                title, epic, requirement_ids, context
            )

            # Build complete UserStory
            new_story = {
                "id": next_id,
                "summary": title,
                "epic_name": epic,
                "issue_type": "Story",
                "requirement_ids": requirement_ids or [],
                **expanded,
            }

            # Validate and add to state
            validated = UserStory.model_validate(new_story)
            existing = runtime.state.get("user_stories") or []

            return Command(
                update={
                    "user_stories": existing + [validated.model_dump()],
                    "messages": [
                        ToolMessage(
                            f"✓ User Story {next_id} ajoutée: {title}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return add_user_story

    def get_add_test_tool(self):
        """Tool to add a single test from a title."""

        @tool
        async def add_test(
            runtime: ToolRuntime,
            title: str,
            user_story_id: str,
            test_type: str | None = None,
        ):
            """
            Ajoute UN test à partir d'un titre.

            Utilise cet outil pour les demandes simples comme "ajoute un test pour US-01".
            Pour générer PLUSIEURS tests, utilise generate_tests().

            Args:
                title: Titre du test (ex: "Vérifier connexion avec identifiants invalides")
                user_story_id: ID de la User Story liée (ex: "US-01")
                test_type: Type de test - "Nominal", "Limite", ou "Erreur" (défaut: "Nominal")
            """
            # Validate user_story_id exists
            user_stories = runtime.state.get("user_stories") or []
            story_context = None
            for story in user_stories:
                if story.get("id") == user_story_id:
                    story_context = story
                    break

            if not story_context:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"⚠️ User Story {user_story_id} non trouvée. "
                                f"Assure-toi que la User Story existe avant d'ajouter un test.",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )

            # Generate ID
            next_id = _get_next_test_id(runtime.state)
            ttype = test_type or "Nominal"

            # Expand title into full test using internal LLM
            expanded = await self._expand_test(
                title, user_story_id, ttype, story_context
            )

            # Build complete Test
            new_test = {
                "id": next_id,
                "name": title,
                "user_story_id": user_story_id,
                "test_type": ttype,
                **expanded,
            }

            # Validate and add to state
            validated = Test.model_validate(new_test)
            existing = runtime.state.get("tests") or []

            return Command(
                update={
                    "tests": existing + [validated.model_dump()],
                    "messages": [
                        ToolMessage(
                            f"✓ Test {next_id} ajouté: {title}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return add_test

    def get_add_requirement_tool(self):
        """Tool to add a single requirement from a title."""

        @tool
        async def add_requirement(
            runtime: ToolRuntime,
            title: str,
            req_type: str | None = None,
            priority: str | None = None,
        ):
            """
            Ajoute UNE exigence à partir d'un titre.

            Utilise cet outil pour les demandes simples comme "ajoute une exigence pour l'authentification".
            Pour générer PLUSIEURS exigences, utilise generate_requirements().

            Args:
                title: Titre de l'exigence (ex: "Authentification multi-facteur")
                req_type: Type d'exigence - "fonctionnelle" ou "non-fonctionnelle" (défaut: "fonctionnelle")
                priority: Priorité - "Haute", "Moyenne", ou "Basse" (défaut: "Moyenne")
            """
            # Generate ID
            rtype = req_type or "fonctionnelle"
            next_id = _get_next_requirement_id(runtime.state, rtype)
            prio = priority or "Moyenne"

            # Expand title into full requirement using internal LLM
            expanded = await self._expand_requirement(title, rtype)

            # Build complete Requirement
            new_req = {
                "id": next_id,
                "title": title,
                "priority": prio,
                **expanded,
            }

            # Validate and add to state
            validated = Requirement.model_validate(new_req)
            existing = runtime.state.get("requirements") or []

            return Command(
                update={
                    "requirements": existing + [validated.model_dump()],
                    "messages": [
                        ToolMessage(
                            f"✓ Exigence {next_id} ajoutée: {title}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return add_requirement

    def get_remove_item_tool(self):
        """Tool to remove an item by ID."""

        @tool
        async def remove_item(
            runtime: ToolRuntime,
            item_type: str,
            item_id: str,
        ):
            """
            Supprime un élément par son ID.

            Args:
                item_type: Type d'élément - "requirements", "user_stories", ou "tests"
                item_id: ID de l'élément à supprimer (ex: "US-01", "SC-05", "EX-FON-01")
            """
            valid_types = ["requirements", "user_stories", "tests"]
            if item_type not in valid_types:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ Type invalide: {item_type}. Types valides: {', '.join(valid_types)}",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )

            existing = runtime.state.get(item_type) or []
            filtered = [item for item in existing if item.get("id") != item_id]

            if len(filtered) == len(existing):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"⚠️ Élément {item_id} non trouvé dans {item_type}",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )

            type_labels = {
                "requirements": "exigence",
                "user_stories": "User Story",
                "tests": "test",
            }

            return Command(
                update={
                    item_type: filtered,
                    "messages": [
                        ToolMessage(
                            f"✓ {type_labels[item_type]} {item_id} supprimée",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return remove_item

    # Export tools

    def _format_requirements_markdown(self, requirements: list[dict]) -> str:
        """Convert requirements list to markdown format."""
        lines = []
        for req in requirements:
            lines.append(
                f"### {req.get('id', 'N/A')}: {req.get('title', 'Sans titre')}"
            )
            lines.append(f"- **Priorité:** {req.get('priority', 'N/A')}")
            lines.append(f"- **Description:** {req.get('description', '')}")
            lines.append("")
        return "\n".join(lines)

    def _format_user_stories_markdown(self, user_stories: list[dict]) -> str:
        """Convert user stories list to markdown format."""
        lines = []
        for story in user_stories:
            lines.append(
                f"### {story.get('id', 'N/A')}: {story.get('summary', 'Sans titre')}"
            )
            lines.append(f"- **Type:** {story.get('issue_type', 'Story')}")
            lines.append(f"- **Priorité:** {story.get('priority', 'N/A')}")
            if story.get("epic_name"):
                lines.append(f"- **Epic:** {story.get('epic_name')}")
            if story.get("requirement_ids"):
                req_ids = story.get("requirement_ids", [])
                if isinstance(req_ids, list):
                    lines.append(f"- **Exigences:** {', '.join(req_ids)}")
                else:
                    lines.append(f"- **Exigences:** {req_ids}")
            if story.get("story_points"):
                lines.append(f"- **Story Points:** {story.get('story_points')}")
            if story.get("labels"):
                labels = story.get("labels", [])
                if isinstance(labels, list):
                    lines.append(f"- **Labels:** {', '.join(labels)}")
                else:
                    lines.append(f"- **Labels:** {labels}")
            lines.append("")
            lines.append(f"**Description:** {story.get('description', '')}")
            lines.append("")
            acceptance_criteria = story.get("acceptance_criteria", [])
            if acceptance_criteria:
                lines.append("**Critères d'acceptation:**")
                for criterion in acceptance_criteria:
                    if isinstance(criterion, dict):
                        lines.append(f"- **{criterion.get('scenario', 'Scénario')}**")
                        for step in criterion.get("steps", []):
                            lines.append(f"  - {step}")
                    else:
                        lines.append(f"- {criterion}")
            lines.append("")
        return "\n".join(lines)

    def _format_tests_markdown(self, tests: list[dict]) -> str:
        """Convert tests list to markdown format."""
        lines = []
        for test in tests:
            lines.append(
                f"### {test.get('id', 'N/A')}: {test.get('name', 'Sans titre')}"
            )
            if test.get("user_story_id"):
                lines.append(f"- **User Story:** {test.get('user_story_id')}")
            if test.get("priority"):
                lines.append(f"- **Priorité:** {test.get('priority')}")
            if test.get("test_type"):
                lines.append(f"- **Type:** {test.get('test_type')}")
            lines.append("")
            if test.get("description"):
                lines.append(f"**Description:** {test.get('description')}")
                lines.append("")
            if test.get("preconditions"):
                lines.append(f"**Préconditions:** {test.get('preconditions')}")
                lines.append("")
            steps = test.get("steps", [])
            if steps:
                lines.append("**Étapes:**")
                for i, step in enumerate(steps, 1):
                    lines.append(f"{i}. {step}")
                lines.append("")
            if test.get("test_data"):
                lines.append(f"**Données de test:** {test.get('test_data')}")
                lines.append("")
            if test.get("expected_result"):
                lines.append(f"**Résultat attendu:** {test.get('expected_result')}")
            lines.append("")
        return "\n".join(lines)

    async def _generate_markdown_file(self, state: dict) -> LinkPart | None:
        """Generate a markdown file from state and return a download link."""
        requirements = state.get("requirements")
        user_stories = state.get("user_stories")
        tests = state.get("tests")

        # If nothing was generated, return None
        if not any([requirements, user_stories, tests]):
            return None

        sections = []
        sections.append("# Livrables Projet\n")
        sections.append(f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*\n")

        if requirements:
            sections.append("---\n")
            sections.append("## Exigences\n")
            sections.append(self._format_requirements_markdown(requirements))
            sections.append("\n")

        if user_stories:
            sections.append("---\n")
            sections.append("## User Stories\n")
            sections.append(self._format_user_stories_markdown(user_stories))
            sections.append("\n")

        if tests:
            sections.append("---\n")
            sections.append("## Scénarios de Tests\n")
            sections.append(self._format_tests_markdown(tests))
            sections.append("\n")

        content = "\n".join(sections)

        # Create temp file with markdown content
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".md", prefix="livrables_", mode="w", encoding="utf-8"
        ) as f:
            f.write(content)
            output_path = Path(f.name)

        # Upload to user storage
        user_id = self.get_end_user_id()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_key = f"{user_id}_livrables_{timestamp}.md"

        with open(output_path, "rb") as f_out:
            upload_result = await self.upload_user_asset(
                key=final_key,
                file_content=f_out,
                filename=f"Livrables_{timestamp}.md",
                content_type="text/markdown",
                user_id_override=user_id,
            )

        # Clean up temp file
        output_path.unlink(missing_ok=True)

        # Build download URL
        download_url = self.get_asset_download_url(
            asset_key=upload_result.key, scope="user"
        )

        return LinkPart(
            href=download_url,
            title=f"📥 Télécharger {upload_result.file_name}",
            kind=LinkKind.download,
            mime="text/markdown",
        )

    def get_export_tool(self):
        """Tool that exports all generated deliverables to a markdown file."""

        @tool
        async def export_deliverables(runtime: ToolRuntime):
            """
            Exporte tous les livrables générés (exigences, user stories, tests) dans un fichier Markdown téléchargeable.

            IMPORTANT: Appelle cet outil à la fin du workflow pour fournir à l'utilisateur
            un fichier contenant tous les livrables générés.

            Returns:
                Lien de téléchargement du fichier Markdown
            """
            # Check if we have any generated content
            has_content = any(
                [
                    runtime.state.get("requirements"),
                    runtime.state.get("user_stories"),
                    runtime.state.get("tests"),
                ]
            )

            if not has_content:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Aucun livrable n'a été généré. Veuillez d'abord générer des exigences, user stories ou tests.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            link_part = await self._generate_markdown_file(runtime.state)
            if link_part:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=f"✓ Fichier exporté avec succès: [{link_part.title}]({link_part.href})",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "❌ Erreur lors de la génération du fichier.",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return export_deliverables

    def get_export_jira_csv_tool(self):
        """Tool that exports generated user stories to CSV format for Jira import."""

        @tool
        async def export_jira_csv(runtime: ToolRuntime):
            """
            Exporte les User Stories générées dans un fichier CSV compatible avec l'import Jira.

            IMPORTANT: Cet outil nécessite que generate_user_stories ait été appelé au préalable.

            Le fichier CSV généré contient les colonnes standard Jira:
            - Summary, Description, IssueType, Priority, Epic Name, Epic Link, Story Points, Labels

            Note: Les critères d'acceptation sont ajoutés à la Description car ce n'est pas un champ standard Jira.

            Returns:
                Lien de téléchargement du fichier CSV
            """
            user_stories = runtime.state.get("user_stories")
            if not user_stories:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Aucune User Story n'a été générée. Veuillez d'abord appeler generate_user_stories.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Build CSV with Jira-compatible field names
            # See: https://support.atlassian.com/jira-cloud-administration/docs/import-data-from-a-csv-file/
            output = io.StringIO()
            fieldnames = [
                "Summary",
                "Description",
                "IssueType",
                "Priority",
                "Epic Name",
                "Epic Link",
                "Story Points",
                "Labels",
                "Requirement IDs",
            ]
            writer = csv.DictWriter(
                output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
            )
            writer.writeheader()

            for story in user_stories:
                # Append acceptance criteria to description since it's not a standard Jira field
                description = story.get("description", "")
                acceptance_criteria = story.get("acceptance_criteria", [])
                if acceptance_criteria:
                    criteria_lines = []
                    for c in acceptance_criteria:
                        if isinstance(c, dict):
                            criteria_lines.append(f"*{c.get('scenario', 'Scénario')}*")
                            for step in c.get("steps", []):
                                criteria_lines.append(f"  - {step}")
                        else:
                            criteria_lines.append(f"- {c}")
                    criteria_text = "\n".join(criteria_lines)
                    description = (
                        f"{description}\n\n*Critères d'acceptation:*\n{criteria_text}"
                    )

                # Convert labels list to comma-separated string
                labels = story.get("labels", [])
                if isinstance(labels, list):
                    labels = ",".join(labels)

                # Convert requirement_ids list to comma-separated string
                requirement_ids = story.get("requirement_ids", [])
                if isinstance(requirement_ids, list):
                    requirement_ids = ",".join(requirement_ids)

                writer.writerow(
                    {
                        "Summary": story.get("summary", story.get("id", "")),
                        "Description": description,
                        "IssueType": story.get("issue_type", "Story"),
                        "Priority": story.get("priority", "Medium"),
                        "Epic Name": story.get("epic_name", "")
                        if story.get("issue_type") == "Epic"
                        else "",
                        "Epic Link": story.get("epic_name", "")
                        if story.get("issue_type") != "Epic"
                        else "",
                        "Story Points": story.get("story_points", ""),
                        "Labels": labels,
                        "Requirement IDs": requirement_ids,
                    }
                )

            csv_content = output.getvalue()

            # Create temp file
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".csv",
                prefix="jira_import_",
                mode="w",
                encoding="utf-8",
            ) as f:
                f.write(csv_content)
                output_path = Path(f.name)

            # Upload to user storage
            user_id = self.get_end_user_id()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_key = f"{user_id}_jira_import_{timestamp}.csv"

            with open(output_path, "rb") as f_out:
                upload_result = await self.upload_user_asset(
                    key=final_key,
                    file_content=f_out,
                    filename=f"jira_import_{timestamp}.csv",
                    content_type="text/csv",
                    user_id_override=user_id,
                )

            # Clean up temp file
            output_path.unlink(missing_ok=True)

            # Build download URL
            download_url = self.get_asset_download_url(
                asset_key=upload_result.key, scope="user"
            )

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"✓ Fichier CSV Jira exporté avec succès: [{upload_result.file_name}]({download_url})\n\n"
                            f"**Pour importer dans Jira:**\n"
                            f"1. Allez dans votre projet Jira\n"
                            f"2. Menu **Project settings** > **External system import**\n"
                            f"3. Sélectionnez **CSV** et uploadez le fichier",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return export_jira_csv

    # Create Agent

    def get_compiled_graph(self) -> CompiledStateGraph:
        # Bulk generation tools
        requirements_tool = self.get_requirements_tool()
        user_stories_tool = self.get_user_stories_tool()
        tests_tool = self.get_tests_tool()
        # Single-item add/remove tools
        add_requirement_tool = self.get_add_requirement_tool()
        add_user_story_tool = self.get_add_user_story_tool()
        add_test_tool = self.get_add_test_tool()
        remove_item_tool = self.get_remove_item_tool()
        # Export tools
        export_tool = self.get_export_tool()
        export_jira_csv_tool = self.get_export_jira_csv_tool()

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
            checkpointer=self.streaming_memory,
            state_schema=CustomState,
        )
