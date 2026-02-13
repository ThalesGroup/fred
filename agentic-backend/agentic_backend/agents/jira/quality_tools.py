"""Quality assessment tools for Jira agent."""

import json
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field

from agentic_backend.application_context import get_default_chat_model

# ---------------------------------------------------------------------------
# Pydantic models for structured assessment output
# ---------------------------------------------------------------------------


class ChecklistItem(BaseModel):
    """A single checklist criterion with its evaluation."""

    criterion: str = Field(description="Nom du critère évalué")
    status: Literal["OK", "Partiel", "Manquant"] = Field(
        description="Statut de l'évaluation: OK (satisfait), Partiel (partiellement satisfait), Manquant (non couvert)"
    )
    comment: str = Field(
        description="Commentaire explicatif justifiant le statut et détaillant les manques éventuels"
    )


class UserStoryAssessment(BaseModel):
    """Structured quality assessment of a user story."""

    us_analysis: list[ChecklistItem] = Field(
        description="Évaluation de la checklist 'Analyse de la User Story'"
    )
    acceptance_criteria_analysis: list[ChecklistItem] = Field(
        description="Évaluation de la checklist 'Critères d'acceptation'"
    )
    summary: str = Field(
        description="Synthèse globale de la qualité de la User Story (2-3 phrases)"
    )
    recommendations: list[str] = Field(
        description="Liste de recommandations concrètes pour améliorer la User Story"
    )


class TestAssessment(BaseModel):
    """Structured quality assessment of a test case."""

    analysis: list[ChecklistItem] = Field(
        description="Évaluation de la checklist 'Cas de test et jeux de données'"
    )
    summary: str = Field(
        description="Synthèse globale de la qualité du test (2-3 phrases)"
    )
    recommendations: list[str] = Field(
        description="Liste de recommandations concrètes pour améliorer le test"
    )


# ---------------------------------------------------------------------------
# Assessment prompts
# ---------------------------------------------------------------------------

US_ASSESSMENT_PROMPT = """Tu es un expert en qualité logicielle et en analyse de User Stories.

Évalue la qualité de la User Story suivante en appliquant les deux checklists ci-dessous.

## User Story à évaluer

{user_story_json}

## Contexte disponible

### Exigences liées
{requirements_json}

### User Stories dont dépend cette US (dépendances)
{dependencies_json}

## Checklist 1 : Analyse de la User Story
Évalue chacun de ces critères :
1. Les objectifs métier de l'US sont clairement identifiés.
2. Les bénéficiaires/utilisateurs concernés sont explicités.
3. Les dépendances avec d'autres US ou modules du projet sont listées.
4. Les hypothèses et prérequis sont mentionnés.
5. Les points d'ambiguïté ou de flou sont relevés et des questions sont générées pour clarification.
6. Les critères de réussite business/techniques sont explicitement recensés.
7. Les risques ou impacts potentiels sont identifiés.

## Checklist 2 : Critères d'acceptation
Évalue chacun de ces critères :
1. Chaque besoin/fonction de l'US est couvert par au moins un critère d'acceptation.
2. Les valeurs limites (maximum, minimum, longueur, etc.) sont explicitement mentionnées.
3. Les valeurs par défaut sont précisées et vérifiées.
4. Les champs/fonctionnalités optionnels et obligatoires sont bien différenciés.
5. Les scénarios d'erreur ou d'usage atypique (champs vides, incohérence, saisie incorrecte…) sont présents.
6. Les critères sont rédigés de façon claire, non ambiguë, et sont testables.
7. Les impacts métier (ex : notification, traçabilité) sont pris en compte.
8. Les critères intègrent des aspects réglementaires/sécurité si applicable.

Pour chaque critère, indique :
- status "OK" si le critère est pleinement satisfait
- status "Partiel" si le critère est partiellement couvert
- status "Manquant" si le critère n'est pas du tout couvert

Fournis aussi une synthèse globale et des recommandations concrètes d'amélioration."""

TEST_ASSESSMENT_PROMPT = """Tu es un expert en qualité logicielle et en conception de tests.

Évalue la qualité du cas de test suivant en appliquant la checklist ci-dessous.

## Test à évaluer

{test_json}

## Contexte disponible

### User Story liée
{user_story_json}

### Autres tests pour la même User Story (pour analyse de couverture)
{sibling_tests_json}

## Checklist : Cas de test et jeux de données
Évalue chacun de ces critères :
1. Les cas nominaux (chemins standards) sont présents.
2. Les cas d'erreur, d'usage inattendu ou de défaillance (inputs invalides, champs vides, etc.) sont inclus.
3. Les valeurs limites (bornes mini/maxi, overflow, etc.) sont testées.
4. Les cas avec valeurs par défaut et valeurs nulles sont prévus.
5. Les jeux de données couvrent la diversité des profils utilisateurs et des contextes d'utilisation.
6. La traçabilité avec les critères d'acceptation est assurée (chaque critère a au moins un cas de test).
7. Les pré-conditions et post-conditions sont clairement décrites pour chaque test.
8. La reproductibilité du test (jeu de données, environnement) est garantie.

Pour chaque critère, indique :
- status "OK" si le critère est pleinement satisfait
- status "Partiel" si le critère est partiellement couvert
- status "Manquant" si le critère n'est pas du tout couvert

Fournis aussi une synthèse globale et des recommandations concrètes d'amélioration."""


# ---------------------------------------------------------------------------
# Tool helper class
# ---------------------------------------------------------------------------


class QualityTools:
    """Quality assessment tools (read-only)."""

    def __init__(self, agent):
        """Initialize quality tools with reference to parent agent."""
        self.agent = agent

    def _get_langfuse_handler(self):
        """Get Langfuse handler from parent agent."""
        return self.agent._get_langfuse_handler()

    def _build_llm_config(self) -> RunnableConfig:
        """Build a RunnableConfig with Langfuse callback if enabled."""
        handler = self._get_langfuse_handler()
        return {"callbacks": [handler]} if handler else {}

    def _format_assessment_report(
        self,
        title: str,
        sections: list[tuple[str, list[ChecklistItem]]],
        summary: str,
        recommendations: list[str],
    ) -> str:
        """Format a structured assessment into a readable report."""
        status_icons = {"OK": "✅", "Partiel": "⚠️", "Manquant": "❌"}

        lines = [f"# {title}", ""]
        for section_title, items in sections:
            lines.append(f"## {section_title}")
            lines.append("")
            for item in items:
                icon = status_icons.get(item.status, "❓")
                lines.append(f"- {icon} **{item.criterion}** [{item.status}]")
                lines.append(f"  {item.comment}")
            lines.append("")

        lines.append("## Synthèse")
        lines.append(summary)
        lines.append("")

        if recommendations:
            lines.append("## Recommandations")
            for rec in recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)

    def get_assess_user_story_tool(self):
        """Tool to assess the quality of a user story."""

        @tool
        async def assess_user_story(
            runtime: ToolRuntime,
            story_id: str,
        ):
            """
            Analyse la qualité d'une User Story en vérifiant deux checklists :
            1) Analyse de la US (objectifs, bénéficiaires, dépendances, hypothèses, ambiguïtés, critères de réussite, risques)
            2) Critères d'acceptation (couverture, valeurs limites, défauts, erreurs, clarté, impacts métier, sécurité)

            Retourne un rapport structuré avec statut OK/Partiel/Manquant pour chaque critère.

            Args:
                story_id: ID de la User Story à évaluer (ex: "US-01")
            """
            # Find the user story
            user_stories = runtime.state.get("user_stories") or []
            story = None
            for s in user_stories:
                if s.get("id") == story_id:
                    story = s
                    break

            if not story:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ User Story {story_id} non trouvée.",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )

            # Gather linked requirements
            requirements = runtime.state.get("requirements") or []
            linked_req_ids = story.get("requirement_ids") or []
            linked_requirements = [
                r for r in requirements if r.get("id") in linked_req_ids
            ]

            # Gather dependency user stories
            dep_ids = story.get("dependencies") or []
            dependency_stories = [s for s in user_stories if s.get("id") in dep_ids]

            # Build the prompt
            prompt = US_ASSESSMENT_PROMPT.format(
                user_story_json=json.dumps(story, indent=2, ensure_ascii=False),
                requirements_json=json.dumps(
                    linked_requirements, indent=2, ensure_ascii=False
                )
                if linked_requirements
                else "Aucune exigence liée.",
                dependencies_json=json.dumps(
                    dependency_stories, indent=2, ensure_ascii=False
                )
                if dependency_stories
                else "Aucune dépendance déclarée.",
            )

            # Call LLM with structured output
            model = get_default_chat_model().with_structured_output(
                UserStoryAssessment, method="json_schema"
            )
            result = await model.ainvoke(
                [SystemMessage(content=prompt)], config=self._build_llm_config()
            )
            if not isinstance(result, UserStoryAssessment):
                result = UserStoryAssessment.model_validate(result)

            # Format the report
            report = self._format_assessment_report(
                title=f"Analyse qualité - {story_id}: {story.get('summary', '')}",
                sections=[
                    ("Analyse de la User Story", result.us_analysis),
                    ("Critères d'acceptation", result.acceptance_criteria_analysis),
                ],
                summary=result.summary,
                recommendations=result.recommendations,
            )

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            report,
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )

        return assess_user_story

    def get_assess_test_tool(self):
        """Tool to assess the quality of a test case."""

        @tool
        async def assess_test(
            runtime: ToolRuntime,
            test_id: str,
        ):
            """
            Analyse la qualité d'un cas de test en vérifiant la checklist :
            cas nominaux, erreurs, valeurs limites, défauts/nulls, diversité, traçabilité, pré/post-conditions, reproductibilité.

            Retourne un rapport structuré avec statut OK/Partiel/Manquant pour chaque critère.

            Args:
                test_id: ID du test à évaluer (ex: "SC-01")
            """
            # Find the test
            tests = runtime.state.get("tests") or []
            target_test = None
            for t in tests:
                if t.get("id") == test_id:
                    target_test = t
                    break

            if not target_test:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ Test {test_id} non trouvé.",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )

            # Find linked user story
            us_id = target_test.get("user_story_id")
            user_stories = runtime.state.get("user_stories") or []
            linked_story = None
            if us_id:
                for s in user_stories:
                    if s.get("id") == us_id:
                        linked_story = s
                        break

            # Find sibling tests (same user story)
            sibling_tests = (
                [
                    t
                    for t in tests
                    if t.get("user_story_id") == us_id and t.get("id") != test_id
                ]
                if us_id
                else []
            )

            # Build the prompt
            prompt = TEST_ASSESSMENT_PROMPT.format(
                test_json=json.dumps(target_test, indent=2, ensure_ascii=False),
                user_story_json=json.dumps(linked_story, indent=2, ensure_ascii=False)
                if linked_story
                else "Aucune User Story liée.",
                sibling_tests_json=json.dumps(
                    sibling_tests, indent=2, ensure_ascii=False
                )
                if sibling_tests
                else "Aucun autre test pour cette User Story.",
            )

            # Call LLM with structured output
            model = get_default_chat_model().with_structured_output(
                TestAssessment, method="json_schema"
            )
            result = await model.ainvoke(
                [SystemMessage(content=prompt)], config=self._build_llm_config()
            )
            if not isinstance(result, TestAssessment):
                result = TestAssessment.model_validate(result)

            # Format the report
            report = self._format_assessment_report(
                title=f"Analyse qualité - {test_id}: {target_test.get('name', '')}",
                sections=[
                    ("Cas de test et jeux de données", result.analysis),
                ],
                summary=result.summary,
                recommendations=result.recommendations,
            )

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            report,
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )

        return assess_test
