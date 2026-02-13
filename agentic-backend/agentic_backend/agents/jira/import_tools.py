"""Import tools for Jira agent - parse markdown exports back into state."""

import logging
import re

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Markdown parsing helpers (deterministic, no LLM)
# ---------------------------------------------------------------------------


def _split_into_sections(markdown: str) -> dict[str, str]:
    """Split markdown into named sections by ``## `` headers."""
    sections: dict[str, str] = {}
    parts = re.split(r"^## ", markdown, flags=re.MULTILINE)
    for part in parts[1:]:
        header, _, body = part.partition("\n")
        sections[header.strip()] = body
    return sections


def _split_into_items(section_text: str) -> list[str]:
    """Split a section into individual items by ``### `` headers."""
    parts = re.split(r"^### ", section_text, flags=re.MULTILINE)
    return [p for p in parts[1:] if p.strip()]


def _extract_bullet(text: str, label: str) -> str | None:
    """Extract ``- **Label:** value`` from *text*."""
    m = re.search(rf"^- \*\*{re.escape(label)}:\*\*\s*(.+)", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _extract_bold_field(text: str, label: str) -> str | None:
    """Extract standalone ``**Label:** value`` (not a bullet)."""
    m = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)", text, re.MULTILINE)
    return m.group(1).strip() if m else None


# ---- Requirements ---------------------------------------------------------


def _parse_requirements(section_text: str) -> list[dict]:
    results: list[dict] = []
    for item in _split_into_items(section_text):
        first_line, _, rest = item.partition("\n")
        m = re.match(r"(.+?):\s*(.+)", first_line.strip())
        if not m:
            continue
        results.append(
            {
                "id": m.group(1).strip(),
                "title": m.group(2).strip(),
                "priority": _extract_bullet(rest, "Priorité") or "Moyenne",
                "description": _extract_bullet(rest, "Description") or "",
            }
        )
    return results


# ---- User Stories ---------------------------------------------------------


def _parse_acceptance_criteria(text: str) -> list[dict]:
    m = re.search(
        r"\*\*Critères d'acceptation:\*\*\n(.*?)(?=\n\*\*Questions de clarification:\*\*|\Z)",
        text,
        re.DOTALL,
    )
    if not m:
        return []

    criteria: list[dict] = []
    current_scenario: str | None = None
    current_steps: list[str] = []

    for line in m.group(1).split("\n"):
        scenario_m = re.match(r"^- \*\*(.+?)\*\*\s*$", line)
        if scenario_m:
            if current_scenario is not None:
                criteria.append({"scenario": current_scenario, "steps": current_steps})
            current_scenario = scenario_m.group(1)
            current_steps = []
        elif re.match(r"^\s+- ", line):
            current_steps.append(re.sub(r"^\s+- ", "", line))

    if current_scenario is not None:
        criteria.append({"scenario": current_scenario, "steps": current_steps})
    return criteria


def _parse_clarification_questions(text: str) -> list[str]:
    m = re.search(r"\*\*Questions de clarification:\*\*\n(.*)", text, re.DOTALL)
    if not m:
        return []
    return [
        qm.group(1).strip()
        for line in m.group(1).split("\n")
        if (qm := re.match(r"^- (.+)", line))
    ]


def _parse_user_stories(section_text: str) -> list[dict]:
    results: list[dict] = []
    for item in _split_into_items(section_text):
        first_line, _, rest = item.partition("\n")
        m = re.match(r"(.+?):\s*(.+)", first_line.strip())
        if not m:
            continue

        story: dict = {
            "id": m.group(1).strip(),
            "summary": m.group(2).strip(),
            "description": _extract_bold_field(rest, "Description") or "",
            "priority": _extract_bullet(rest, "Priorité") or "Moyenne",
        }

        v = _extract_bullet(rest, "Type")
        if v:
            story["issue_type"] = v
        v = _extract_bullet(rest, "Epic")
        if v:
            story["epic_name"] = v
        v = _extract_bullet(rest, "Exigences")
        if v:
            story["requirement_ids"] = [x.strip() for x in v.split(",")]
        v = _extract_bullet(rest, "Dépendances")
        if v:
            story["dependencies"] = [x.strip() for x in v.split(",")]
        v = _extract_bullet(rest, "Story Points")
        if v and v.isdigit():
            story["story_points"] = int(v)
        v = _extract_bullet(rest, "Labels")
        if v:
            story["labels"] = [x.strip() for x in v.split(",")]

        criteria = _parse_acceptance_criteria(rest)
        if criteria:
            story["acceptance_criteria"] = criteria

        questions = _parse_clarification_questions(rest)
        if questions:
            story["clarification_questions"] = questions

        results.append(story)
    return results


# ---- Tests ----------------------------------------------------------------


def _parse_numbered_steps(text: str) -> list[str]:
    m = re.search(r"\*\*Étapes:\*\*\n(.*?)(?=\n\*\*|\Z)", text, re.DOTALL)
    if not m:
        return []
    return [
        sm.group(1).strip()
        for line in m.group(1).split("\n")
        if (sm := re.match(r"^\d+\.\s+(.+)", line))
    ]


def _parse_tests(section_text: str) -> list[dict]:
    results: list[dict] = []
    for item in _split_into_items(section_text):
        first_line, _, rest = item.partition("\n")
        m = re.match(r"(.+?):\s*(.+)", first_line.strip())
        if not m:
            continue

        test: dict = {
            "id": m.group(1).strip(),
            "name": m.group(2).strip(),
            "steps": _parse_numbered_steps(rest),
            "expected_result": _extract_bold_field(rest, "Résultat attendu") or "",
        }

        v = _extract_bullet(rest, "User Story")
        if v:
            test["user_story_id"] = v
        v = _extract_bullet(rest, "Priorité")
        if v:
            test["priority"] = v
        v = _extract_bullet(rest, "Type")
        if v:
            test["test_type"] = v
        v = _extract_bold_field(rest, "Description")
        if v:
            test["description"] = v
        v = _extract_bold_field(rest, "Préconditions")
        if v:
            test["preconditions"] = v
        v = _extract_bold_field(rest, "Données de test")
        if v:
            test["test_data"] = [v]

        results.append(test)
    return results


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------


class ImportTools:
    """Tools for importing markdown exports back into agent state."""

    def __init__(self, agent):
        self.agent = agent

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
            Aucun appel LLM n'est effectué — le parsing est déterministe.

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

            # Deterministic parsing — no LLM calls
            sections = _split_into_sections(markdown_content)

            requirements = _parse_requirements(sections.get("Exigences", ""))
            user_stories = _parse_user_stories(sections.get("User Stories", ""))
            tests = _parse_tests(sections.get("Scénarios de Tests", ""))

            if not any([requirements, user_stories, tests]):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "⚠️ Aucun élément n'a pu être extrait du Markdown fourni. "
                                "Vérifie que le fichier contient des sections "
                                "Exigences, User Stories ou Scénarios de Tests.",
                                tool_call_id=runtime.tool_call_id,
                            ),
                        ],
                    }
                )

            # Build state update
            state_update: dict = {}

            if mode == "overwrite":
                for key, existing in [
                    ("requirements", runtime.state.get("requirements") or []),
                    ("user_stories", runtime.state.get("user_stories") or []),
                    ("tests", runtime.state.get("tests") or []),
                ]:
                    if existing:
                        state_update[key] = [
                            {"__remove__": item.get("id")} for item in existing
                        ]

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
            mode_label = (
                "fusionné(s)" if mode == "merge" else "importé(s) (remplacement)"
            )
            state_update["messages"] = [
                ToolMessage(
                    f"✓ Import réussi : {summary} {mode_label} depuis le Markdown.",
                    tool_call_id=runtime.tool_call_id,
                )
            ]

            logger.info("[JiraAgent] Markdown import (mode=%s): %s", mode, summary)

            return Command(update=state_update)

        return import_markdown
