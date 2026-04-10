"""Custodian starting profile."""

from agentic_backend.core.agents.v2 import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_FS,
    MCPServerRef,
)

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

CUSTODIAN_PROFILE = ReActProfile(
    profile_id="custodian",
    title="Custodian",
    description="Manage files and corpus operations with explicit human approval.",
    role="Data & Corpus Custodian",
    agent_description=(
        "Ensures safe and controlled management of user files, generated reports, "
        "and knowledge corpora."
    ),
    tags=("corpus", "filesystem", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_custodian_system_prompt.md"
    ),
    enable_tool_approval=True,
    approval_required_tools=(
        "build_corpus_toc",
        "revectorize_corpus",
        "purge_vectors",
    ),
    mcp_servers=(
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_FS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
    ),
)
