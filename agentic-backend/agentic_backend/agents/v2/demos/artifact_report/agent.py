"""
ReAct v2 example focused on generated deliverables.

Use this pattern when a chat answer is not enough and the user needs a file
(brief, report, markdown export) they can download and reuse.
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    ReActAgentDefinition,
    ReActPolicy,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.prompt_resources import load_packaged_markdown

DEFAULT_SYSTEM_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "demos",
        "artifact_report",
        "prompts",
        "artifact_report_demo_system_prompt.md",
    ),
)


def _artifact_report_fields() -> tuple[FieldSpec, ...]:
    return (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description=(
                "Business instructions for the report-writing assistant. Edit this "
                "when you want to change how the generated deliverable should read."
            ),
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    )


class ArtifactReportDemoV2Definition(ReActAgentDefinition):
    """
    Simple deliverable-producing assistant.

    Quick edit guide:
    - prompt: writing style and workflow
    - `resources.fetch_text`: read templates/style guides
    - `artifacts.publish_text`: publish final file
    """

    agent_id: str = "artifact.report.demo.v2"
    role: str = "Downloadable report assistant"
    description: str = (
        "Generates a concise report, brief, or summary, publishes it through Fred "
        "storage, and returns a secure download link to the user."
    )
    tags: tuple[str, ...] = ("artifact", "download", "report", "react", "demo")
    system_prompt_template: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        min_length=1,
    )
    fields: tuple[FieldSpec, ...] = _artifact_report_fields()
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref="resources.fetch_text",
            description="Fetch a stored text template or style guide for this agent.",
        ),
        ToolRefRequirement(
            tool_ref="artifacts.publish_text",
            description="Publish a generated text artifact and return a download link.",
        ),
    )

    def policy(self) -> ReActPolicy:
        """
        Return runtime policy for this assistant.
        """

        return ReActPolicy(system_prompt_template=self.system_prompt_template)
