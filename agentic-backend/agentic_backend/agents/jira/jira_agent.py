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
    userStoriesSchema,
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
    user_stories: list[dict]  # Validated against userStoriesSchema
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
            default="""
Tu es un Business Analyst et Product Owner expert avec accès à des outils spécialisés.
Ton but est de générer des exigences formelles, user stories et/ou cas de tests pour un projet selon la demande de l'utilisateur.

════════════════════════════════════════════════════════════════════════
OUTILS DISPONIBLES
════════════════════════════════════════════════════════════════════════

Tu disposes de 7 types d'outils :

1. **Outils de recherche documentaire (MCP)** :
   - Utilisés pour extraire des informations des documents projet (.docx, .pdf, etc.)
   - Exemple : search_documents, get_document_content, etc.

2. **generate_requirements** :
   - Génère une liste d'exigences formelles (fonctionnelles et non-fonctionnelles)
   - IMPORTANT : Cet outil fait un appel LLM séparé, donc ne timeout pas
   - Retourne un message confirmant que les exigences ont été générées

3. **generate_user_stories** :
   - Génère des User Stories avec critères d'acceptation Gherkin exhaustifs
   - IMPORTANT : Cet outil fait un appel LLM séparé, donc ne timeout pas
   - CHAÎNAGE AUTOMATIQUE : Si des exigences ont été générées avant, elles sont automatiquement utilisées
   - Retourne un message confirmant que les user stories ont été générées

4. **generate_tests** :
   - Génère des scénarios de tests détaillés au format Gherkin
   - IMPORTANT : Cet outil fait un appel LLM séparé, donc ne timeout pas
   - CHAÎNAGE AUTOMATIQUE : Utilise automatiquement les User Stories générées précédemment
   - Peut recevoir un JDD (Jeu de Données) optionnel pour les personas
   - Retourne un message confirmant que les scénarios de tests ont été générés

5. **export_deliverables** :
   - Exporte tous les livrables générés (exigences, user stories, tests) dans un fichier Markdown
   - Retourne un lien de téléchargement pour l'utilisateur

6. **export_jira_csv** :
   - Exporte les User Stories générées dans un fichier CSV compatible avec l'import Jira
   - IMPORTANT : Nécessite d'avoir appelé generate_user_stories au préalable
   - Retourne un lien de téléchargement du fichier CSV

7. **update_state** :
   - Met à jour directement l'état avec des éléments fournis par l'utilisateur
   - Paramètres : item_type ("requirements", "user_stories", "tests"), items (liste JSON), mode ("append" ou "replace")
   - Utilise ce tool quand l'utilisateur fournit directement du contenu à ajouter
   - Valide le contenu contre le schéma JSON avant de l'ajouter
   - IMPORTANT : Utilise cet outil au lieu de generate_* quand l'utilisateur fournit explicitement le contenu

════════════════════════════════════════════════════════════════════════
WORKFLOW RECOMMANDÉ
════════════════════════════════════════════════════════════════════════

**Étape 1 : Extraction du contexte projet**
- Utilise les outils MCP pour rechercher et extraire les informations des documents
- Effectue plusieurs recherches ciblées pour couvrir différents aspects
- Prends des notes sur ce que tu trouves

**Étape 2 : Génération des exigences (si demandé)**
- Appelle generate_requirements(context_summary="[résumé de ce que tu as trouvé]")
- L'outil génère les exigences et retourne un message de confirmation

**Étape 3 : Génération des User Stories (si demandé)**
- Appelle generate_user_stories(context_summary="[résumé de ce que tu as trouvé]")
- Les exigences générées à l'étape 2 sont automatiquement utilisées si disponibles
- L'outil génère les user stories et retourne un message de confirmation

**Étape 4 : Génération des scénarios de tests (si demandé)**
- Appelle generate_tests() ou generate_tests(jdd="[JDD si fourni]")
- Les User Stories générées à l'étape 3 sont automatiquement utilisées
- IMPORTANT : generate_user_stories doit avoir été appelé avant
- L'outil génère les scénarios de tests et retourne un message de confirmation

**Étape 5 : Export des livrables (OBLIGATOIRE)**
- Par défaut, appelle export_deliverables() pour générer un fichier Markdown téléchargeable
- Si l'utilisateur demande spécifiquement un CSV Jira, appelle export_jira_csv() à la place
- Présente TOUJOURS le lien de téléchargement à l'utilisateur

════════════════════════════════════════════════════════════════════════
RÈGLES ABSOLUES
════════════════════════════════════════════════════════════════════════

1. **NE JAMAIS afficher le contenu complet** : Après chaque génération, donne uniquement un message court de confirmation (ex: "5 User Stories générées"). Ne liste JAMAIS le contenu des exigences, user stories ou tests dans ta réponse.

2. **TOUJOURS fournir un lien de téléchargement** : À la fin de TOUT workflow, appelle OBLIGATOIREMENT un outil d'export (export_deliverables ou export_jira_csv selon le besoin) pour fournir le lien de téléchargement. C'est la SEULE façon pour l'utilisateur d'accéder au contenu.

3. **Utiliser update_state pour le contenu fourni par l'utilisateur** : Si l'utilisateur fournit explicitement une exigence, user story ou test à ajouter, utilise update_state au lieu de generate_*.""",
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
        self, content: str, schema: dict, tool_call_id: str
    ) -> tuple[list[dict] | None, Command | None]:
        """
        Parse JSON content from LLM response, clean markdown formatting, and validate against schema.

        Args:
            content: Raw LLM response content (may include markdown code blocks)
            schema: JSON schema to validate against
            tool_call_id: Tool call ID for error messages

        Returns:
            Tuple of (parsed_data, error_command). If successful, error_command is None.
            If failed, parsed_data is None and error_command contains the error message.
        """
        clean_data = content.strip()

        # Remove markdown code blocks if present
        if clean_data.startswith("```"):
            clean_data = re.sub(r"^```(?:json)?\n?", "", clean_data)
            clean_data = re.sub(r"\n?```$", "", clean_data)

        # Fix invalid JSON escape sequences (e.g., \' is not valid in JSON)
        clean_data = clean_data.replace("\\'", "'")

        try:
            data = json.loads(clean_data)
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

            IMPORTANT: Avant d'appeler cet outil, utilise les outils de recherche MCP
            pour extraire les informations pertinentes des documents projet, puis
            fournis un résumé de ce contexte en paramètre.

            Args:
                context_summary: Résumé du contexte projet extrait des documents

            Returns:
                Message de confirmation que les exigences ont été générées
            """
            requirements_prompt = """Tu es un Business Analyst expert. Génère une liste d'exigences formelles basée sur le contexte projet suivant.

Contexte projet extrait des documents:
{context_summary}

Consignes :
1. **Génère des exigences fonctionnelles et non-fonctionnelles**
2. **Formalisme :** Exigences claires, concises, non ambiguës et testables
3. **ID Unique :** Ex: EX-FON-001 (fonctionnelle), EX-NFON-001 (non-fonctionnelle)
4. **Priorisation :** Haute, Moyenne ou Basse

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Format JSON attendu:
[
  {{
    "id": "EX-FON-001",
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

    def get_user_stories_tool(self):
        """Tool that generates user stories using a separate LLM call"""

        @tool
        async def generate_user_stories(runtime: ToolRuntime, context_summary: str):
            """
            Génère des User Stories de haute qualité avec critères d'acceptation exhaustifs (Gherkin).

            IMPORTANT: Avant d'appeler cet outil, utilise les outils de recherche MCP
            pour extraire les informations pertinentes des documents projet.

            Si des exigences ont été générées précédemment avec generate_requirements,
            elles seront automatiquement utilisées pour assurer la cohérence.

            Args:
                context_summary: Résumé du contexte projet extrait des documents

            Returns:
                Message de confirmation que les user stories ont été générées
            """
            stories_prompt = """Tu es un Product Owner expert. Génère des User Stories de haute qualité.

Contexte projet extrait des documents:
{context_summary}

{requirements_section}

**Structure de base :**
- **Format :** "En tant que [persona], je veux [action], afin de [bénéfice]"
- **ID Unique :** Ex: US-001, US-002
- Stories atomiques, verticales et testables
- **Cohérence :** Couvre les exigences si elles sont fournies
- **Couverture complète :** Happy path + cas d'erreur + tous les personas

**Critères d'Acceptation Exhaustifs (Format Gherkin)** - OBLIGATOIRE pour CHAQUE story :

1. **Cas Nominaux (Happy Path) :**
   - Scénario idéal où tout fonctionne

2. **Validations de Données :**
   - Formats invalides (email, mot de passe, etc.)
   - Champs obligatoires manquants
   - Limites min/max de caractères
   - Fichiers non supportés ou trop volumineux
   - Unicité des données (doublons)

3. **Cas d'Erreur :**
   - Erreurs techniques (API, timeout, erreur 500)
   - Erreurs métier (stock insuffisant, droits insuffisants)
   - Perte de connexion

4. **Cas Limites :**
   - Valeurs frontières (0, 1, max, max+1)
   - Listes vides ou très longues
   - Dates limites (29 février, changement d'heure)

5. **Feedback Utilisateur :**
   - Messages de succès EXACTS (Toasts, Modales)
   - Messages d'erreur EXACTS affichés
   - États de chargement et boutons désactivés

**Format Gherkin strict :** "Étant donné que [contexte], Quand [action], Alors [résultat attendu]"

**Métadonnées :**
- **Estimation :** Fibonacci (1, 2, 3, 5, 8, 13, 21)
- **Priorisation :** High (Must Have), Medium (Should Have), Low (Could Have)
- **Dépendances :** Ordre logique, AUCUNE dépendance circulaire

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Format JSON attendu:
[
  {{
    "id": "US-001",
    "summary": "Titre court et descriptif de la User Story",
    "description": "En tant que [persona], je veux [action], afin de [bénéfice]",
    "issue_type": "Story",
    "priority": "High",
    "epic_name": "Nom de l'Epic parent",
    "story_points": 3,
    "labels": ["label1", "label2"],
    "acceptance_criteria": [
      "Étant donné que [contexte], Quand [action], Alors [résultat]",
      "Étant donné que [contexte], Quand [action], Alors [résultat]"
    ]
  }}
]

Règles:
- id: Identifiant unique (US-XXX)
- summary: Titre concis (max 100 caractères)
- description: Format "En tant que [persona], je veux [action], afin de [bénéfice]"
- issue_type: "Story", "Task" ou "Bug"
- priority: "High", "Medium" ou "Low"
- epic_name: Regroupe les stories liées sous un même Epic
- story_points: Fibonacci uniquement (1, 2, 3, 5, 8, 13, 21)
- labels: Tags pour catégorisation
- acceptance_criteria: Critères d'acceptation exhaustifs en format Gherkin (cas nominaux, validations, erreurs, cas limites, feedback)

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            requirements_section = ""
            # Use stored requirements from previous tool call if available
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
                        context_summary=context_summary,
                        requirements_section=requirements_section,
                    )
                )
            ]

            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            user_stories, error_cmd = self._parse_and_validate_json(
                str(response.content), userStoriesSchema, runtime.tool_call_id
            )
            if error_cmd:
                return error_cmd

            return Command(
                update={
                    "user_stories": user_stories,
                    "messages": [
                        ToolMessage(
                            f"✓ {len(user_stories)} User Stories générées avec succès. "
                            f"Si tu as terminé de générer tous les livrables demandés par l'utilisateur, "
                            f"appelle maintenant export_deliverables() pour fournir le lien de téléchargement.",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return generate_user_stories

    def get_tests_tool(self):
        """Tool that generates test scenarios using a separate LLM call"""

        @tool
        async def generate_tests(runtime: ToolRuntime, jdd: str = ""):
            """
            Génère des scénarios de tests détaillés et exploitables.

            IMPORTANT: Cet outil utilise automatiquement les User Stories générées
            précédemment avec generate_user_stories. Assurez-vous d'avoir appelé
            generate_user_stories avant d'appeler cet outil.

            Args:
                jdd: Jeu de Données pour les personas (optionnel, n'invente rien)

            Returns:
                Message de confirmation que les scénarios de tests ont été générés
            """
            tests_prompt = """## Rôle

Tu es un expert en tests logiciels. Ton rôle est de créer des scénarios de tests détaillés et exploitables.

## Instructions principales

Génère des scénarios de tests complets à partir des informations fournies dans les User Stories (US) suivantes, en suivant le format Gherkin (Etant donné que-Lorsque-Alors) et en incluant les cas nominaux, limites et d'erreur. Toutes les US fournies doivent faire l'objet d'un test.
Tu peux également te baser sur les JDDs fournis en entrée pour les personas de chaque tests

**--- DÉBUT DES USER STORIES À ANALYSER ---**
{USER_STORIES}
**--- FIN DES USER STORIES À ANALYSER ---**

**--- DÉBUT DU JDD À ANALYSER ---**
{JDD}
**--- FIN DU JDD À ANALYSER ---**

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Format JSON attendu:
[
  {{
    "id": "SC-001",
    "name": "Titre du scénario de test",
    "user_story_id": "US-001",
    "description": "Brève explication de ce que le scénario teste",
    "preconditions": "Les états ou données nécessaires avant l'exécution du test",
    "steps": [
      "Étant donné que [contexte]",
      "Lorsque [action]",
      "Alors [résultat attendu]"
    ],
    "test_data": "Jeux de données nécessaires",
    "priority": "Haute",
    "test_type": "Nominal",
    "expected_result": "Le résultat final attendu du test"
  }}
]

Règles:
- id: Identifiant unique (SC-XXX ou SC-LOGIN-XXX)
- name: Titre concis décrivant l'objectif du test
- user_story_id: L'ID de la User Story couverte par ce test
- description: Brève explication de ce que le scénario teste
- preconditions: Les états ou données nécessaires avant l'exécution
- steps: Étapes au format Gherkin (Étant donné que - Lorsque - Alors)
- test_data: Jeux de données nécessaires pour le test
- priority: "Haute", "Moyenne" ou "Basse"
- test_type: "Nominal", "Limite" ou "Erreur"
- expected_result: Le résultat final attendu

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            # Use stored user stories from previous tool call
            user_stories = runtime.state.get("user_stories")
            if not user_stories:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Erreur: Aucune User Story n'a été générée. Veuillez d'abord appeler generate_user_stories.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=tests_prompt.format(
                        USER_STORIES=json.dumps(
                            user_stories, ensure_ascii=False, indent=2
                        ),
                        JDD=jdd if jdd else "Aucun JDD fourni",
                    )
                )
            ]

            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Parse and validate JSON response
            tests, error_cmd = self._parse_and_validate_json(
                str(response.content), testsSchema, runtime.tool_call_id
            )
            if error_cmd:
                return error_cmd

            return Command(
                update={
                    "tests": tests,
                    "messages": [
                        ToolMessage(
                            f"✓ {len(tests)} scénarios de tests générés avec succès. "
                            f"Si tu as terminé de générer tous les livrables demandés par l'utilisateur, "
                            f"appelle maintenant export_deliverables() pour fournir le lien de téléchargement.",
                            tool_call_id=runtime.tool_call_id,
                        ),
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

    def _build_markdown_content(self, state: dict) -> str | None:
        """Build markdown content from generated requirements, user stories, and tests."""
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

        return "\n".join(sections)

    async def _generate_markdown_file(self, state: dict) -> LinkPart | None:
        """Generate a markdown file from state and return a download link."""
        content = self._build_markdown_content(state)
        if not content:
            return None

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
                    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria)
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
        user_stories_tool = self.get_user_stories_tool()
        tests_tool = self.get_tests_tool()
        update_state_tool = self.get_update_state_tool()
        export_tool = self.get_export_tool()
        export_jira_csv_tool = self.get_export_jira_csv_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                requirements_tool,
                user_stories_tool,
                tests_tool,
                update_state_tool,
                export_tool,
                export_jira_csv_tool,
                *self.mcp.get_tools(),
            ],
            checkpointer=self.streaming_memory,
            state_schema=CustomState,
        )
