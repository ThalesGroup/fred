"""
Tutorial sample for v2 authored tools.

Two patterns are shown:

1. Sync tools — pure Python logic, no Fred runtime interaction.
   Good for computation, formatting, validation.

2. Async tools — use ctx.publish_text() / ctx.publish_bytes() to store a
   file in Fred and return a download link to the user.
   Good for report generation, export, any tool that produces a file.

Use this when onboarding a developer who needs to write Python-authored tools:
- no business dependencies
- no MCP dependencies
- deterministic outputs
- runnable without an external service (except artifact publishing, which
  requires RuntimeServices.artifact_publisher — marked integration below)
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2.authoring import (
    ReActAgent,
    ToolContext,
    ToolOutput,
    tool,
)

DEFAULT_SYSTEM_PROMPT = """
You are a tutorial assistant.
Prefer short answers and call tools when arithmetic, text formatting, or file
generation is needed.
""".strip()


# ---------------------------------------------------------------------------
# Pattern 1 — Sync tools (pure computation, no await needed)
# ---------------------------------------------------------------------------


@tool(
    tool_ref="sample.math.add",
    description="Add two numbers and return both a sentence and machine-readable JSON.",
    success_message="Addition completed.",
)
def add_numbers(ctx: ToolContext, left: float, right: float) -> ToolOutput:
    total = left + right
    return ctx.json(
        {"left": left, "right": right, "total": total},
        text=f"{left} + {right} = {total}",
    )


@tool(
    tool_ref="sample.text.slugify",
    description="Normalize a text into a lower-case URL slug.",
    success_message="Slug generated.",
)
def slugify_text(ctx: ToolContext, text: str) -> ToolOutput:
    normalized = text.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    if not normalized:
        return ctx.error("Input text cannot be converted to a non-empty slug.")
    return ctx.text(normalized)


@tool(
    tool_ref="sample.time.utc_now",
    description="Return the current UTC timestamp in ISO-8601 format.",
    success_message="UTC timestamp generated.",
)
def utc_now(ctx: ToolContext) -> ToolOutput:
    del ctx
    return ToolOutput(text=datetime.now(tz=UTC).isoformat())


# ---------------------------------------------------------------------------
# Pattern 2 — Async tool that publishes a file and returns a download link
#
# Use ctx.publish_text() to store any text content (markdown, CSV, JSON…)
# in Fred storage. The returned PublishedArtifact carries a download link
# that the UI renders as a clickable file attachment.
#
# Use ctx.publish_bytes() for binary content (XLSX, PDF, images…).
#
# Note: requires RuntimeServices.artifact_publisher at runtime.
# Mark tests that call this tool with @pytest.mark.integration.
# ---------------------------------------------------------------------------


@tool(
    tool_ref="sample.report.generate",
    description=(
        "Generate a short markdown report on a topic and publish it as a "
        "downloadable file. Returns a link the user can click to download."
    ),
    success_message="Report published.",
)
async def generate_report(ctx: ToolContext, topic: str) -> ToolOutput:
    # 1. Build the content (replace this with real business logic)
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    content = f"# Report: {topic}\n\n_Generated on {now}_\n\nAdd your content here.\n"

    # 2. Publish to Fred storage — returns a PublishedArtifact
    artifact = await ctx.publish_text(
        file_name=f"{topic.lower().replace(' ', '_')}_report.md",
        content=content,
        title=f"Report: {topic}",
    )

    # 3. Return the link as a UI part so the user sees a download button,
    #    and a text summary so the model can describe what was produced.
    return ToolOutput(
        text=f"Report on '{topic}' is ready.",
        ui_parts=(artifact.to_link_part(),),
    )


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


class Definition(ReActAgent):
    """
    Tutorial agent exposing both sync and async Python tools.

    Sync tools: add_numbers, slugify_text, utc_now
    Async tool: generate_report (publishes a file and returns a download link)
    """

    agent_id: str = "sample.tutorial.tools.v2"
    role: str = "Tutorial Tools Sample"
    description: str = (
        "Sample agent demonstrating sync computation tools and async file "
        "publishing with download links."
    )
    tags: tuple[str, ...] = ("sample", "tutorial", "tools", "react")
    tools = (add_numbers, slugify_text, utc_now, generate_report)
    system_prompt_template: str = Field(default=DEFAULT_SYSTEM_PROMPT, min_length=1)
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description="Core tutorial instructions for the sample agent.",
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    )


TutorialToolsSampleDefinition = Definition
