"""Batch generation tools for Jira agent."""

import json
import logging

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agentic_backend.agents.jira.helpers import get_max_id_number
from agentic_backend.agents.jira.pydantic_models import (
    RequirementsList,
    TestsList,
    TestTitlesList,
    UserStoriesList,
    UserStoryTitlesList,
)
from agentic_backend.application_context import get_default_chat_model

logger = logging.getLogger(__name__)


class BatchTools:
    """Batch generation tools for requirements, user stories, and tests."""

    def __init__(self, agent):
        """Initialize batch tools with reference to parent agent."""
        self.agent = agent

    def _get_langfuse_handler(self):
        """Get Langfuse handler from parent agent."""
        return self.agent._get_langfuse_handler()

    def _build_llm_config(self) -> RunnableConfig:
        """Build a RunnableConfig with Langfuse callback if enabled."""
        handler = self._get_langfuse_handler()
        return {"callbacks": [handler]} if handler else {}

    def get_requirements_tool(self):
        """Tool that generates requirements using a separate LLM call."""

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

            response = await model.ainvoke(messages, config=self._build_llm_config())
            if not isinstance(response, RequirementsList):
                response = RequirementsList.model_validate(response)
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

{quantity_header}

Contexte projet extrait des documents:
{context_summary}

{requirements_section}

{existing_stories_section}

**Objectif:** Créer une liste cohérente de titres de User Stories qui:
- Couvrent l'ensemble du périmètre fonctionnel
- Évitent les doublons et chevauchements
- Sont regroupées par Epic logique
- Suivent une progression fonctionnelle cohérente
- Sont ordonnées logiquement. **AUCUNE dépendance circulaire.**
{req_id_instruction}

**Règles:**
- Chaque titre doit être concis (max 80 caractères)
- Utiliser des verbes d'action (Créer, Afficher, Modifier, Supprimer, etc.)
- Regrouper les stories liées sous le même Epic
- Indiquer les dépendances entre US (US prérequises) (pas de dépendances circulaires)
{req_mandatory_instruction}
- **NE PAS générer de titres pour des fonctionnalités déjà couvertes par les User Stories existantes**
- Les IDs doivent continuer la séquence existante (commencer à US-{next_id_hint})

{quantity_instruction}"""

        # Build requirements section
        requirements_section = ""
        req_id_instruction = ""
        requirements = runtime.state.get("requirements")
        if requirements:
            requirements_section = f"""
Exigences à respecter:
{json.dumps(requirements, ensure_ascii=False, indent=2)}
"""
            req_id_instruction = (
                "- **Sont liées aux exigences correspondantes via requirement_ids**"
            )
        else:
            req_id_instruction = "- **Aucune exigence n'a été générée : requirement_ids doit être null pour TOUTES les User Stories. NE PAS inventer d'IDs d'exigences.**"

        # Build existing stories section to avoid duplicates
        existing_stories_section = ""
        existing_stories = runtime.state.get("user_stories") or []

        # Determine the next ID hint based on existing stories
        max_num = get_max_id_number(existing_stories, r"US-(\d+)")
        next_id_hint = f"{max_num + 1:02d}"

        if existing_stories:
            existing_info = [
                {
                    "id": story.get("id"),
                    "title": story.get("summary"),
                    "epic_name": story.get("epic_name"),
                }
                for story in existing_stories
            ]
            existing_stories_section = f"""
**User Stories DÉJÀ EXISTANTES (NE PAS DUPLIQUER):**
{json.dumps(existing_info, ensure_ascii=False, indent=2)}

Tu dois générer des User Stories COMPLÉMENTAIRES qui n'existent pas encore.
"""

        # Build quantity instructions (header at top, reminder at bottom)
        if quantity is not None:
            quantity_header = f"""⚠️ **CONTRAINTE STRICTE:** Tu DOIS générer EXACTEMENT {quantity} nouveaux titres de User Stories.
Ni plus, ni moins. Exactement {quantity} éléments."""
            quantity_instruction = f"""⚠️ **RAPPEL:** Génère EXACTEMENT {quantity} titres. Pas {quantity - 1}, pas {quantity + 1}. Exactement {quantity}."""
        else:
            quantity_header = ""
            quantity_instruction = "Génère le nombre approprié de User Stories pour couvrir l'ensemble du périmètre fonctionnel du projet."

        # Build requirement mandatory instruction
        if requirements:
            req_mandatory_instruction = "- **OBLIGATOIRE: Chaque User Story doit avoir au moins un requirement_id parmi les exigences listées ci-dessus**"
        else:
            req_mandatory_instruction = "- **requirement_ids doit être null : aucune exigence n'existe, NE PAS inventer d'IDs**"

        model = get_default_chat_model().with_structured_output(
            UserStoryTitlesList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=titles_prompt.format(
                    context_summary=context_summary,
                    requirements_section=requirements_section,
                    existing_stories_section=existing_stories_section,
                    req_id_instruction=req_id_instruction,
                    req_mandatory_instruction=req_mandatory_instruction,
                    quantity_header=quantity_header,
                    quantity_instruction=quantity_instruction,
                    next_id_hint=next_id_hint,
                )
            )
        ]

        response = await model.ainvoke(messages, config=self._build_llm_config())
        if not isinstance(response, UserStoryTitlesList):
            response = UserStoryTitlesList.model_validate(response)
        return [t.model_dump() for t in response.items]

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

Contexte projet extrait des documents:
{context_summary}

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
- **Priorisation:** Haute, Moyenne, Basse

**Questions de clarification :** Pour chaque story, ajoute 1 à 3 questions précises pour lever les ambiguïtés.

Génère EXACTEMENT {count} User Stories correspondant aux titres fournis.
Utilise les mêmes IDs, epic_name et requirement_ids que dans les titres."""

        # Build requirements section
        requirements_section = ""
        if requirements:
            requirements_section = f"""
Exigences à respecter:
{json.dumps(requirements, ensure_ascii=False, indent=2)}
"""
        else:
            requirements_section = (
                "**Aucune exigence n'a été générée. "
                "requirement_ids doit être null pour toutes les User Stories. "
                "NE PAS inventer d'IDs d'exigences.**"
            )

        model = get_default_chat_model().with_structured_output(
            UserStoriesList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=stories_prompt.format(
                    context_summary=context_summary,
                    requirements_section=requirements_section,
                    titles_json=json.dumps(
                        titles_to_process, ensure_ascii=False, indent=2
                    ),
                    count=len(titles_to_process),
                )
            )
        ]

        response = await model.ainvoke(messages, config=self._build_llm_config())
        if not isinstance(response, UserStoriesList):
            response = UserStoriesList.model_validate(response)
        return [s.model_dump() for s in response.items]

    def get_user_stories_tool(self):
        """Tool that generates user stories with automatic title generation."""

        @tool
        async def generate_user_stories(
            runtime: ToolRuntime,
            context_summary: str,
            quantity: int | None = None,
        ):
            """
            Génère des User Stories complètes à partir du contexte projet en une seule invocation.

            Cet outil génère automatiquement les titres puis développe toutes les stories par lots internes.
            Il peut être utilisé même si des User Stories existent déjà : les stories existantes
            seront prises en compte pour éviter les doublons et continuer la numérotation.

            Pour ajouter une seule User Story, utilise plutôt add_user_story().

            IMPORTANT:
            - AVANT d'appeler cet outil, tu DOIS faire une recherche documentaire avec les outils MCP
            - Le context_summary doit contenir les informations extraites des documents (min 200 caractères)
            - Cet outil peut prendre du temps si beaucoup de stories sont à générer

            Args:
                context_summary: Résumé du contexte projet extrait des documents (min 200 caractères)
                quantity: Nombre total de User Stories à générer (optionnel)

            Returns:
                Message de confirmation avec le nombre total de stories générées
            """
            batch_size = 10

            # Validation
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

            # Get existing data from state
            existing_stories = runtime.state.get("user_stories") or []
            requirements = runtime.state.get("requirements")

            # Generate titles
            pending_titles = await self._generate_user_story_titles(
                runtime, context_summary, quantity
            )

            # Batch processing setup
            all_generated_stories = []
            total_to_generate = len(pending_titles)
            batches_completed = 0

            logger.info(
                f"[JiraAgent] Starting batch generation: {total_to_generate} user stories in batches of {batch_size}"
            )

            # Process batches
            while pending_titles:
                current_batch_size = min(batch_size, len(pending_titles))
                titles_batch = pending_titles[:current_batch_size]
                pending_titles = pending_titles[current_batch_size:]

                new_stories = await self._generate_user_story_batch(
                    titles_batch, context_summary, requirements
                )
                all_generated_stories.extend(new_stories)
                batches_completed += 1

                logger.info(
                    f"[JiraAgent] Batch {batches_completed} complete: "
                    f"{len(all_generated_stories)}/{total_to_generate} user stories generated"
                )

            # Build success message and return
            stories_generated = len(all_generated_stories)
            total_stories = len(existing_stories) + stories_generated
            msg = (
                f"✓ {stories_generated} User Stories générées en {batches_completed} lots. "
                f"Total: {total_stories} User Stories complètes! "
                f"Appelle export_deliverables() pour exporter les livrables."
            )

            return Command(
                update={
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
        titles_prompt = """Tu es un expert en tests logiciels. Génère une liste de titres de tests pour les User Stories suivantes.

{quantity_header}

## User Stories à couvrir

{user_stories_json}

{existing_tests_section}

## Instructions

Pour chaque User Story, génère des titres de tests couvrant:
- **Nominal**: Cas de test du parcours nominal (happy path)
- **Limite**: Cas de test aux limites (valeurs frontières, listes vides/longues)
- **Erreur**: Cas de test d'erreur (validations, erreurs techniques)

**Règles:**
- Chaque titre doit être concis et descriptif (max 80 caractères)
- Les IDs doivent suivre le format SC-XX (commencer à SC-{next_id_hint})
- Chaque titre doit référencer sa User Story via user_story_id
- **NE PAS générer de titres pour des tests déjà existants**

{quantity_instruction}"""
        user_stories = runtime.state.get("user_stories") or []
        existing_tests = runtime.state.get("tests") or []

        # Determine the next ID hint based on existing tests
        max_num = get_max_id_number(existing_tests, r"SC-(\d+)")
        next_id_hint = f"{max_num + 1:02d}"

        # Build existing tests section to avoid duplicates
        existing_tests_section = ""
        if existing_tests:
            existing_info = [
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "user_story_id": t.get("user_story_id"),
                }
                for t in existing_tests
            ]
            existing_tests_section = f"""
**Tests DÉJÀ EXISTANTS (NE PAS DUPLIQUER):**
{json.dumps(existing_info, ensure_ascii=False, indent=2)}

Tu dois générer des titres de tests COMPLÉMENTAIRES qui n'existent pas encore.
"""

        if quantity is not None:
            quantity_header = f"""⚠️ **CONTRAINTE STRICTE:** Tu DOIS générer EXACTEMENT {quantity} nouveaux titres de tests.
Ni plus, ni moins. Exactement {quantity} éléments."""
            quantity_instruction = f"""⚠️ **RAPPEL:** Génère EXACTEMENT {quantity} titres. Pas {quantity - 1}, pas {quantity + 1}. Exactement {quantity}."""
        else:
            quantity_header = ""
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
                    existing_tests_section=existing_tests_section,
                    next_id_hint=next_id_hint,
                    quantity_header=quantity_header,
                    quantity_instruction=quantity_instruction,
                )
            )
        ]

        response = await model.ainvoke(messages, config=self._build_llm_config())
        if not isinstance(response, TestTitlesList):
            response = TestTitlesList.model_validate(response)
        return [t.model_dump() for t in response.items]

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
        tests_prompt = """## Rôle

Tu es un expert en tests logiciels. Génère des scénarios de tests COMPLETS pour les titres de tests suivants.

## Titres de tests à développer

{titles_json}

## User Stories associées (pour contexte)

{user_stories_json}

## Jeu de Données (JDD)

{jdd}

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
        # Get the relevant user stories for the titles being processed
        relevant_story_ids = {t.get("user_story_id") for t in titles_to_process}
        relevant_stories = [
            stories_by_id[sid] for sid in relevant_story_ids if sid in stories_by_id
        ]

        model = get_default_chat_model().with_structured_output(
            TestsList, method="json_schema"
        )
        messages = [
            SystemMessage(
                content=tests_prompt.format(
                    titles_json=json.dumps(
                        titles_to_process, ensure_ascii=False, indent=2
                    ),
                    user_stories_json=json.dumps(
                        relevant_stories, ensure_ascii=False, indent=2
                    ),
                    jdd=jdd if jdd else "Aucun JDD fourni",
                    count=len(titles_to_process),
                )
            )
        ]

        response = await model.ainvoke(messages, config=self._build_llm_config())
        if not isinstance(response, TestsList):
            response = TestsList.model_validate(response)
        return [t.model_dump() for t in response.items]

    def get_tests_tool(self):
        """Tool that generates test scenarios with automatic title generation."""

        @tool
        async def generate_tests(
            runtime: ToolRuntime,
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
                quantity: Nombre total de tests à générer (optionnel)
                jdd: Jeu de Données pour les personas (optionnel)

            Returns:
                Message de confirmation avec le nombre total de tests générés
            """
            batch_size = 10

            # Get existing data from state
            existing_tests = runtime.state.get("tests") or []
            all_stories = runtime.state.get("user_stories") or []

            # Validation
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

            # Generate titles
            pending_titles = await self._generate_test_titles(runtime, quantity)

            # Create lookup map for user stories
            stories_by_id = {s.get("id"): s for s in all_stories}

            # Batch processing setup
            all_generated_tests = []
            total_to_generate = len(pending_titles)
            batches_completed = 0

            logger.info(
                f"[JiraAgent] Starting batch generation: {total_to_generate} tests in batches of {batch_size}"
            )

            # Process batches
            while pending_titles:
                current_batch_size = min(batch_size, len(pending_titles))
                titles_batch = pending_titles[:current_batch_size]
                pending_titles = pending_titles[current_batch_size:]

                new_tests = await self._generate_test_batch(
                    titles_batch, stories_by_id, jdd
                )
                all_generated_tests.extend(new_tests)
                batches_completed += 1

                logger.info(
                    f"[JiraAgent] Batch {batches_completed} complete: "
                    f"{len(all_generated_tests)}/{total_to_generate} tests generated"
                )

            # Build success message and return
            tests_generated = len(all_generated_tests)
            total_tests = len(existing_tests) + tests_generated
            msg = (
                f"✓ {tests_generated} tests générés en {batches_completed} lots. "
                f"Total: {total_tests} tests complets! "
                f"Appelle export_deliverables() pour exporter les livrables."
            )

            return Command(
                update={
                    "tests": all_generated_tests,
                    "messages": [
                        ToolMessage(msg, tool_call_id=runtime.tool_call_id),
                    ],
                }
            )

        return generate_tests
