"""Single-item add/remove tools for Jira agent."""

from typing import cast

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agentic_backend.agents.jira.helpers import (
    get_next_requirement_id,
    get_next_test_id,
    get_next_user_story_id,
)
from agentic_backend.agents.jira.pydantic_models import (
    QuickRequirement,
    QuickTest,
    QuickUserStory,
    Requirement,
    Test,
    UserStory,
)
from agentic_backend.application_context import get_default_chat_model


class SingleItemTools:
    """Single-item generation and removal tools."""

    def __init__(self, agent):
        """Initialize single-item tools with reference to parent agent."""
        self.agent = agent

    def _get_langfuse_handler(self):
        """Get Langfuse handler from parent agent."""
        return self.agent._get_langfuse_handler()

    async def _expand_requirement(
        self,
        title: str,
        req_type: str,
        example_requirement: dict | None = None,
    ) -> dict:
        """
        Use internal LLM call with structured output to expand a title into a full requirement.

        This is for SINGLE item generation only (1 LLM call).
        For bulk generation, use generate_requirements() which has batching.
        """
        type_label = (
            "fonctionnelle" if req_type == "fonctionnelle" else "non-fonctionnelle"
        )

        example_section = ""
        if example_requirement:
            example_section = f"""
Voici un exemple d'exigence existante pour référence de style et longueur:
- Titre: {example_requirement.get("title")}
- Description: {example_requirement.get("description")}

Ta description doit avoir une longueur et un style similaires à cet exemple.
"""

        prompt = f"""Génère une exigence {type_label} complète à partir de ce titre.

Titre: {title}

Génère une description de l'exigence qui:
- Explique clairement ce qui est requis
- Est mesurable et testable
- Est cohérente avec le titre fourni
- Est concise (1-2 phrases maximum)

{example_section}
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
- Description au format "En tant que [persona], je veux [action], afin de [bénéfice]"
- 2-4 critères d'acceptation avec étapes Gherkin (Étant donné/Quand/Alors)
- Story points (Fibonacci: 1, 2, 3, 5, 8, 13, 21)
- Priorité (High/Medium/Low)
- 1 à 3 questions de clarification pour lever les ambiguïtés
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
            next_id = get_next_requirement_id(runtime.state, rtype)
            prio = priority or "Moyenne"

            # Get an example requirement from state if available
            existing_requirements = runtime.state.get("requirements") or []
            example_requirement = (
                existing_requirements[0] if existing_requirements else None
            )

            # Expand title into full requirement using internal LLM
            expanded = await self._expand_requirement(title, rtype, example_requirement)

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

            Utilise cet outil pour:
            - Les demandes simples comme "ajoute une US pour le login"
            - Ajouter des User Stories après avoir ajouté de nouvelles exigences (add_requirement)
            - Tu peux appeler cet outil plusieurs fois séquentiellement pour ajouter plusieurs stories

            ⚠️ generate_user_stories() ne fonctionne que pour la génération initiale.
            Pour ajouter des stories incrémentalement, utilise TOUJOURS cet outil.

            Args:
                title: Titre de la User Story (ex: "Permettre la connexion SSO")
                epic_name: Nom de l'Epic parent (défaut: "Backlog")
                requirement_ids: Liste des IDs d'exigences liées (optionnel)
                context: Contexte supplémentaire pour guider la génération
            """
            # Generate ID
            next_id = get_next_user_story_id(runtime.state)
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
            next_id = get_next_test_id(runtime.state)
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
