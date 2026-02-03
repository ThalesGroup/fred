"""Batch generation tools for Jira agent."""

import json
import logging
import re
from typing import cast

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

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
- Sont ordonnées logiquement. **AUCUNE dépendance circulaire.**
- **Sont liées aux exigences correspondantes via requirement_ids**

**Règles:**
- Chaque titre doit être concis (max 80 caractères)
- Utiliser des verbes d'action (Créer, Afficher, Modifier, Supprimer, etc.)
- Regrouper les stories liées sous le même Epic
- Indiquer les dépendances entre US (US prérequises) (pas de dépendances circulaires)
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
- **Priorisation:** High, Medium, Low

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

        langfuse_handler = self._get_langfuse_handler()
        config: RunnableConfig = (
            {"callbacks": [langfuse_handler]} if langfuse_handler else {}
        )

        response = cast(UserStoriesList, await model.ainvoke(messages, config=config))
        return [s.model_dump() for s in response.items]

    def get_user_stories_tool(self):
        """Tool that generates user stories with automatic title generation."""

        @tool
        async def generate_user_stories(
            runtime: ToolRuntime,
            context_summary: str,
            batch_size: int = 10,
            quantity: int | None = None,
        ):
            """
            Génère TOUTES les User Stories complètes à partir du contexte projet en une seule invocation.

            Cet outil est pour la GÉNÉRATION INITIALE uniquement (quand aucune User Story n'existe).
            Il génère automatiquement les titres puis génère toutes les stories par lots internes.

            ⚠️ NE PAS UTILISER si des User Stories existent déjà!
            Pour ajouter des User Stories de manière incrémentale (ex: après add_requirement),
            utilise add_user_story() plusieurs fois à la place.

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
        """Tool that generates test scenarios with automatic title generation."""

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
