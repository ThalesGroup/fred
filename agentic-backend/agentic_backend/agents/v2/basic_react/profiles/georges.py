"""Georges starting profile."""

from ..profile_ids import GEORGES_PROFILE_ID
from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

GEORGES_PROFILE = ReActProfile(
    profile_id=GEORGES_PROFILE_ID,
    title="Georges",
    description="Friendly broad generalist assistant for fallback and open-ended queries.",
    role="Broad and general knowledge assistant",
    agent_description=(
        "Fallback generalist expert used to handle broad queries when no "
        "specialist applies."
    ),
    tags=("fallback", "generalist", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_georges_system_prompt.md"
    ),
)
