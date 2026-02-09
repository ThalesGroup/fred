"""Export tools for Jira agent."""

import csv
import io
import tempfile
from datetime import datetime
from pathlib import Path

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart


class ExportTools:
    """Export tools for deliverables."""

    def __init__(self, agent):
        """Initialize export tools with reference to parent agent."""
        self.agent = agent

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
            if story.get("requirement_ids"):
                req_ids = story.get("requirement_ids", [])
                if isinstance(req_ids, list):
                    lines.append(f"- **Exigences:** {', '.join(req_ids)}")
                else:
                    lines.append(f"- **Exigences:** {req_ids}")
            if story.get("dependencies"):
                dependencies = story.get("dependencies", [])
                if isinstance(dependencies, list):
                    lines.append(f"- **Dépendances:** {', '.join(dependencies)}")
                else:
                    lines.append(f"- **Dépendances:** {dependencies}")
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
                    if isinstance(criterion, dict):
                        lines.append(f"- **{criterion.get('scenario', 'Scénario')}**")
                        for step in criterion.get("steps", []):
                            lines.append(f"  - {step}")
                    else:
                        lines.append(f"- {criterion}")
            lines.append("")
            # Add clarification questions if present
            clarification_questions = story.get("clarification_questions", [])
            if clarification_questions:
                lines.append("**Questions de clarification:**")
                for question in clarification_questions:
                    lines.append(f"- {question}")
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

    async def _generate_markdown_file(self, state: dict) -> LinkPart | None:
        """Generate a markdown file from state and return a download link."""
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

        content = "\n".join(sections)

        # Create temp file with markdown content
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".md", prefix="livrables_", mode="w", encoding="utf-8"
        ) as f:
            f.write(content)
            output_path = Path(f.name)

        # Upload to user storage
        try:
            user_id = self.agent.get_end_user_id()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_key = f"{user_id}_livrables_{timestamp}.md"

            with open(output_path, "rb") as f_out:
                upload_result = await self.agent.upload_user_blob(
                    key=final_key,
                    file_content=f_out,
                    filename=f"Livrables_{timestamp}.md",
                    content_type="text/markdown",
                )

            return LinkPart(
                href=upload_result.download_url,
                title=f"📥 Télécharger {upload_result.file_name}",
                kind=LinkKind.download,
                mime="text/markdown",
            )
        finally:
            output_path.unlink(missing_ok=True)

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
            - Summary, Description, Issue Type, Priority, Epic Name, Story Points, Labels

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
                "Issue Type",
                "Priority",
                "Epic Name",
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
                    criteria_lines = []
                    for c in acceptance_criteria:
                        if isinstance(c, dict):
                            criteria_lines.append(f"*{c.get('scenario', 'Scénario')}*")
                            for step in c.get("steps", []):
                                criteria_lines.append(f"  - {step}")
                        else:
                            criteria_lines.append(f"- {c}")
                    criteria_text = "\n".join(criteria_lines)
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
                        "Issue Type": story.get("issue_type", "Story"),
                        "Priority": story.get("priority", "Moyenne"),
                        "Epic Name": story.get("epic_name", ""),
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
            try:
                user_id = self.agent.get_end_user_id()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_key = f"{user_id}_jira_import_{timestamp}.csv"

                with open(output_path, "rb") as f_out:
                    upload_result = await self.agent.upload_user_blob(
                        key=final_key,
                        file_content=f_out,
                        filename=f"jira_import_{timestamp}.csv",
                        content_type="text/csv",
                    )
            finally:
                output_path.unlink(missing_ok=True)

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"✓ Fichier CSV Jira exporté avec succès: [{upload_result.file_name}]({upload_result.download_url})\n\n"
                            f"**Pour importer dans Jira:**\n"
                            f"1. Allez dans votre projet Jira\n"
                            f"2. Menu **Project settings** > **External system import**\n"
                            f"3. Sélectionnez **CSV** et uploadez le fichier\n"
                            f"4. Mappez le champ **Epic Name** vers le champ Epic Link de Jira\n"
                            f"5. Les Epics doivent exister dans le projet ou être créés avant l'import",
                            tool_call_id=runtime.tool_call_id,
                        ),
                    ],
                }
            )

        return export_jira_csv
