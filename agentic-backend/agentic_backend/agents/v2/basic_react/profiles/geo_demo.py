"""Geo demo starting profile."""

from agentic_backend.core.agents.v2.models import ToolRefRequirement

from ..profile_ids import GEO_DEMO_PROFILE_ID
from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

GEO_DEMO_PROFILE = ReActProfile(
    profile_id=GEO_DEMO_PROFILE_ID,
    title="Geo Demo",
    description="Render lightweight maps from coordinates or well-known places for demos and MVPs.",
    role="geo_demo",
    agent_description=(
        "Small map-oriented assistant that can turn points into a rendered map "
        "using structured UI geo parts."
    ),
    tags=("geo", "map", "demo", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_geo_demo_system_prompt.md"
    ),
    tool_requirements=(
        ToolRefRequirement(
            tool_ref="geo.render_points",
            description="Render one or more latitude/longitude points as a map.",
        ),
    ),
)
