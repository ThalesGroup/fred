"""
Tiny tutorial sample for v2 authored tools.

Use this when onboarding a new developer:
- no business dependencies
- no MCP dependencies
- very small tools and deterministic outputs
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
Prefer short answers and call tools when arithmetic or text formatting helps.
""".strip()


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


class Definition(ReActAgent):
    """
    Minimal tutorial definition with simple local Python tools.
    """

    agent_id: str = "sample.tutorial.tools.v2"
    role: str = "Tutorial Tools Sample"
    description: str = (
        "Simple v2 sample agent exposing tiny local tools (math, slugify, UTC time)."
    )
    tags: tuple[str, ...] = ("sample", "tutorial", "tools", "react")
    tools = (add_numbers, slugify_text, utc_now)
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
