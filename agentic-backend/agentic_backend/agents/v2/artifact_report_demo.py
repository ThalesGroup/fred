"""
Downloadable report demo for the v2 contract.

Why this file exists:
- It is the clean replacement for the old academy downloadable-content demo.
- It shows the intended business pattern for artifact-producing assistants:
  understand the request, draft a useful deliverable, publish it through Fred,
  and return a secure link to the user.
- It is intentionally ReAct-based because this job is mostly conversational and
  tool-light. The agent does not need a controlled workflow graph; it needs one
  clear publishing capability.

Why a developer should care:
- many real assistants are only valuable once they can hand back a report,
  summary, export, or brief as a durable file
- those deliverables often need an admin-provided template or house style guide
- this example teaches the v2 capability directly, without falling back to
  `AgentFlow.upload_user_blob(...)`
- it demonstrates the right boundary in both directions:
  - fetch existing templates/resources from Fred
  - publish the generated file back through Fred
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
    path_parts=("agents", "v2", "prompts", "artifact_report_demo_system_prompt.md"),
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
    Business demo of a downloadable deliverable agent.

    Use this pattern when the assistant should produce something durable for the
    user, not just a chat answer. The definition stays small:
    - one clear business role
    - one resource-reading capability for templates
    - one publishing capability for the generated file
    - one prompt that explains when to draft, fetch, and publish
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
        Structured behavior contract for the shared ReAct runtime.

        The important business promise is simple:
        - answer directly when the user only wants a normal explanation
        - publish a file when the user asks for a deliverable they should keep
        """

        return ReActPolicy(system_prompt_template=self.system_prompt_template)
