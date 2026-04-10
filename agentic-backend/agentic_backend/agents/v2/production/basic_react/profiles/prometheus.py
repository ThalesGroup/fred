"""Prometheus cluster-wide monitoring starting profile."""

from agentic_backend.core.agents.agent_spec import MCPServerRef

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

PROMETHEUS_PROFILE = ReActProfile(
    profile_id="prometheus",
    title="Spot",
    description="Cluster-wide Prometheus investigation with metric discovery-first PromQL.",
    role="Cluster Prometheus Investigator",
    agent_description=(
        "Investigates cluster-wide Prometheus metrics with discovery-first "
        "PromQL workflows and MCP tools."
    ),
    tags=("monitoring", "promql", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_prometheus_system_prompt.md"
    ),
    mcp_servers=(MCPServerRef(id="mcp-knowledge-flow-prometheus-ops"),),
)
