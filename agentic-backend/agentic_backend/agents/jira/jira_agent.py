import csv
import io
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from langchain.agents import AgentState, create_agent
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

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
    generated_requirements: str
    generated_user_stories: str
    generated_user_stories_jira: str  # JSON format for Jira CSV export
    generated_tests: str


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
   - OBLIGATOIRE : Appelle cet outil à la fin pour fournir le fichier à l'utilisateur

6. **generate_user_stories_for_jira** :
   - Génère des User Stories au format JSON structuré pour l'import Jira
   - IMPORTANT : Cet outil fait un appel LLM séparé, donc ne timeout pas
   - CHAÎNAGE AUTOMATIQUE : Si des exigences ont été générées avant, elles sont automatiquement utilisées
   - Utilise cet outil à la place de generate_user_stories si l'utilisateur veut importer dans Jira

7. **export_jira_csv** :
   - Exporte les User Stories Jira générées dans un fichier CSV compatible avec l'import Jira
   - IMPORTANT : Nécessite d'avoir appelé generate_user_stories_for_jira au préalable
   - Retourne un lien de téléchargement du fichier CSV

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
- Appelle export_deliverables() pour générer le fichier Markdown téléchargeable
- Cet outil retourne un lien de téléchargement à présenter à l'utilisateur

════════════════════════════════════════════════════════════════════════
WORKFLOW ALTERNATIF : EXPORT JIRA
════════════════════════════════════════════════════════════════════════

Si l'utilisateur souhaite importer les User Stories dans Jira :

**Étape 1 : Extraction du contexte projet** (identique)

**Étape 2 : Génération des exigences** (optionnel, identique)

**Étape 3 : Génération des User Stories pour Jira**
- Appelle generate_user_stories_for_jira(context_summary="[résumé]") au lieu de generate_user_stories
- Génère des User Stories au format JSON structuré

**Étape 4 : Export CSV Jira**
- Appelle export_jira_csv() pour générer le fichier CSV téléchargeable
- Ce fichier est directement importable dans Jira via Project settings > External system import""",
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
            requirements_prompt = """
Tu es un Business Analyst expert. Génère une liste d'exigences formelles basée sur le contexte projet suivant.

Contexte projet extrait des documents:
{context_summary}

Consignes :
1. **Génère des exigences fonctionnelles et non-fonctionnelles**
2. **Formalisme :** Exigences claires, concises, non ambiguës et testables
3. **ID Unique :** Ex: EX-FON-001 (fonctionnelle), EX-NFON-001 (non-fonctionnelle)
4. **Priorisation :** Haute, Moyenne ou Basse

Format attendu pour chaque exigence:
- ID: [ID unique]
- Titre: [Nom concis]
- Description: [Exigence détaillée]
- Type: [Fonctionnelle/Non-fonctionnelle]
- Priorité: [Haute/Moyenne/Basse]

IMPORTANT: n'ajoute pas de phrase d'incitation à l'interaction en fin de message
ex de ce qu'il ne faut pas ajouter: "Besoin d'ajustements ou de précisions sur certaines exigences ?"
"""

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=requirements_prompt.format(context_summary=context_summary)
                )
            ]

            # Add Langfuse tracing if enabled
            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Return confirmation message
            return Command(
                update={
                    "generated_requirements": str(response.content),
                    "messages": [
                        ToolMessage(
                            "✓ Exigences générées avec succès. Elles seront affichées à la fin de la conversation.",
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
            stories_prompt = """
Tu es un Product Owner expert. Génère des User Stories de haute qualité.

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
- **Priorisation :** Must Have, Should Have, Could Have, Won't Have
- **Dépendances :** Ordre logique, AUCUNE dépendance circulaire
- **Questions :** 1 à 3 questions de clarification par story

IMPORTANT: n'ajoute pas de phrase d'incitation à l'interaction en fin de message
ex de ce qu'il ne faut pas ajouter: "Besoin d'ajustements ou de précisions sur certaines sories ?"
"""

            requirements_section = ""
            # Use stored requirements from previous tool call if available
            generated_requirements = runtime.state.get("generated_requirements")
            if generated_requirements:
                requirements_section = f"""
Exigences à respecter:
{generated_requirements}
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

            # Add Langfuse tracing if enabled
            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Return confirmation message and update state
            return Command(
                update={
                    "generated_user_stories": str(response.content),
                    "messages": [
                        ToolMessage(
                            "✓ User Stories générées avec succès. Elles seront affichées à la fin de la conversation.",
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
            tests_prompt = """
## Rôle

Tu es un expert en tests logiciels. Ton rôle est de créer des scénarios de tests détaillés et exploitables.

## Instructions principales

Génère des scénarios de tests complets à partir des informations fournies dans les User Stories (US) suivantes, en suivant le format Gherkin (Etant donné que-Lorsque-Alors) et en incluant les cas nominaux, limites et d'erreur. Toutes les US fournies doivent faire l'objet d'un test.
Tu peux également te baser sur les JDDs fournis en entrée pour les personas de chaque tests

## Format de réponse attendu 📝

Pour chaque scénario :

1. **ID du Scénario** : Un identifiant unique (ex: SC-001, SC-LOGIN-001).
2. **userStoryId**: L'ID de la User Story couverte par ce test.
3. **Titre du Scénario** : Un titre concis décrivant l'objectif du test.
4. **Description** : Une brève explication de ce que le scénario teste.
5. **Préconditions** : Les états ou données nécessaires avant l'exécution du test.
6. **Étapes** : Au format Gherkin présentées sous forme de tableau avec les colonnes suivantes : Numéro (#1, #2, ...), Action (Etant donné que - Lorsque), Résultat attendu (Alors).
7. **Données de test** : Jeux de données nécessaires
8. **Priorité** : (Haute, Moyenne, Basse) Indiquant l'importance du test.
9. **type**: Le type de cas de test (Nominal, Limite, Erreur).

-------------------------------------------

**--- DÉBUT DES USER STORIES À ANALYSER ---**
{USER_STORIES}
**--- FIN DES USER STORIES À ANALYSER ---**

**--- DÉBUT DU JDD À ANALYSER ---**
{JDD}
**--- FIN DU JDD À ANALYSER ---**

IMPORTANT: n'ajoute pas de phrase d'incitation à l'interaction en fin de message
ex de ce qu'il ne faut pas ajouter: "Besoin d'ajustements ou de précisions sur certains tests ?"
"""

            # Use stored user stories from previous tool call
            generated_user_stories = runtime.state.get("generated_user_stories")
            if not generated_user_stories:
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
                        USER_STORIES=generated_user_stories,
                        JDD=jdd if jdd else "Aucun JDD fourni",
                    )
                )
            ]

            # Add Langfuse tracing if enabled
            langfuse_handler = self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Return confirmation message and update state
            return Command(
                update={
                    "generated_tests": str(response.content),
                    "messages": [
                        ToolMessage(
                            "✓ Scénarios de tests générés avec succès. Ils seront affichés à la fin de la conversation.",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return generate_tests

    def _build_markdown_content(self, state: dict) -> str | None:
        """Build markdown content from generated requirements, user stories, and tests."""
        requirements = state.get("generated_requirements")
        user_stories = state.get("generated_user_stories")
        tests = state.get("generated_tests")

        # If nothing was generated, return None
        if not any([requirements, user_stories, tests]):
            return None

        sections = []
        sections.append("# Livrables Projet\n")
        sections.append(f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*\n")

        if requirements:
            sections.append("---\n")
            sections.append("## Exigences\n")
            sections.append(requirements)
            sections.append("\n")

        if user_stories:
            sections.append("---\n")
            sections.append("## User Stories\n")
            sections.append(user_stories)
            sections.append("\n")

        if tests:
            sections.append("---\n")
            sections.append("## Scénarios de Tests\n")
            sections.append(tests)
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
                    runtime.state.get("generated_requirements"),
                    runtime.state.get("generated_user_stories"),
                    runtime.state.get("generated_tests"),
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

    def get_user_stories_jira_tool(self):
        """Tool that generates user stories in structured JSON format for Jira import."""

        @tool
        async def generate_user_stories_for_jira(
            runtime: ToolRuntime, context_summary: str
        ):
            """
            Génère des User Stories dans un format structuré JSON pour l'import Jira.

            Cet outil génère des User Stories optimisées pour l'import CSV dans Jira,
            avec tous les champs nécessaires (Summary, Description, Priority, Story Points, etc.).

            IMPORTANT: Avant d'appeler cet outil, utilise les outils de recherche MCP
            pour extraire les informations pertinentes des documents projet.

            Si des exigences ont été générées précédemment avec generate_requirements,
            elles seront automatiquement utilisées pour assurer la cohérence.

            Args:
                context_summary: Résumé du contexte projet extrait des documents

            Returns:
                Message de confirmation que les user stories Jira ont été générées
            """
            stories_prompt = """Tu es un Product Owner expert. Génère des User Stories au format JSON pour l'import Jira.

Contexte projet extrait des documents:
{context_summary}

{requirements_section}

IMPORTANT: Tu dois répondre UNIQUEMENT avec un tableau JSON valide, sans aucun texte avant ou après.

Chaque User Story doit suivre ce schéma JSON exact:
{{
  "stories": [
    {{
      "id": "US-001",
      "summary": "Titre court et descriptif de la User Story",
      "description": "En tant que [persona], je veux [action], afin de [bénéfice]",
      "issue_type": "Story",
      "priority": "High|Medium|Low",
      "epic_name": "Nom de l'Epic parent (optionnel)",
      "story_points": 3,
      "labels": "label1,label2",
      "acceptance_criteria": "Critère 1\\nCritère 2\\nCritère 3"
    }}
  ]
}}

Règles:
1. **summary**: Titre concis (max 100 caractères), format "US-XXX: Titre descriptif"
2. **description**: Format "En tant que [persona], je veux [action], afin de [bénéfice]"
3. **priority**: "High" pour Must Have, "Medium" pour Should Have, "Low" pour Could Have
4. **story_points**: Fibonacci uniquement (1, 2, 3, 5, 8, 13, 21)
5. **labels**: Tags séparés par des virgules (ex: "authentication,security")
6. **acceptance_criteria**: Critères d'acceptation en format Gherkin, séparés par \\n
7. **epic_name**: Regroupe les stories liées sous un même Epic

Génère des User Stories couvrant:
- Cas nominaux (Happy Path)
- Validations de données
- Cas d'erreur
- Cas limites

Réponds UNIQUEMENT avec le JSON, sans markdown ni backticks."""

            requirements_section = ""
            generated_requirements = runtime.state.get("generated_requirements")
            if generated_requirements:
                requirements_section = f"""
Exigences à respecter:
{generated_requirements}
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

            return Command(
                update={
                    "generated_user_stories_jira": str(response.content),
                    "messages": [
                        ToolMessage(
                            "✓ User Stories Jira générées avec succès. Utilisez export_jira_csv pour télécharger le fichier CSV.",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return generate_user_stories_for_jira

    def get_export_jira_csv_tool(self):
        """Tool that exports generated Jira user stories to CSV format."""

        @tool
        async def export_jira_csv(runtime: ToolRuntime):
            """
            Exporte les User Stories générées pour Jira dans un fichier CSV compatible avec l'import Jira.

            IMPORTANT: Cet outil nécessite que generate_user_stories_for_jira ait été appelé au préalable.

            Le fichier CSV généré contient les colonnes standard Jira:
            - Summary, Description, IssueType, Priority, Epic Name, Epic Link, Story Points, Labels

            Note: Les critères d'acceptation sont ajoutés à la Description car ce n'est pas un champ standard Jira.

            Returns:
                Lien de téléchargement du fichier CSV
            """
            import json

            jira_data = runtime.state.get("generated_user_stories_jira")
            if not jira_data:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Aucune User Story Jira n'a été générée. Veuillez d'abord appeler generate_user_stories_for_jira.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Parse JSON data
            try:
                # Clean potential markdown code blocks
                clean_data = jira_data.strip()
                if clean_data.startswith("```"):
                    clean_data = re.sub(r"^```(?:json)?\n?", "", clean_data)
                    clean_data = re.sub(r"\n?```$", "", clean_data)

                parsed = json.loads(clean_data)
                stories = parsed.get("stories", [])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Jira JSON: {e}")
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ Erreur lors du parsing JSON: {e}. Veuillez régénérer les User Stories.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            if not stories:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Aucune User Story trouvée dans les données générées.",
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

            for story in stories:
                # Append acceptance criteria to description since it's not a standard Jira field
                description = story.get("description", "")
                acceptance_criteria = story.get("acceptance_criteria", "").replace(
                    "\\n", "\n"
                )
                if acceptance_criteria:
                    description = f"{description}\n\n*Critères d'acceptation:*\n{acceptance_criteria}"

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
                        "Labels": story.get("labels", ""),
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
        user_stories_jira_tool = self.get_user_stories_jira_tool()
        tests_tool = self.get_tests_tool()
        export_tool = self.get_export_tool()
        export_jira_csv_tool = self.get_export_jira_csv_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                requirements_tool,
                user_stories_tool,
                user_stories_jira_tool,
                tests_tool,
                export_tool,
                export_jira_csv_tool,
                *self.mcp.get_tools(),
            ],
            checkpointer=self.streaming_memory,
            state_schema=CustomState,
        )
