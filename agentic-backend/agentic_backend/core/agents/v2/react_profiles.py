"""
Default ReAct profiles for the v2 SDK.

Why this file exists:
- a plain prompt library is not enough to turn a generic ReAct agent into a
  recognisable business assistant
- a useful starting point often includes default MCP services, approval rules,
  tags, and chat affordances alongside the prompt
- profiles keep that business identity visible without creating a new runtime
  model for every small variation
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_spec import MCPServerRef
from agentic_backend.core.agents.v2.models import ToolRefRequirement

from .prompt_resources import load_packaged_markdown


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


GENERIC_ASSISTANT_PROFILE_ID = "generic_assistant"
GEORGES_PROFILE_ID = "georges"
CUSTODIAN_PROFILE_ID = "custodian"
SENTINEL_PROFILE_ID = "sentinel"
LOG_GENIUS_PROFILE_ID = "log_genius"
GEO_DEMO_PROFILE_ID = "geo_demo"

PROFILE_MANAGED_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        "react_profile_id",
        "role",
        "description",
        "tags",
        "system_prompt_template",
        "enable_tool_approval",
        "approval_required_tools",
    }
)


class ReActProfile(FrozenModel):
    """
    Typed business starting point for a generic ReAct agent.

    The goal is to let a team say "start from custodian" or "start from
    sentinel" and get a coherent assistant immediately, instead of rebuilding
    the same defaults by hand every time.
    """

    profile_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    agent_description: str = Field(..., min_length=1)
    tags: tuple[str, ...] = ()
    system_prompt_template: str = Field(..., min_length=1)
    enable_tool_approval: bool = False
    approval_required_tools: tuple[str, ...] = ()
    mcp_servers: tuple[MCPServerRef, ...] = ()
    tool_requirements: tuple[ToolRefRequirement, ...] = ()
    chat_options: AgentChatOptions = Field(default_factory=AgentChatOptions)


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
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "prompts",
            "basic_react_system_prompt.md",
        ),
    ),
)


CUSTODIAN_PROFILE = ReActProfile(
    profile_id=CUSTODIAN_PROFILE_ID,
    title="Custodian",
    description="Manage files and corpus operations with explicit human approval.",
    role="Data & Corpus Custodian",
    agent_description=(
        "Ensures safe and controlled management of user files, generated reports, "
        "and knowledge corpora."
    ),
    tags=("corpus", "filesystem", "react"),
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "prompts",
            "basic_react_custodian_system_prompt.md",
        ),
    ),
    enable_tool_approval=True,
    approval_required_tools=(
        "build_corpus_toc",
        "revectorize_corpus",
        "purge_vectors",
    ),
    mcp_servers=(
        MCPServerRef(id="mcp-knowledge-flow-fs"),
        MCPServerRef(id="mcp-knowledge-flow-corpus"),
    ),
)


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
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "prompts",
            "basic_react_georges_system_prompt.md",
        ),
    ),
)


SENTINEL_PROFILE = ReActProfile(
    profile_id=SENTINEL_PROFILE_ID,
    title="Sentinel",
    description="Monitor platform health with OpenSearch and KPI MCP tools.",
    role="sentinel_expert",
    agent_description=(
        "Operations and monitoring assistant for OpenSearch health, diagnostics, "
        "and platform KPI review."
    ),
    tags=("monitoring", "react"),
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "prompts",
            "basic_react_sentinel_system_prompt.md",
        ),
    ),
    mcp_servers=(MCPServerRef(id="mcp-knowledge-flow-opensearch-ops"),),
)


LOG_GENIUS_PROFILE = ReActProfile(
    profile_id=LOG_GENIUS_PROFILE_ID,
    title="LogGenius",
    description="Analyze recent Agentic and Knowledge Flow logs for fast triage.",
    role="log_genius",
    agent_description=(
        "Log analysis assistant for triage across Agentic and Knowledge Flow."
    ),
    tags=("monitoring", "logs", "react"),
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "prompts",
            "basic_react_log_genius_system_prompt.md",
        ),
    ),
    tool_requirements=(
        ToolRefRequirement(
            tool_ref="logs.query",
            description="Query recent application logs and return a structured triage digest.",
        ),
    ),
)


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
    system_prompt_template=load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "prompts",
            "basic_react_geo_demo_system_prompt.md",
        ),
    ),
    tool_requirements=(
        ToolRefRequirement(
            tool_ref="geo.render_points",
            description="Render one or more latitude/longitude points as a map.",
        ),
    ),
)


_REACT_PROFILES: dict[str, ReActProfile] = {
    profile.profile_id: profile
    for profile in (
        GENERIC_ASSISTANT_PROFILE,
        GEORGES_PROFILE,
        CUSTODIAN_PROFILE,
        SENTINEL_PROFILE,
        LOG_GENIUS_PROFILE,
        GEO_DEMO_PROFILE,
    )
}


def list_react_profiles() -> tuple[ReActProfile, ...]:
    return tuple(_REACT_PROFILES.values())


def get_react_profile(profile_id: str) -> ReActProfile:
    try:
        return _REACT_PROFILES[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(_REACT_PROFILES))
        raise ValueError(
            f"Unknown ReAct profile {profile_id!r}. Known profiles: {known}."
        ) from exc


def profile_options_summary() -> str:
    lines = ["Available starting profiles:"]
    for profile in list_react_profiles():
        lines.append(f"- {profile.profile_id}: {profile.description}")
    return "\n".join(lines)
