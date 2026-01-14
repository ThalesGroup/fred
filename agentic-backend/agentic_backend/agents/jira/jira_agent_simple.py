import logging
import os

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.graph.state import CompiledStateGraph

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

════════════════════════════════════════════════════════════════════════
OUTILS DISPONIBLES
════════════════════════════════════════════════════════════════════════

Tu disposes de 4 types d'outils :

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
   - Peut recevoir les exigences en paramètre pour assurer la cohérence
   - Retourne un message confirmant que les user stories ont été générées

4. **generate_tests** :
   - Génère des scénarios de tests détaillés au format Gherkin
   - IMPORTANT : Cet outil fait un appel LLM séparé, donc ne timeout pas
   - Nécessite les User Stories en paramètre
   - Peut recevoir un JDD (Jeu de Données) optionnel pour les personas
   - Retourne un message confirmant que les scénarios de tests ont été générés

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
- Si l'utilisateur demande aussi des user stories :
  - Appelle generate_user_stories(context_summary="...", requirements="[exigences de l'étape 2]")
- Si l'utilisateur demande UNIQUEMENT des user stories :
  - Appelle directement generate_user_stories(context_summary="...", requirements="")
- L'outil génère les user stories et retourne un message de confirmation

**Étape 4 : Génération des scénarios de tests (si demandé)**
- Si l'utilisateur demande des tests :
  - Appelle generate_tests(user_stories="[user stories de l'étape 3]", jdd="[JDD si fourni]")
- L'outil génère les scénarios de tests et retourne un message de confirmation

**Étape 5 : Conclusion**
- Une fois tous les outils appelés, termine ta réponse
- Les résultats détaillés (exigences, user stories et tests) seront automatiquement affichés à l'utilisateur""",
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
        # Storage for tool outputs
        self.generated_requirements = None
        self.generated_user_stories = None
        self.generated_tests = None
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

        # Capture self reference for closure
        agent_self = self

        @tool
        async def generate_requirements(context_summary: str) -> str:
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
"""

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=requirements_prompt.format(context_summary=context_summary)
                )
            ]

            # Add Langfuse tracing if enabled
            langfuse_handler = agent_self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Store the full output
            content = response.content
            if isinstance(content, str):
                agent_self.generated_requirements = content
            elif isinstance(content, list):
                agent_self.generated_requirements = "".join(
                    part if isinstance(part, str) else part.get("text", "")
                    for part in content
                )
            else:
                agent_self.generated_requirements = str(content)

            # Return confirmation message
            return "✓ Exigences générées avec succès. Elles seront affichées à la fin de la conversation."

        return generate_requirements

    def get_user_stories_tool(self):
        """Tool that generates user stories using a separate LLM call"""

        # Capture self reference for closure
        agent_self = self

        @tool
        async def generate_user_stories(
            context_summary: str, requirements: str = ""
        ) -> str:
            """
            Génère des User Stories de haute qualité avec critères d'acceptation exhaustifs (Gherkin).

            IMPORTANT: Avant d'appeler cet outil, utilise les outils de recherche MCP
            pour extraire les informations pertinentes des documents projet.

            Args:
                context_summary: Résumé du contexte projet extrait des documents
                requirements: Les exigences préalablement générées (optionnel, pour cohérence)

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
"""

            requirements_section = ""
            if requirements:
                requirements_section = f"""
Exigences à respecter:
{requirements}
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
            langfuse_handler = agent_self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Store the full output
            content = response.content
            if isinstance(content, str):
                agent_self.generated_user_stories = content
            elif isinstance(content, list):
                agent_self.generated_user_stories = "".join(
                    part if isinstance(part, str) else part.get("text", "")
                    for part in content
                )
            else:
                agent_self.generated_user_stories = str(content)

            # Return confirmation message
            return "✓ User Stories générées avec succès. Elles seront affichées à la fin de la conversation."

        return generate_user_stories

    def get_tests_tool(self):
        """Tool that generates test scenarios using a separate LLM call"""

        # Capture self reference for closure
        agent_self = self

        @tool
        async def generate_tests(user_stories: str, jdd: str = "") -> str:
            """
            Génère des scénarios de tests détaillés et exploitables à partir des User Stories fournies.

            IMPORTANT: Avant d'appeler cet outil, assure-toi d'avoir les User Stories.
            Tu peux également fournir un JDD (Jeu de Données) pour les personas de chaque test.

            Args:
                user_stories: Les User Stories à couvrir par les tests
                jdd: Jeu de Données pour les personas (optionnel)

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
"""

            model = get_default_chat_model()
            messages = [
                SystemMessage(
                    content=tests_prompt.format(
                        USER_STORIES=user_stories,
                        JDD=jdd if jdd else "Aucun JDD fourni",
                    )
                )
            ]

            # Add Langfuse tracing if enabled
            langfuse_handler = agent_self._get_langfuse_handler()
            config: RunnableConfig = (
                {"callbacks": [langfuse_handler]} if langfuse_handler else {}
            )

            response = await model.ainvoke(messages, config=config)

            # Store the full output
            content = response.content
            if isinstance(content, str):
                agent_self.generated_tests = content
            elif isinstance(content, list):
                agent_self.generated_tests = "".join(
                    part if isinstance(part, str) else part.get("text", "")
                    for part in content
                )
            else:
                agent_self.generated_tests = str(content)

            # Return confirmation message
            return "✓ Scénarios de tests générés avec succès. Ils seront affichés à la fin de la conversation."

        return generate_tests

    async def astream_updates(self, state, *, config=None, **kwargs):
        """Override to append stored tool outputs to final response"""
        final_event = None

        # Stream all events from parent
        async for event in super().astream_updates(state, config=config, **kwargs):
            final_event = event
            yield event

        # After streaming is complete, if we have stored outputs, send them as additional messages
        if final_event is not None and (
            self.generated_requirements
            or self.generated_user_stories
            or self.generated_tests
        ):
            # Build the additional content
            additional_content = "\n\n---\n\n"

            if self.generated_requirements:
                additional_content += "# 📋 Exigences Générées\n\n"
                additional_content += self.generated_requirements
                additional_content += "\n\n"

            if self.generated_user_stories:
                additional_content += "# 📝 User Stories Générées\n\n"
                additional_content += self.generated_user_stories
                additional_content += "\n\n"

            if self.generated_tests:
                additional_content += "# 🧪 Scénarios de Tests Générés\n\n"
                additional_content += self.generated_tests

            # Create a new AI message with the stored content
            additional_message = AIMessage(content=additional_content)

            # Yield it as a new update
            yield {"agent": {"messages": [additional_message]}}

            # Reset for next run
            self.generated_requirements = None
            self.generated_user_stories = None
            self.generated_tests = None

    def get_compiled_graph(self) -> CompiledStateGraph:
        requirements_tool = self.get_requirements_tool()
        user_stories_tool = self.get_user_stories_tool()
        tests_tool = self.get_tests_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                requirements_tool,
                user_stories_tool,
                tests_tool,
                *self.mcp.get_tools(),
            ],
            checkpointer=self.streaming_memory,
        )
