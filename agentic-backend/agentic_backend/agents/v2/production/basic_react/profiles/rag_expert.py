"""RAG expert starting profile."""

from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.v2.builtin_tools import TOOL_REF_KNOWLEDGE_SEARCH
from agentic_backend.core.agents.v2.models import (
    GuardrailDefinition,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.prompt_resources import load_packaged_markdown

from ..profile_model import ReActProfile

RAG_EXPERT_PROFILE = ReActProfile(
    profile_id="rag_expert",
    title="RAG Expert",
    description="Document-grounded assistant for retrieval-augmented Q&A.",
    role="Document-grounded RAG expert",
    agent_description=(
        "A retrieval-augmented assistant that answers from selected documents "
        "and clearly distinguishes grounded evidence from uncertainty."
    ),
    tags=("rag", "documents", "react"),
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "production",
            "basic_react",
            "prompts",
            "basic_react_rag_expert_system_prompt.md",
        ),
    ),
    tool_requirements=(
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Search the selected document libraries and session attachments "
                "and return relevant grounded snippets."
            ),
        ),
    ),
    guardrails=(
        GuardrailDefinition(
            guardrail_id="grounding",
            title="Ground answers in retrieved evidence",
            description=(
                "Do not present unsupported claims as if they came from the corpus."
            ),
        ),
        GuardrailDefinition(
            guardrail_id="uncertainty",
            title="State uncertainty explicitly",
            description=(
                "When retrieval is missing or inconclusive, say so clearly "
                "instead of over-claiming."
            ),
        ),
    ),
    chat_options=AgentChatOptions(
        attach_files=True,
        libraries_selection=True,
        search_rag_scoping=True,
    ),
)
