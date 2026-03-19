from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    ReActAgentDefinition,
    ReActPolicy,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.builtin_tools import TOOL_REF_KNOWLEDGE_SEARCH
from agentic_backend.core.agents.v2.prompt_resources import load_packaged_markdown

DEFAULT_SYSTEM_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "candidate",
        "DVARiskValidatorAssistant",
        "qa",
        "prompts",
        "dva_risk_validator_qa_system.md",
    ),
)


def _qa_fields() -> tuple[FieldSpec, ...]:
    return (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description="Business instructions for the DVA Q&A assistant.",
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Enable attachments",
            description="Allow session attachments and file uploads.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Enable library selection",
            description="Allow selecting document libraries for retrieval.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.documents_selection",
            type="boolean",
            title="Enable document selection",
            description="Allow selecting specific documents for retrieval.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="Enable RAG scope selection",
            description="Allow choosing corpus-only, hybrid, or general search.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )


class DVARiskValidatorQA(ReActAgentDefinition):
    agent_id: str = "dva.risk_validator.qa.v2"
    role: str = "DVA Risk Validator Q&A"
    description: str = (
        "Answers questions using both the DVA and the generated risk validation report."
    )
    tags: tuple[str, ...] = ("dva", "risk", "qa", "react", "v2")
    system_prompt_template: str = Field(default=DEFAULT_SYSTEM_PROMPT, min_length=1)
    fields: tuple[FieldSpec, ...] = _qa_fields()
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search the DVA, generated report, and risk index.",
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)
