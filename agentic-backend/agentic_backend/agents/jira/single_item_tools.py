"""Single-item add/remove tools for Jira agent."""

import json

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import Command

from agentic_backend.agents.jira.helpers import (
    ensure_pydantic_model,
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
        try:
            result = ensure_pydantic_model(
                await model.ainvoke([SystemMessage(content=prompt)]),
                QuickRequirement,
            )
            return result.model_dump()
        except Exception as e:
            raise RuntimeError(
                f"Erreur lors de la génération de l'exigence: {e}"
            ) from e

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
- Priorité (Haute/Moyenne/Basse)
- 1 à 3 questions de clarification pour lever les ambiguïtés
"""

        model = get_default_chat_model().with_structured_output(
            QuickUserStory, method="json_schema"
        )
        try:
            result = ensure_pydantic_model(
                await model.ainvoke([SystemMessage(content=prompt)]),
                QuickUserStory,
            )
            return result.model_dump()
        except Exception as e:
            raise RuntimeError(
                f"Erreur lors de la génération de la User Story: {e}"
            ) from e

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
        try:
            result = ensure_pydantic_model(
                await model.ainvoke([SystemMessage(content=prompt)]),
                QuickTest,
            )
            return result.model_dump()
        except Exception as e:
            raise RuntimeError(f"Erreur lors de la génération du test: {e}") from e

    def get_add_requirement_tool(self):
        """Tool to add a single requirement from a title."""

        @tool
        async def add_requirement(
            runtime: ToolRuntime,
            title: str,
            req_type: str | None = None,
            priority: str | None = None,
            description: str | None = None,
        ):
            """
            Ajoute UNE exigence à partir d'un titre.

            Si une description est fournie, elle est utilisée directement sans appel LLM.
            Sinon, la description est générée automatiquement à partir du titre.

            Utilise cet outil pour les demandes simples comme "ajoute une exigence pour l'authentification".
            Pour générer PLUSIEURS exigences, utilise generate_requirements().

            Args:
                title: Titre de l'exigence (ex: "Authentification multi-facteur")
                req_type: Type d'exigence - "fonctionnelle" ou "non-fonctionnelle" (défaut: "fonctionnelle")
                priority: Priorité - "Haute", "Moyenne", ou "Basse" (défaut: "Moyenne")
                description: Description détaillée de l'exigence (optionnel - si fourni, pas d'appel LLM)
            """
            # Generate ID
            rtype = req_type or "fonctionnelle"
            next_id = get_next_requirement_id(runtime.state, rtype)
            prio = priority or "Moyenne"

            if description is not None:
                # User provided description directly, skip LLM
                expanded = {"description": description}
            else:
                # Get an example requirement from state if available
                existing_requirements = runtime.state.get("requirements") or []
                example_requirement = (
                    existing_requirements[0] if existing_requirements else None
                )
                # Expand title into full requirement using internal LLM
                expanded = await self._expand_requirement(
                    title, rtype, example_requirement
                )

            # Build complete Requirement
            new_req = {
                "id": next_id,
                "title": title,
                "priority": prio,
                **expanded,
            }

            # Validate and add to state (reducer handles appending)
            validated = Requirement.model_validate(new_req)

            return Command(
                update={
                    "requirements": [validated.model_dump()],
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
            description: str | None = None,
            priority: str | None = None,
            issue_type: str | None = None,
            story_points: int | None = None,
            labels: list[str] | None = None,
            dependencies: list[str] | None = None,
            acceptance_criteria: list[dict] | None = None,
            clarification_questions: list[str] | None = None,
        ):
            """
            Ajoute UNE User Story à partir d'un titre.

            Si une description est fournie, elle est utilisée directement sans appel LLM.
            Sinon, la description et les autres champs manquants sont générés automatiquement.

            Utilise cet outil pour:
            - Les demandes simples comme "ajoute une US pour le login"
            - Ajouter des User Stories après avoir ajouté de nouvelles exigences (add_requirement)
            - Ajouter une US complète avec tous les champs fournis par l'utilisateur
            - Tu peux appeler cet outil plusieurs fois séquentiellement pour ajouter plusieurs stories

            ⚠️ generate_user_stories() ne fonctionne que pour la génération initiale.
            Pour ajouter des stories incrémentalement, utilise TOUJOURS cet outil.

            Args:
                title: Titre de la User Story (ex: "Permettre la connexion SSO")
                epic_name: Nom de l'Epic parent (défaut: "Backlog")
                requirement_ids: Liste des IDs d'exigences liées (optionnel)
                context: Contexte supplémentaire pour guider la génération
                description: Description au format "En tant que [persona], je veux [action], afin de [bénéfice]" (optionnel - si fourni, pas d'appel LLM)
                priority: Priorité - "Haute", "Moyenne", ou "Basse" (optionnel)
                issue_type: Type d'issue Jira - "Story", "Task", ou "Bug" (défaut: "Story")
                story_points: Story points - Fibonacci: 1, 2, 3, 5, 8, 13, 21 (optionnel)
                labels: Étiquettes pour catégorisation (optionnel)
                dependencies: IDs de User Stories pré-requises (optionnel)
                acceptance_criteria: Critères d'acceptation avec scénario et étapes Gherkin (optionnel)
                clarification_questions: Questions de clarification (optionnel)
            """
            # Generate ID
            next_id = get_next_user_story_id(runtime.state)
            epic = epic_name or "Backlog"

            if description is not None:
                # User provided description directly, skip LLM
                expanded: dict = {
                    "description": description,
                    "priority": priority or "Moyenne",
                }
                if story_points is not None:
                    expanded["story_points"] = story_points
                if acceptance_criteria is not None:
                    expanded["acceptance_criteria"] = acceptance_criteria
                if clarification_questions is not None:
                    expanded["clarification_questions"] = clarification_questions
            else:
                # Expand title into full story using internal LLM
                expanded = await self._expand_user_story(
                    title, epic, requirement_ids, context
                )
                # Override LLM-generated fields with user-provided values
                if priority is not None:
                    expanded["priority"] = priority
                if story_points is not None:
                    expanded["story_points"] = story_points
                if acceptance_criteria is not None:
                    expanded["acceptance_criteria"] = acceptance_criteria
                if clarification_questions is not None:
                    expanded["clarification_questions"] = clarification_questions

            # Build complete UserStory
            new_story = {
                "id": next_id,
                "summary": title,
                "epic_name": epic,
                "issue_type": issue_type or "Story",
                "requirement_ids": requirement_ids or [],
                "labels": labels,
                "dependencies": dependencies,
                **expanded,
            }

            # Validate and add to state (reducer handles appending)
            validated = UserStory.model_validate(new_story)

            return Command(
                update={
                    "user_stories": [validated.model_dump()],
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
            description: str | None = None,
            preconditions: str | None = None,
            steps: list[str] | None = None,
            test_data: list[str] | None = None,
            priority: str | None = None,
            expected_result: str | None = None,
        ):
            """
            Ajoute UN test à partir d'un titre.

            Si les étapes (steps) et le résultat attendu (expected_result) sont fournis,
            ils sont utilisés directement sans appel LLM.
            Sinon, les champs manquants sont générés automatiquement.

            Utilise cet outil pour les demandes simples comme "ajoute un test pour US-01".
            Pour générer PLUSIEURS tests, utilise generate_tests().

            Args:
                title: Titre du test (ex: "Vérifier connexion avec identifiants invalides")
                user_story_id: ID de la User Story liée (ex: "US-01")
                test_type: Type de test - "Nominal", "Limite", ou "Erreur" (défaut: "Nominal")
                description: Description du test (optionnel)
                preconditions: Préconditions nécessaires (optionnel)
                steps: Étapes détaillées en format Gherkin (optionnel - si fourni avec expected_result, pas d'appel LLM)
                test_data: Données de test (optionnel)
                priority: Priorité - "Haute", "Moyenne", ou "Basse" (optionnel)
                expected_result: Résultat attendu du test (optionnel - si fourni avec steps, pas d'appel LLM)
            """
            # Validate user_story_id exists
            user_stories = runtime.state.get("user_stories") or []
            story_context = None
            for story in user_stories:
                if story.get("id") == user_story_id:
                    story_context = story
                    break

            if not story_context:
                return (
                    f"⚠️ User Story {user_story_id} non trouvée. "
                    f"Assure-toi que la User Story existe avant d'ajouter un test."
                )

            # Generate ID
            next_id = get_next_test_id(runtime.state)
            ttype = test_type or "Nominal"

            if steps is not None and expected_result is not None:
                # User provided core fields directly, skip LLM
                expanded: dict = {
                    "steps": steps,
                    "expected_result": expected_result,
                    "priority": priority or "Moyenne",
                }
                if description is not None:
                    expanded["description"] = description
                if preconditions is not None:
                    expanded["preconditions"] = preconditions
                if test_data is not None:
                    expanded["test_data"] = test_data
            else:
                # Expand title into full test using internal LLM
                expanded = await self._expand_test(
                    title, user_story_id, ttype, story_context
                )
                # Override LLM-generated fields with user-provided values
                if description is not None:
                    expanded["description"] = description
                if preconditions is not None:
                    expanded["preconditions"] = preconditions
                if steps is not None:
                    expanded["steps"] = steps
                if test_data is not None:
                    expanded["test_data"] = test_data
                if priority is not None:
                    expanded["priority"] = priority
                if expected_result is not None:
                    expanded["expected_result"] = expected_result

            # Build complete Test
            new_test = {
                "id": next_id,
                "name": title,
                "user_story_id": user_story_id,
                "test_type": ttype,
                **expanded,
            }

            # Validate and add to state (reducer handles appending)
            validated = Test.model_validate(new_test)

            return Command(
                update={
                    "tests": [validated.model_dump()],
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
                return f"❌ Type invalide: {item_type}. Types valides: {', '.join(valid_types)}"

            # Check if item exists before removing
            existing = runtime.state.get(item_type) or []
            item_exists = any(item.get("id") == item_id for item in existing)

            if not item_exists:
                return f"⚠️ Élément {item_id} non trouvé dans {item_type}"

            type_labels = {
                "requirements": "exigence",
                "user_stories": "User Story",
                "tests": "test",
            }

            # Use removal marker - reducer will handle filtering
            return Command(
                update={
                    item_type: [{"__remove__": item_id}],
                    "messages": [
                        ToolMessage(
                            f"✓ {type_labels[item_type]} {item_id} supprimé(e)",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return remove_item

    def get_update_requirement_tool(self):
        """Tool to update an existing requirement."""

        @tool
        async def update_requirement(
            runtime: ToolRuntime,
            item_id: str,
            title: str | None = None,
            description: str | None = None,
            priority: str | None = None,
            regenerate: bool = False,
        ):
            """
            Met à jour une exigence existante.

            Args:
                item_id: ID de l'exigence à modifier (ex: "EX-FON-01")
                title: Nouveau titre (optionnel)
                description: Nouvelle description (optionnel)
                priority: Nouvelle priorité - "Haute", "Moyenne", ou "Basse" (optionnel)
                regenerate_description: Si True, régénère la description à partir du nouveau titre
            """
            # Validate item exists
            requirements = runtime.state.get("requirements") or []
            existing = None
            for req in requirements:
                if req.get("id") == item_id:
                    existing = req
                    break

            if not existing:
                return f"❌ Exigence {item_id} non trouvée."

            # Build update fields
            update_fields = {}

            if title is not None:
                update_fields["title"] = title

            if description is not None:
                update_fields["description"] = description
            elif regenerate and title is not None:
                # Regenerate description using LLM
                req_type = "fonctionnelle" if "FON" in item_id else "non-fonctionnelle"
                expanded = await self._expand_requirement(title, req_type, existing)
                update_fields["description"] = expanded["description"]

            if priority is not None:
                # Validate priority
                valid_priorities = ["Haute", "Moyenne", "Basse"]
                if priority not in valid_priorities:
                    return f"❌ Priorité invalide: {priority}. Valeurs acceptées: {', '.join(valid_priorities)}"
                update_fields["priority"] = priority

            if not update_fields:
                return "⚠️ Aucun champ à mettre à jour fourni."

            # Validate with Pydantic (merge with existing to validate full object)
            merged = {**existing, **update_fields}
            try:
                Requirement.model_validate(merged)
            except Exception as e:
                return f"❌ Erreur de validation: {e}"

            # Return update command
            return Command(
                update={
                    "requirements": [{"__update__": item_id, **update_fields}],
                    "messages": [
                        ToolMessage(
                            f"✓ Exigence {item_id} mise à jour.",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return update_requirement

    def get_update_user_story_tool(self):
        """Tool to update an existing user story."""

        @tool
        async def update_user_story(
            runtime: ToolRuntime,
            item_id: str,
            summary: str | None = None,
            description: str | None = None,
            epic_name: str | None = None,
            priority: str | None = None,
            story_points: int | None = None,
            labels: list[str] | None = None,
            requirement_ids: list[str] | None = None,
            dependencies: list[str] | None = None,
            acceptance_criteria: list[dict] | None = None,
            regenerate: bool = False,
        ):
            """
            Met à jour une User Story existante.

            Args:
                item_id: ID de la User Story à modifier (ex: "US-01")
                summary: Nouveau titre/résumé (optionnel)
                description: Nouvelle description (optionnel)
                epic_name: Nouveau nom d'Epic (optionnel)
                priority: Nouvelle priorité - "Haute", "Moyenne", ou "Basse" (optionnel)
                story_points: Nouveaux story points - Fibonacci: 1, 2, 3, 5, 8, 13, 21 (optionnel)
                labels: Nouvelles étiquettes (optionnel)
                requirement_ids: Nouveaux IDs d'exigences liées (optionnel)
                dependencies: Nouvelles dépendances (IDs de User Stories) (optionnel)
                acceptance_criteria: Nouveaux critères d'acceptation (optionnel)
                regenerate: Si True, régénère description/critères à partir du nouveau résumé
            """
            # Validate item exists
            user_stories = runtime.state.get("user_stories") or []
            existing = None
            for story in user_stories:
                if story.get("id") == item_id:
                    existing = story
                    break

            if not existing:
                return f"❌ User Story {item_id} non trouvée."

            # Build update fields
            update_fields = {}

            if summary is not None:
                update_fields["summary"] = summary

            if description is not None:
                update_fields["description"] = description
            elif regenerate and summary is not None:
                # Regenerate using LLM
                epic = epic_name or existing.get("epic_name", "Backlog")
                req_ids = (
                    requirement_ids
                    if requirement_ids is not None
                    else existing.get("requirement_ids")
                )
                expanded = await self._expand_user_story(summary, epic, req_ids, None)
                update_fields["description"] = expanded["description"]
                if "acceptance_criteria" in expanded:
                    update_fields["acceptance_criteria"] = expanded[
                        "acceptance_criteria"
                    ]

            if epic_name is not None:
                update_fields["epic_name"] = epic_name

            if priority is not None:
                valid_priorities = ["Haute", "Moyenne", "Basse"]
                if priority not in valid_priorities:
                    return f"❌ Priorité invalide: {priority}. Valeurs acceptées: {', '.join(valid_priorities)}"
                update_fields["priority"] = priority

            if story_points is not None:
                if story_points < 1 or story_points > 21:
                    return f"❌ Story points invalides: {story_points}. Doit être entre 1 et 21."
                update_fields["story_points"] = story_points

            if labels is not None:
                update_fields["labels"] = labels

            if requirement_ids is not None:
                # Validate requirement IDs exist
                requirements = runtime.state.get("requirements") or []
                existing_req_ids = {r.get("id") for r in requirements}
                invalid_ids = [
                    rid for rid in requirement_ids if rid not in existing_req_ids
                ]
                if invalid_ids:
                    return f"❌ Exigences non trouvées: {', '.join(invalid_ids)}"
                update_fields["requirement_ids"] = requirement_ids

            if dependencies is not None:
                # Validate dependencies exist
                existing_story_ids = {s.get("id") for s in user_stories}
                invalid_deps = [d for d in dependencies if d not in existing_story_ids]
                if invalid_deps:
                    return f"❌ User Stories non trouvées: {', '.join(invalid_deps)}"
                # Check for self-reference
                if item_id in dependencies:
                    return "❌ Dépendance circulaire: une User Story ne peut pas dépendre d'elle-même."
                update_fields["dependencies"] = dependencies

            if acceptance_criteria is not None:
                update_fields["acceptance_criteria"] = acceptance_criteria

            if not update_fields:
                return "⚠️ Aucun champ à mettre à jour fourni."

            # Validate with Pydantic
            merged = {**existing, **update_fields}
            try:
                UserStory.model_validate(merged)
            except Exception as e:
                return f"❌ Erreur de validation: {e}"

            # Return update command
            return Command(
                update={
                    "user_stories": [{"__update__": item_id, **update_fields}],
                    "messages": [
                        ToolMessage(
                            f"✓ User Story {item_id} mise à jour.",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return update_user_story

    def get_update_test_tool(self):
        """Tool to update an existing test."""

        @tool
        async def update_test(
            runtime: ToolRuntime,
            item_id: str,
            name: str | None = None,
            user_story_id: str | None = None,
            description: str | None = None,
            preconditions: str | None = None,
            steps: list[str] | None = None,
            test_data: list[str] | None = None,
            priority: str | None = None,
            test_type: str | None = None,
            expected_result: str | None = None,
            regenerate: bool = False,
        ):
            """
            Met à jour un test existant.

            Args:
                item_id: ID du test à modifier (ex: "SC-01")
                name: Nouveau nom/titre (optionnel)
                user_story_id: Nouveau ID de User Story liée (optionnel)
                description: Nouvelle description (optionnel)
                preconditions: Nouvelles préconditions (optionnel)
                steps: Nouvelles étapes Gherkin (optionnel)
                test_data: Nouvelles données de test (optionnel)
                priority: Nouvelle priorité - "Haute", "Moyenne", ou "Basse" (optionnel)
                test_type: Nouveau type - "Nominal", "Limite", ou "Erreur" (optionnel)
                expected_result: Nouveau résultat attendu (optionnel)
                regenerate: Si True, régénère le test à partir du nouveau nom
            """
            # Validate item exists
            tests = runtime.state.get("tests") or []
            existing = None
            for test in tests:
                if test.get("id") == item_id:
                    existing = test
                    break

            if not existing:
                return f"❌ Test {item_id} non trouvé."

            # Build update fields
            update_fields = {}

            if name is not None:
                update_fields["name"] = name

            if user_story_id is not None:
                # Validate user story exists
                user_stories = runtime.state.get("user_stories") or []
                story_context = None
                for story in user_stories:
                    if story.get("id") == user_story_id:
                        story_context = story
                        break

                if not story_context:
                    return f"❌ User Story {user_story_id} non trouvée."
                update_fields["user_story_id"] = user_story_id

            if description is not None:
                update_fields["description"] = description
            elif regenerate and name is not None:
                # Regenerate using LLM
                us_id = user_story_id or existing.get("user_story_id")
                ttype = test_type or existing.get("test_type", "Nominal")
                user_stories = runtime.state.get("user_stories") or []
                story_context = None
                for story in user_stories:
                    if story.get("id") == us_id:
                        story_context = story
                        break
                expanded = await self._expand_test(name, us_id, ttype, story_context)
                update_fields["description"] = expanded.get("description")
                if "steps" in expanded:
                    update_fields["steps"] = expanded["steps"]
                if "expected_result" in expanded:
                    update_fields["expected_result"] = expanded["expected_result"]

            if preconditions is not None:
                update_fields["preconditions"] = preconditions

            if steps is not None:
                update_fields["steps"] = steps

            if test_data is not None:
                update_fields["test_data"] = test_data

            if priority is not None:
                valid_priorities = ["Haute", "Moyenne", "Basse"]
                if priority not in valid_priorities:
                    return f"❌ Priorité invalide: {priority}. Valeurs acceptées: {', '.join(valid_priorities)}"
                update_fields["priority"] = priority

            if test_type is not None:
                valid_types = ["Nominal", "Limite", "Erreur"]
                if test_type not in valid_types:
                    return f"❌ Type de test invalide: {test_type}. Valeurs acceptées: {', '.join(valid_types)}"
                update_fields["test_type"] = test_type

            if expected_result is not None:
                update_fields["expected_result"] = expected_result

            if not update_fields:
                return "⚠️ Aucun champ à mettre à jour fourni."

            # Validate with Pydantic
            merged = {**existing, **update_fields}
            try:
                Test.model_validate(merged)
            except Exception as e:
                return f"❌ Erreur de validation: {e}"

            # Return update command
            return Command(
                update={
                    "tests": [{"__update__": item_id, **update_fields}],
                    "messages": [
                        ToolMessage(
                            f"✓ Test {item_id} mis à jour.",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        return update_test

    def get_read_items_tool(self):
        """Tool to read/inspect items by type."""

        @tool
        async def read_items(
            runtime: ToolRuntime,
            item_type: str,
            ids: str | list[str],
        ):
            """
            Récupère un ou plusieurs éléments pour consultation.

            Args:
                item_type: Type d'élément - "requirements", "user_stories", ou "tests"
                ids: Liste d'IDs (ex: ["US-01", "US-02"]) ou "all" pour tous les éléments
            """
            valid_types = ["requirements", "user_stories", "tests"]
            if item_type not in valid_types:
                return f"❌ Type invalide: {item_type}. Types valides: {', '.join(valid_types)}"

            type_labels = {
                "requirements": "exigence(s)",
                "user_stories": "User Stor(y/ies)",
                "tests": "test(s)",
            }
            label = type_labels[item_type]

            items = runtime.state.get(item_type) or []

            if not items:
                return f"ℹ️ Aucun(e) {label} n'existe encore."

            if ids == "all":
                return f"📋 {len(items)} {label}:\n\n{json.dumps(items, indent=2, ensure_ascii=False)}"

            if not isinstance(ids, list):
                ids = [ids]

            found = []
            missing = []
            for item_id in ids:
                item = next((i for i in items if i.get("id") == item_id), None)
                if item:
                    found.append(item)
                else:
                    missing.append(item_id)

            message_parts = []
            if found:
                message_parts.append(
                    f"✓ {len(found)} {label} trouvé(e)(s):\n\n{json.dumps(found, indent=2, ensure_ascii=False)}"
                )
            if missing:
                message_parts.append(f"⚠️ Non trouvé(e)(s): {', '.join(missing)}")

            return "\n\n".join(message_parts)

        return read_items
