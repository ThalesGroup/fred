"""Prometheus cluster-wide monitoring starting profile."""

from agentic_backend.core.agents.agent_spec import MCPServerRef

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

PROMETHEUS_PROFILE = ReActProfile(
    profile_id="prometheus",
    title="Prometheus",
    description="Cluster-wide Prometheus and PromQL investigation.",
    role="prometheus_expert",
    agent_description=(
        "Cluster-wide monitoring assistant for Prometheus metric discovery, "
        "PromQL investigation, and cross-namespace troubleshooting."
    ),
    tags=("monitoring", "promql", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_prometheus_system_prompt.md"
    ),
    mcp_servers=(MCPServerRef(id="mcp-knowledge-flow-prometheus-ops"),),
)
