"""Base assistant starting profile."""

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

BASE_ASSISTANT_PROFILE = ReActProfile(
    profile_id="base_assistant",
    title="Base Assistant",
    description="General-purpose assistant with no preconfigured tools.",
    role="General assistant with optional tools",
    agent_description=(
        "Neutral starting point for ReAct agents without preset MCP servers, "
        "declared tool refs, or approval rules."
    ),
    tags=("assistant", "react"),
    system_prompt_template=load_basic_react_prompt("basic_react_system_prompt.md"),
)
