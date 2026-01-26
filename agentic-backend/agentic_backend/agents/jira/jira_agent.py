import csv
import io
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from jsonschema import Draft7Validator
from langchain.agents import AgentState, create_agent
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agentic_backend.agents.jira.jsonschema import (
    requirementsSchema,
    testsSchema,
    testTitlesSchema,
    userStoriesSchema,
    userStoryTitlesSchema,
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


class CustomState(AgentState):
    requirements: list[dict]  # Validated against requirementsSchema
    user_story_titles: list[dict]  # List of {id, title, epic_name} for batch generation
    user_stories: list[dict]  # Validated against userStoriesSchema
    test_titles: list[
        dict
    ]  # List of {id, title, user_story_id, test_type} for batch generation
    tests: list[dict]  # Validated against testsSchema


# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
TUNING = AgentTuning(
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

## WORKFLOW

**1. Recherche documentaire (MCP)**
Stratégie obligatoire :
- D'abord découvrir : recherche "objectif projet", "contexte", "périmètre", "acteurs"
- Identifier le domaine métier à partir des résultats
- Puis cibler avec le vocabulaire DÉCOUVERT (jamais inventé)

**2. Génération des exigences (si demandé)**
- generate_requirements(context_summary) → exigences fonctionnelles et non-fonctionnelles

**3. Génération des User Stories en 2 étapes (si demandé)**
- generate_user_story_titles(context_summary, quantity=10) → génère les titres pour éviter doublons
- generate_user_stories(batch_size=5) → génère les stories complètes par lots de 3-5
- Répéter generate_user_stories() jusqu'à ce que toutes les stories soient générées

**4. Génération des tests en 2 étapes (si demandé)**
- generate_test_titles() → génère les titres de tests pour toutes les User Stories
- generate_tests(batch_size=5) → génère les tests complets par lots
- Répéter generate_tests() jusqu'à ce que tous les tests soient générés

**5. Export (OBLIGATOIRE)**
- export_deliverables() → fichier Markdown
- export_jira_csv() → CSV pour import Jira

## RÈGLES

1. **Jamais afficher le contenu** : uniquement confirmer (ex: "5 User Stories générées")
2. **Toujours exporter** : appeler export_deliverables ou export_jira_csv à la fin
3. **update_state** : UNIQUEMENT pour du contenu fourni par l'utilisateur. JAMAIS comme solution de repli quand generate_* échoue.
4. **Erreurs de validation** : Si generate_* échoue, corrige le format JSON et réessaie generate_*. Ne pas utiliser update_state.""",
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


@expose_runtime_source("agent.Jim")
class JiraAgent(AgentFlow):
    tuning = TUNING
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

    def _parse_and_validate_json(
        self,
        content: str,
        schema: dict,
        tool_call_id: str,
    ) -> tuple[list[dict] | None, Command | None]:
        """
        Parse JSON content from LLM response, clean markdown formatting, and validate against schema.

        Args:
            content: Raw LLM response content (may include markdown code blocks)
            schema: JSON schema to validate against (must be an array schema with 'items')
            tool_call_id: Tool call ID for error messages

        Returns:
            Tuple of (parsed_data, error_command). If successful, error_command is None.
            If failed, parsed_data is None and error_command contains the error.
        """
        clean_data = content.strip()

        # Remove markdown code blocks if present
        if clean_data.startswith("```"):
            clean_data = re.sub(r"^```(?:json)?\n?", "", clean_data)
            clean_data = re.sub(r"\n?```$", "", clean_data)

        # Fix invalid JSON escape sequences that are not valid in JSON
        # JSON only allows: \" \\ \/ \b \f \n \r \t \uXXXX
        # LLMs sometimes produce \' which is invalid in JSON - replace with just '
        clean_data = clean_data.replace("\\'", "'")

        try:
            data = json.loads(clean_data)
        except json.JSONDecodeError:
            # Try to fix unescaped quotes inside strings and retry
            # LLMs often produce: "text": "Message 'pour "Contrôle"'"
            # Should be: "text": "Message 'pour \"Contrôle\"'"
            result = []
            i = 0
            in_string = False
            while i < len(clean_data):
                char = clean_data[i]
                if char == "\\" and i + 1 < len(clean_data):
                    result.append(char)
                    result.append(clean_data[i + 1])
                    i += 2
                    continue
                if char == '"':
                    if not in_string:
                        in_string = True
                        result.append(char)
                    else:
                        # Check if this quote ends the string or is inside it
                        j = i + 1
                        while j < len(clean_data) and clean_data[j] in " \t\n\r":
                            j += 1
                        # If followed by : , ] } or end, it's a real delimiter
                        if j >= len(clean_data) or clean_data[j] in ":,]}":
                            in_string = False
                            result.append(char)
                        else:
                            # Unescaped quote inside string - escape it
                            result.append('\\"')
                else:
                    result.append(char)
                i += 1
            fixed_data = "".join(result)

            try:
                data = json.loads(fixed_data)
                logger.info("[JiraAgent] Fixed unescaped quotes in JSON")
            except json.JSONDecodeError as e:
                return None, Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ Erreur de parsing JSON: {e}. Veuillez réessayer.",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )

        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors(data))
        if errors:
            error_msgs = [f"{e.path}: {e.message}" for e in errors[:3]]
            return None, Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"❌ Erreur de validation JSON: {'; '.join(error_msgs)}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        return data, None

    async def astream_updates(self, state, *, config, **kwargs):
        """
        Override to add validation retry logic.
        If the agent generates a validation error, automatically retry up to 2 times.

        IMPORTANT: Events are yielded in real-time so the UI sees tool calls as they happen.
        Only on validation error do we suppress further events and retry silently.
        """
        max_retries = 2
        current_state = state

        for attempt in range(max_retries + 1):
            logger.info(
                f"[JiraAgent] Execution attempt {attempt + 1}/{max_retries + 1}"
            )

            final_state_messages = []
            is_last_attempt = attempt >= max_retries

            async for event in super().astream_updates(
                current_state,  # type: ignore
                config=config,
                **kwargs,
            ):
                # Track messages for validation error detection
                for node_name, node_data in event.items():
                    if isinstance(node_data, dict) and "messages" in node_data:
                        final_state_messages = node_data["messages"]

                # Always yield events in real-time so UI sees tool calls
                yield event

            has_jira_validation_error = False
            # Check the last few messages for tool error messages
            for msg in reversed(final_state_messages[-3:]):
                content = getattr(msg, "content", "")
                if isinstance(content, str) and (
                    "❌ Erreur de validation JSON" in content
                    or "❌ Erreur de parsing JSON" in content
                    or "❌ Erreur de validation" in content
                ):
                    has_jira_validation_error = True

            # Check if there's a validation error in the final state
            if has_jira_validation_error:
                if not is_last_attempt:
                    logger.warning(
                        f"[JiraAgent] Validation error detected on attempt {attempt + 1}. "
                        f"Retrying automatically ({attempt + 1}/{max_retries} retries used)..."
                    )
                    # Update state with the error message for retry
                    current_state = {"messages": final_state_messages}
                    continue
                else:
                    logger.error(
                        f"[JiraAgent] Validation errors persist after {max_retries} retries. "
                        f"Giving up."
                    )
                    break
            else:
                # No validation error - success!
                if attempt > 0:
                    logger.info(
                        f"[JiraAgent] Succeeded after {attempt} retry(ies). Validation passed."
                    )
                break

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

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Format JSON attendu:
[
  {{
    "id": "EX-FON-01",
    "title": "Titre court de l'exigence",
    "description": "Description détaillée de l'exigence",
    "priority": "Haute"
  }}
]

Règles:
- id: Identifiant unique (EX-FON-XXX pour fonctionnelle, EX-NFON-XXX pour non-fonctionnelle)
- title: Titre concis
- description: Description détaillée et testable
- priority: "Haute", "Moyenne" ou "Basse"

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=requirements_prompt.format(context_summary=context_summary)
                )
            ]

            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            requirements, error_cmd = self._parse_and_validate_json(
                str(response.content), requirementsSchema, runtime.tool_call_id
            )
            if error_cmd:
                return error_cmd

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

    def get_user_story_titles_tool(self):
        """Tool that generates user story titles for batch generation"""

        @tool
        async def generate_user_story_titles(
            runtime: ToolRuntime, context_summary: str, quantity: int = 20
        ):
            """
            Génère une liste de titres de User Stories pour une génération par lots.

            Cette étape permet de:
            1. Définir le périmètre complet des User Stories à générer
            2. Éviter les doublons et chevauchements

            IMPORTANT:
            - AVANT d'appeler cet outil, tu DOIS faire une recherche documentaire avec les outils MCP
            - Le context_summary doit contenir les informations extraites des documents (min 200 caractères)
            - Après cet outil, utilise generate_user_stories() pour générer les stories complètes

            Args:
                context_summary: Résumé du contexte projet extrait des documents (min 200 caractères)
                quantity: Nombre de User Stories à générer (défaut: 20)

            Returns:
                Message de confirmation avec la liste des titres générés
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

            titles_prompt = """Tu es un Product Owner expert. Génère une liste de {quantity} titres de User Stories.

Contexte projet extrait des documents:
{context_summary}

{requirements_section}

{existing_stories_section}

**Objectif:** Créer une liste cohérente de titres de User Stories qui:
- Couvrent l'ensemble du périmètre fonctionnel
- Évitent les doublons et chevauchements
- Sont regroupées par Epic logique
- Suivent une progression fonctionnelle cohérente

**Règles:**
- Chaque titre doit être concis (max 80 caractères)
- Utiliser des verbes d'action (Créer, Afficher, Modifier, Supprimer, etc.)
- Regrouper les stories liées sous le même Epic
- **NE PAS générer de titres pour des fonctionnalités déjà couvertes par les User Stories existantes**
- Les IDs doivent continuer la séquence existante (ex: si US-01 existe, commencer à US-02)

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Format JSON attendu:
[
  {{
    "id": "US-{next_id_hint}",
    "title": "Créer un compte utilisateur",
    "epic_name": "Gestion des utilisateurs"
  }}
]

Génère exactement {quantity} NOUVEAUX titres de User Stories (en plus des existantes).

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

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
                # Extract numeric parts from IDs like "US-01", "US-02"
                max_num = 0
                for id_str in all_existing_ids:
                    match = re.search(r"US-(\d+)", id_str)
                    if match:
                        max_num = max(max_num, int(match.group(1)))
                next_id_hint = f"{max_num + 1:02d}"

            if existing_stories or existing_titles:
                # Combine existing info for the prompt
                existing_info = []
                for story in existing_stories:
                    existing_info.append(
                        {
                            "id": story.get("id"),
                            "title": story.get("summary"),
                            "epic_name": story.get("epic_name"),
                        }
                    )
                # Add titles that don't have corresponding stories yet
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

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=titles_prompt.format(
                        context_summary=context_summary,
                        requirements_section=requirements_section,
                        existing_stories_section=existing_stories_section,
                        quantity=quantity,
                        next_id_hint=next_id_hint,
                    )
                )
            ]

            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            new_titles, error_cmd = self._parse_and_validate_json(
                str(response.content),
                userStoryTitlesSchema,
                runtime.tool_call_id,
            )
            if error_cmd:
                return error_cmd

            # Merge with existing titles (append new ones)
            all_titles = existing_titles + new_titles

            # Format new titles for display
            titles_display = "\n".join(
                f"  - {t['id']}: {t['title']} ({t['epic_name']})" for t in new_titles
            )

            # Build response message
            if existing_titles:
                msg = (
                    f"✓ {len(new_titles)} nouveaux titres de User Stories générés "
                    f"({len(all_titles)} au total):\n{titles_display}\n\n"
                    f"Appelle maintenant generate_user_stories() pour générer les User Stories complètes "
                    f"à partir de ces titres (par lots de 3-5 pour une meilleure qualité)."
                )
            else:
                msg = (
                    f"✓ {len(new_titles)} titres de User Stories générés:\n{titles_display}\n\n"
                    f"Appelle maintenant generate_user_stories() pour générer les User Stories complètes "
                    f"à partir de ces titres (par lots de 3-5 pour une meilleure qualité)."
                )

            return Command(
                update={
                    "user_story_titles": all_titles,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_user_story_titles

    def get_user_stories_tool(self):
        """Tool that generates user stories from titles in batches"""

        @tool
        async def generate_user_stories(
            runtime: ToolRuntime,
            context_summary: str = "",
            batch_size: int = 5,
            story_ids: list[str] | None = None,
        ):
            """
            Génère des User Stories complètes à partir des titres générés par generate_user_story_titles.

            WORKFLOW RECOMMANDÉ:
            1. Appeler generate_user_story_titles() pour générer les titres
            2. Appeler generate_user_stories() plusieurs fois avec batch_size=3-5
               jusqu'à ce que toutes les stories soient générées

            Args:
                context_summary: Résumé du contexte projet
                batch_size: Nombre de User Stories à générer par appel (défaut: 5)
                story_ids: Liste spécifique d'IDs à générer (optionnel, sinon prend le prochain batch)

            Returns:
                Message de confirmation avec le nombre de stories générées et restantes
            """
            # Get titles and existing stories
            all_titles = runtime.state.get("user_story_titles") or []
            existing_stories = runtime.state.get("user_stories") or []
            existing_ids = {s.get("id") for s in existing_stories}

            # Determine which titles to process
            if story_ids:
                # User specified specific IDs
                titles_to_process = [
                    t
                    for t in all_titles
                    if t["id"] in story_ids and t["id"] not in existing_ids
                ]
            else:
                # Get next batch of unprocessed titles
                pending_titles = [t for t in all_titles if t["id"] not in existing_ids]
                titles_to_process = pending_titles[:batch_size]

            if not titles_to_process:
                if not all_titles:
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    "❌ Aucun titre de User Story n'a été généré. "
                                    "Appelle d'abord generate_user_story_titles() pour définir les titres.",
                                    tool_call_id=runtime.tool_call_id,
                                ),
                            ],
                        }
                    )
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"✓ Toutes les User Stories ont déjà été générées ({len(existing_stories)} au total). "
                                f"Appelle export_deliverables() pour exporter les livrables.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

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

**Métadonnées:**
- **Estimation:** Fibonacci (1, 2, 3, 5, 8, 13, 21)
- **Priorisation:** High, Medium, Low

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide.

Format JSON attendu:
[
  {{
    "id": "US-01",
    "summary": "Titre de la User Story",
    "description": "En tant que [persona], je veux [action], afin de [bénéfice]",
    "issue_type": "Story",
    "priority": "High",
    "epic_name": "Nom de l'Epic",
    "story_points": 3,
    "labels": ["label1"],
    "acceptance_criteria": [
      {{
        "scenario": "Nom du scénario de test",
        "steps": [
          "Étant donné que [contexte]",
          "Quand [action]",
          "Alors [résultat attendu]"
        ]
      }}
    ]
  }}
]

IMPORTANT: Génère EXACTEMENT {count} User Stories correspondant aux titres fournis.
Utilise les mêmes IDs et epic_name que dans les titres.

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            # Build context section
            context_section = ""
            if context_summary:
                context_section = f"Contexte projet:\n{context_summary}"

            # Build requirements section
            requirements_section = ""
            requirements = runtime.state.get("requirements")
            if requirements:
                requirements_section = f"""
Exigences à respecter:
{json.dumps(requirements, ensure_ascii=False, indent=2)}
"""

            model = get_default_chat_model()
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

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            new_stories, error_cmd = self._parse_and_validate_json(
                str(response.content),
                userStoriesSchema,
                runtime.tool_call_id,
            )

            if error_cmd:
                return error_cmd

            # Merge with existing stories
            all_stories = existing_stories + new_stories
            remaining = len(all_titles) - len(all_stories)

            # Build response message
            if remaining > 0:
                next_batch = min(batch_size, remaining)
                msg = (
                    f"✓ {len(new_stories)} User Stories générées ({len(all_stories)}/{len(all_titles)} au total). "
                    f"Reste {remaining} stories à générer. "
                    f"Appelle generate_user_stories() pour générer le prochain lot de {next_batch}."
                )
            else:
                msg = (
                    f"✓ {len(new_stories)} User Stories générées. "
                    f"Toutes les {len(all_stories)} User Stories sont maintenant complètes! "
                    f"Appelle export_deliverables() pour exporter les livrables."
                )

            return Command(
                update={
                    "user_stories": all_stories,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_user_stories

    def get_test_titles_tool(self):
        """Tool that generates test titles for batch generation"""

        @tool
        async def generate_test_titles(runtime: ToolRuntime):
            """
            Génère une liste de titres de tests pour toutes les User Stories.

            Cette étape permet de:
            1. Définir le périmètre complet des tests à générer
            2. Éviter les doublons et assurer une couverture complète
            3. Planifier les types de tests (Nominal, Limite, Erreur) pour chaque story

            IMPORTANT:
            - AVANT d'appeler cet outil, des User Stories doivent avoir été générées
            - Après cet outil, utilise generate_tests() pour générer les tests complets

            Returns:
                Message de confirmation avec la liste des titres générés
            """
            # Get user stories
            user_stories = runtime.state.get("user_stories") or []
            if not user_stories:
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

            # Get existing test titles and tests to avoid duplicates
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
                next_id_hint = f"{max_num + 1:03d}"

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

Pour chaque User Story, génère environ 3 titres de tests couvrant:
- **Nominal**: Cas de test du parcours nominal (happy path)
- **Limite**: Cas de test aux limites (valeurs frontières, listes vides/longues)
- **Erreur**: Cas de test d'erreur (validations, erreurs techniques)

Tu peux varier le nombre de tests selon la complexité de la story (minimum 2, maximum 5 par story).

**Règles:**
- Chaque titre doit être concis et descriptif (max 80 caractères)
- Les IDs doivent suivre le format SC-XXX (commencer à SC-{next_id_hint})
- Chaque titre doit référencer sa User Story via user_story_id

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Format JSON attendu:
[
  {{
    "id": "SC-{next_id_hint}",
    "title": "Vérifier la création d'un compte avec des données valides",
    "user_story_id": "US-01",
    "test_type": "Nominal"
  }},
  {{
    "id": "SC-{next_id_hint_plus_1}",
    "title": "Vérifier le rejet d'un email invalide",
    "user_story_id": "US-01",
    "test_type": "Erreur"
  }}
]

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            # Calculate next_id_hint_plus_1 for the example
            next_id_hint_plus_1 = f"{int(next_id_hint) + 1:03d}"

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=titles_prompt.format(
                        user_stories_json=json.dumps(
                            user_stories, ensure_ascii=False, indent=2
                        ),
                        existing_titles_section=existing_titles_section,
                        next_id_hint=next_id_hint,
                        next_id_hint_plus_1=next_id_hint_plus_1,
                    )
                )
            ]

            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            new_titles, error_cmd = self._parse_and_validate_json(
                str(response.content),
                testTitlesSchema,
                runtime.tool_call_id,
            )
            if error_cmd:
                return error_cmd

            # Merge with existing titles (append new ones)
            all_titles = existing_titles + new_titles

            # Count tests per story for display
            tests_per_story = {}
            for title in new_titles:
                story_id = title.get("user_story_id", "unknown")
                tests_per_story[story_id] = tests_per_story.get(story_id, 0) + 1

            # Build response message
            if existing_titles:
                msg = (
                    f"✓ {len(new_titles)} nouveaux titres de tests générés "
                    f"({len(all_titles)} au total) pour {len(tests_per_story)} User Stories.\n\n"
                    f"Appelle maintenant generate_tests() pour générer les tests complets "
                    f"à partir de ces titres (par lots de 5 pour une meilleure qualité)."
                )
            else:
                msg = (
                    f"✓ {len(new_titles)} titres de tests générés pour {len(tests_per_story)} User Stories.\n\n"
                    f"Appelle maintenant generate_tests() pour générer les tests complets "
                    f"à partir de ces titres (par lots de 5 pour une meilleure qualité)."
                )

            return Command(
                update={
                    "test_titles": all_titles,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_test_titles

    def get_tests_tool(self):
        """Tool that generates test scenarios from titles in batches"""

        @tool
        async def generate_tests(
            runtime: ToolRuntime,
            batch_size: int = 5,
            test_ids: list[str] | None = None,
            jdd: str = "",
        ):
            """
            Génère des tests complets à partir des titres générés par generate_test_titles.

            WORKFLOW RECOMMANDÉ:
            1. Appeler generate_test_titles() pour générer les titres
            2. Appeler generate_tests() plusieurs fois avec batch_size=5
               jusqu'à ce que tous les tests soient générés

            Args:
                batch_size: Nombre de tests à générer par appel (défaut: 5)
                test_ids: Liste spécifique d'IDs de tests à générer (optionnel, sinon prend le prochain batch)
                jdd: Jeu de Données pour les personas (optionnel)

            Returns:
                Message de confirmation avec le nombre de tests générés et restants
            """
            # Get test titles and existing tests
            all_titles = runtime.state.get("test_titles") or []
            existing_tests = runtime.state.get("tests") or []
            all_stories = runtime.state.get("user_stories") or []
            existing_test_ids = {t.get("id") for t in existing_tests}

            # Create a map of stories by ID for quick lookup
            stories_by_id = {s.get("id"): s for s in all_stories}

            # Determine which titles to process
            if test_ids:
                # User specified specific IDs
                titles_to_process = [
                    t
                    for t in all_titles
                    if t["id"] in test_ids and t["id"] not in existing_test_ids
                ]
            else:
                # Get next batch of unprocessed titles
                pending_titles = [
                    t for t in all_titles if t["id"] not in existing_test_ids
                ]
                titles_to_process = pending_titles[:batch_size]

            if not titles_to_process:
                if not all_titles:
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    "❌ Aucun titre de test n'a été généré. "
                                    "Appelle d'abord generate_test_titles() pour définir les titres.",
                                    tool_call_id=runtime.tool_call_id,
                                ),
                            ],
                        }
                    )
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"✓ Tous les tests ont déjà été générés ({len(existing_tests)} au total). "
                                f"Appelle export_deliverables() pour exporter les livrables.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

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

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide.

Format JSON attendu:
[
  {{
    "id": "SC-01",
    "name": "Titre du scénario de test",
    "user_story_id": "US-01",
    "description": "Brève explication de ce que le scénario teste",
    "preconditions": "Les états ou données nécessaires avant l'exécution du test",
    "steps": [
      "Étant donné que [contexte]",
      "Lorsque [action]",
      "Alors [résultat attendu]"
    ],
    "test_data": ["email: test@example.com", "password: Test123!"],
    "priority": "Haute",
    "test_type": "Nominal",
    "expected_result": "Le résultat final attendu du test"
  }}
]

Règles:
- Génère EXACTEMENT {count} tests correspondant aux titres fournis
- Utilise les mêmes IDs, user_story_id et test_type que dans les titres
- priority: "Haute", "Moyenne" ou "Basse"

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            model = get_default_chat_model()
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

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            new_tests, error_cmd = self._parse_and_validate_json(
                str(response.content),
                testsSchema,
                runtime.tool_call_id,
            )
            if error_cmd:
                return error_cmd

            # Merge with existing tests
            all_tests = existing_tests + new_tests
            remaining = len(all_titles) - len(all_tests)

            # Build response message
            if remaining > 0:
                next_batch = min(batch_size, remaining)
                msg = (
                    f"✓ {len(new_tests)} tests générés ({len(all_tests)}/{len(all_titles)} au total). "
                    f"Reste {remaining} tests à générer. "
                    f"Appelle generate_tests() pour générer le prochain lot de {next_batch}."
                )
            else:
                msg = (
                    f"✓ {len(new_tests)} tests générés. "
                    f"Tous les {len(all_tests)} tests sont maintenant complets! "
                    f"Appelle export_deliverables() pour exporter les livrables."
                )

            return Command(
                update={
                    "tests": all_tests,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_tests

    def get_update_state_tool(self):
        """Tool to directly update state with user-provided content"""

        @tool
        async def update_state(
            runtime: ToolRuntime,
            item_type: str,
            items: list[dict] | None = None,
            mode: str = "append",
            ids_to_remove: list[str] | None = None,
        ):
            """
            Met à jour l'état avec des éléments fournis par l'utilisateur.

            Utilise cet outil quand l'utilisateur fournit directement du contenu
            (exigences, user stories ou tests) à ajouter, remplacer ou supprimer.

            Args:
                item_type: Type d'élément - "requirements", "user_stories", ou "tests"
                items: Liste d'éléments au format JSON (requis pour append/replace)
                mode: "append" pour ajouter, "replace" pour tout remplacer, "remove" pour supprimer
                ids_to_remove: Liste d'IDs à supprimer (requis pour mode "remove")

            Returns:
                Message de confirmation avec le nombre total d'éléments
            """
            # Block update_state if there's a recent validation error from generate_* tools
            # This prevents the LLM from using update_state as a fallback
            if mode != "remove":
                messages = runtime.state.get("messages") or []
                for msg in reversed(messages[-10:]):
                    content = getattr(msg, "content", "")
                    if isinstance(content, str) and (
                        "❌ Erreur de validation JSON" in content
                        or "❌ Erreur de parsing JSON" in content
                    ):
                        return Command(
                            update={
                                "messages": [
                                    ToolMessage(
                                        "❌ update_state ne peut pas être utilisé après une erreur de validation. "
                                        "Tu dois corriger le format JSON et réessayer l'outil generate_* approprié "
                                        "(generate_requirements, generate_user_stories, ou generate_tests).",
                                        tool_call_id=runtime.tool_call_id,
                                    )
                                ]
                            }
                        )

            # Validate item_type
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

            # Select schema based on type
            schema_map = {
                "requirements": requirementsSchema,
                "user_stories": userStoriesSchema,
                "tests": testsSchema,
            }

            # Translate item_type for French message
            type_labels = {
                "requirements": "exigences",
                "user_stories": "user stories",
                "tests": "tests",
            }

            existing = runtime.state.get(item_type) or []

            # Handle remove mode
            if mode == "remove":
                if not ids_to_remove:
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    "❌ ids_to_remove est requis pour le mode 'remove'",
                                    tool_call_id=runtime.tool_call_id,
                                )
                            ]
                        }
                    )
                # Filter out items with matching IDs
                final_items = [
                    item for item in existing if item.get("id") not in ids_to_remove
                ]
                removed_count = len(existing) - len(final_items)
                action_msg = f"suppression de {removed_count}"
            else:
                # For append/replace, items are required
                if items is None:
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    f"❌ items est requis pour le mode '{mode}'",
                                    tool_call_id=runtime.tool_call_id,
                                )
                            ]
                        }
                    )

                # Validate items against schema
                validator = Draft7Validator(schema_map[item_type])
                errors = list(validator.iter_errors(items))
                if errors:
                    error_msgs = [f"{e.path}: {e.message}" for e in errors[:3]]
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    f"❌ Erreur de validation: {'; '.join(error_msgs)}",
                                    tool_call_id=runtime.tool_call_id,
                                )
                            ]
                        }
                    )

                if mode == "replace":
                    final_items = items
                    action_msg = f"remplacé par {len(items)}"
                else:  # append
                    final_items = existing + items
                    action_msg = f"ajout de {len(items)}"

            return Command(
                update={
                    item_type: final_items,
                    "messages": [
                        ToolMessage(
                            f"✓ État mis à jour: {len(final_items)} {type_labels[item_type]} ({action_msg}). "
                            f"Si tu as terminé de générer tous les livrables demandés par l'utilisateur, "
                            f"appelle maintenant export_deliverables() pour fournir le lien de téléchargement.",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return update_state

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

    def get_compiled_graph(self) -> CompiledStateGraph:
        requirements_tool = self.get_requirements_tool()
        user_story_titles_tool = self.get_user_story_titles_tool()
        user_stories_tool = self.get_user_stories_tool()
        test_titles_tool = self.get_test_titles_tool()
        tests_tool = self.get_tests_tool()
        update_state_tool = self.get_update_state_tool()
        export_tool = self.get_export_tool()
        export_jira_csv_tool = self.get_export_jira_csv_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                requirements_tool,
                user_story_titles_tool,
                user_stories_tool,
                test_titles_tool,
                tests_tool,
                update_state_tool,
                export_tool,
                export_jira_csv_tool,
                *self.mcp.get_tools(),
            ],
            checkpointer=self.streaming_memory,
            state_schema=CustomState,
        )
