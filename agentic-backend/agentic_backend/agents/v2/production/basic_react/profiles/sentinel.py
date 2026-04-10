"""Sentinel starting profile."""

from agentic_backend.core.agents.v2 import (
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    MCPServerRef,
)

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

SENTINEL_PROFILE = ReActProfile(
    profile_id="sentinel",
    title="Sentinel",
    description="Monitor platform health with OpenSearch and KPI MCP tools.",
    role="Monitoring assistant",
    agent_description=(
        "Operations and monitoring assistant for OpenSearch health, diagnostics, "
        "and platform KPI review."
    ),
    tags=("monitoring", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_sentinel_system_prompt.md"
    ),
    mcp_servers=(MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS),),
)
