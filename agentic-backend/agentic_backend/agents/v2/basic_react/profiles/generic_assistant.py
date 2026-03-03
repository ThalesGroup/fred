"""Generic assistant starting profile."""

from ..profile_ids import GENERIC_ASSISTANT_PROFILE_ID
from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

GENERIC_ASSISTANT_PROFILE = ReActProfile(
    profile_id=GENERIC_ASSISTANT_PROFILE_ID,
    title="Generic Assistant",
    description="A general-purpose assistant that can later be equipped with tools.",
    role="General assistant with optional tools",
    agent_description=(
        "A concise assistant that can answer directly or use explicitly declared "
        "platform tools when they are available."
    ),
    tags=("assistant", "react"),
    system_prompt_template=load_basic_react_prompt("basic_react_system_prompt.md"),
)
