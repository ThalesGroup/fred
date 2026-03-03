"""
Compatibility re-export for Basic ReAct profile declarations.

Business ReAct profiles are now owned by the Basic ReAct agent package:
`agentic_backend.agents.v2.basic_react.profiles`.

This module stays as a stable import path for existing runtime/catalog code.
"""

from agentic_backend.agents.v2.basic_react.profiles import (
    CUSTODIAN_PROFILE_ID,
    GENERIC_ASSISTANT_PROFILE_ID,
    GEO_DEMO_PROFILE_ID,
    GEORGES_PROFILE_ID,
    LOG_GENIUS_PROFILE_ID,
    PROFILE_MANAGED_MODEL_FIELDS,
    RAG_EXPERT_PROFILE_ID,
    SENTINEL_PROFILE_ID,
    ReActProfile,
    get_react_profile,
    list_react_profiles,
    profile_options_summary,
)

__all__ = [
    "CUSTODIAN_PROFILE_ID",
    "GENERIC_ASSISTANT_PROFILE_ID",
    "GEO_DEMO_PROFILE_ID",
    "GEORGES_PROFILE_ID",
    "LOG_GENIUS_PROFILE_ID",
    "PROFILE_MANAGED_MODEL_FIELDS",
    "RAG_EXPERT_PROFILE_ID",
    "ReActProfile",
    "SENTINEL_PROFILE_ID",
    "get_react_profile",
    "list_react_profiles",
    "profile_options_summary",
]
