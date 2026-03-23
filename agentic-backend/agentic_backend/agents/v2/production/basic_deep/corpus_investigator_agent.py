"""
Curated deep agent for corpus investigation workflows.
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    GuardrailDefinition,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.support.builtins import (
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
    TOOL_REF_KNOWLEDGE_SEARCH,
)

from .agent import BasicDeepAgentDefinition
from .prompt_loader import load_basic_deep_prompt

CORPUS_INVESTIGATOR_SYSTEM_PROMPT = load_basic_deep_prompt(
    "corpus_investigator_system_prompt.md"
)


class CorpusInvestigatorDeepV2Definition(BasicDeepAgentDefinition):
    agent_id: str = "deep.corpus_investigator.v2"
    role: str = "Corpus Investigator"
    description: str = (
        "Curated deep research assistant for multi-step investigation over a corpus."
    )
    tags: tuple[str, ...] = ("assistant", "deep", "corpus", "investigation")
    system_prompt_template: str = Field(
        default=CORPUS_INVESTIGATOR_SYSTEM_PROMPT,
        min_length=1,
    )
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description="Core behavior instructions for corpus investigation.",
            required=True,
            default=CORPUS_INVESTIGATOR_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Allow users to attach files for corpus-grounded analysis.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Enable library selection",
            description="Let users choose target libraries for corpus search.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="Enable RAG scope selector",
            description="Let users choose corpus-only vs broader search scope.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Search the selected corpus and return relevant grounded snippets."
            ),
        ),
        ToolRefRequirement(
            tool_ref=TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
            description="Publish a markdown report artifact for the user.",
        ),
    )
    guardrails: tuple[GuardrailDefinition, ...] = (
        GuardrailDefinition(
            guardrail_id="grounding",
            title="Ground claims in corpus evidence",
            description=(
                "Do not present unsupported claims as if they came from corpus evidence."
            ),
        ),
        GuardrailDefinition(
            guardrail_id="uncertainty",
            title="State uncertainty explicitly",
            description=(
                "When evidence is missing or inconclusive, say what is missing."
            ),
        ),
    )
