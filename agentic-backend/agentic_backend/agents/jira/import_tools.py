"""Import tools for Jira agent - parse markdown exports back into state."""

import asyncio
import logging

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agentic_backend.agents.jira.pydantic_models import (
    RequirementsList,
    TestsList,
    UserStoriesList,
)
from agentic_backend.application_context import get_default_chat_model

logger = logging.getLogger(__name__)


class ImportTools:
    """Tools for importing markdown exports back into agent state."""

    def __init__(self, agent):
        """Initialize import tools with reference to parent agent."""
        self.agent = agent

    def _get_langfuse_handler(self):
        """Get Langfuse handler from parent agent."""
        return self.agent._get_langfuse_handler()

    def _build_llm_config(self) -> RunnableConfig:
        """Build a RunnableConfig with Langfuse callback if enabled."""
        handler = self._get_langfuse_handler()
        return {"callbacks": [handler]} if handler else {}

    async def _parse_requirements(self, markdown_content: str) -> list[dict]:
        """Parse requirements from markdown content using LLM structured output."""
        prompt = """Extrais toutes les exigences du document Markdown suivant.

Le document peut contenir une section "Exigences" avec des entrées au format:
### ID: Titre
- **Priorité:** ...
- **Description:** ...

Si aucune exigence n'est présente dans le document, retourne une liste vide.

Document Markdown:
{markdown_content}"""

        model = get_default_chat_model().with_structured_output(
            RequirementsList, method="json_schema"
        )
        response = await model.ainvoke(
            [SystemMessage(content=prompt.format(markdown_content=markdown_content))],
            config=self._build_llm_config(),
        )
        if not isinstance(response, RequirementsList):
            response = RequirementsList.model_validate(response)
        return [r.model_dump() for r in response.items]

    async def _parse_user_stories(self, markdown_content: str) -> list[dict]:
        """Parse user stories from markdown content using LLM structured output."""
        prompt = """Extrais toutes les User Stories du document Markdown suivant.

Le document peut contenir une section "User Stories" avec des entrées détaillées incluant:
- ID, titre/summary, description, priorité, epic, story points, labels
- Exigences liées (requirement_ids)
- Dépendances (dependencies)
- Critères d'acceptation (acceptance_criteria) avec scénarios et étapes Gherkin
- Questions de clarification

Si aucune User Story n'est présente dans le document, retourne une liste vide.

Document Markdown:
{markdown_content}"""

        model = get_default_chat_model().with_structured_output(
            UserStoriesList, method="json_schema"
        )
        response = await model.ainvoke(
            [SystemMessage(content=prompt.format(markdown_content=markdown_content))],
            config=self._build_llm_config(),
        )
        if not isinstance(response, UserStoriesList):
            response = UserStoriesList.model_validate(response)
        return [s.model_dump() for s in response.items]

    async def _parse_tests(self, markdown_content: str) -> list[dict]:
        """Parse tests from markdown content using LLM structured output."""
        prompt = """Extrais tous les scénarios de tests du document Markdown suivant.

Le document peut contenir une section "Scénarios de Tests" avec des entrées incluant:
- ID, nom, User Story liée, priorité, type de test
- Description, préconditions, étapes (Gherkin), données de test, résultat attendu

Si aucun test n'est présent dans le document, retourne une liste vide.

Document Markdown:
{markdown_content}"""

        model = get_default_chat_model().with_structured_output(
            TestsList, method="json_schema"
        )
        response = await model.ainvoke(
            [SystemMessage(content=prompt.format(markdown_content=markdown_content))],
            config=self._build_llm_config(),
        )
        if not isinstance(response, TestsList):
            response = TestsList.model_validate(response)
        return [t.model_dump() for t in response.items]

    def get_import_markdown_tool(self):
        """Tool that imports a previously exported markdown file back into state."""

        @tool
        async def import_markdown(
            runtime: ToolRuntime,
            markdown_content: str,
            mode: str = "merge",
        ):
            """
            Importe un fichier Markdown précédemment exporté dans l'état de l'agent.

            Cet outil parse le contenu Markdown pour en extraire les exigences,
            User Stories et tests, puis les charge dans l'état.

            IMPORTANT:
            - Le contenu doit provenir d'un fichier Markdown généré par export_deliverables()
            - En mode merge (défaut), les éléments sont ajoutés à l'état existant et les conflits d'IDs sont résolus automatiquement
            - En mode overwrite, tous les éléments existants sont supprimés avant l'import

            Args:
                markdown_content: Contenu brut du fichier Markdown à importer
                mode: "merge" (défaut) pour fusionner avec les éléments existants, "overwrite" pour remplacer tous les éléments existants
            """
            if mode not in ("merge", "overwrite"):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                '❌ Mode invalide. Valeurs acceptées: "merge", "overwrite".',
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            if not markdown_content or len(markdown_content.strip()) < 50:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Le contenu Markdown fourni est trop court ou vide.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Parse all three sections in parallel
            requirements, user_stories, tests = await asyncio.gather(
                self._parse_requirements(markdown_content),
                self._parse_user_stories(markdown_content),
                self._parse_tests(markdown_content),
            )

            if not any([requirements, user_stories, tests]):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "⚠️ Aucun élément n'a pu être extrait du Markdown fourni. "
                                "Vérifie que le fichier contient des exigences, User Stories ou tests.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Build state update
            state_update: dict = {}

            # In overwrite mode, remove all existing items first
            if mode == "overwrite":
                existing_reqs = runtime.state.get("requirements") or []
                existing_stories = runtime.state.get("user_stories") or []
                existing_tests = runtime.state.get("tests") or []

                if existing_reqs:
                    state_update["requirements"] = [
                        {"__remove__": r.get("id")} for r in existing_reqs
                    ]
                if existing_stories:
                    state_update["user_stories"] = [
                        {"__remove__": s.get("id")} for s in existing_stories
                    ]
                if existing_tests:
                    state_update["tests"] = [
                        {"__remove__": t.get("id")} for t in existing_tests
                    ]

            # Add imported items
            summary_parts = []
            if requirements:
                state_update.setdefault("requirements", []).extend(requirements)
                summary_parts.append(f"{len(requirements)} exigence(s)")
            if user_stories:
                state_update.setdefault("user_stories", []).extend(user_stories)
                summary_parts.append(f"{len(user_stories)} User Story(ies)")
            if tests:
                state_update.setdefault("tests", []).extend(tests)
                summary_parts.append(f"{len(tests)} test(s)")

            summary = ", ".join(summary_parts)
            mode_label = "fusionné(s)" if mode == "merge" else "importé(s) (remplacement)"
            state_update["messages"] = [
                ToolMessage(
                    f"✓ Import réussi : {summary} {mode_label} depuis le Markdown.",
                    tool_call_id=runtime.tool_call_id,
                )
            ]

            logger.info(
                "[JiraAgent] Markdown import (mode=%s): %s",
                mode,
                summary,
            )

            return Command(update=state_update)

        return import_markdown
