"""LogGenius starting profile."""

from agentic_backend.core.agents.v2.builtin_tools import (
    TOOL_REF_LOGS_QUERY,
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
)
from agentic_backend.core.agents.v2.models import ToolRefRequirement

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

LOG_GENIUS_PROFILE = ReActProfile(
    profile_id="log_genius",
    title="LogGenius",
    description="Analyze recent Agentic and Knowledge Flow logs for fast triage.",
    role="log_genius",
    agent_description=(
        "Log analysis assistant for triage across Agentic and Knowledge Flow."
    ),
    tags=("monitoring", "logs", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_log_genius_system_prompt.md"
    ),
    tool_requirements=(
        ToolRefRequirement(
            tool_ref=TOOL_REF_LOGS_QUERY,
            description="Query recent application logs and return a structured triage digest.",
        ),
        ToolRefRequirement(
            tool_ref=TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
            description=(
                "Summarize one Fred conversation from Langfuse traces "
                "(bottlenecks, node path, and timings)."
            ),
        ),
    ),
)
