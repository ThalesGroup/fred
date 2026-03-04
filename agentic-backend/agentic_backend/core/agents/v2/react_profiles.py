"""
Compatibility re-export for Basic ReAct profile declarations.

Business ReAct profiles are now owned by the Basic ReAct agent package:
`agentic_backend.agents.v2.basic_react.profiles`.

This module stays as a stable import path for existing runtime/catalog code.
"""

from agentic_backend.agents.v2.basic_react.profile_model import (
    PROFILE_MANAGED_MODEL_FIELDS,
    ReActProfile,
)
from agentic_backend.agents.v2.basic_react.profile_registry import (
    get_react_profile,
    list_react_profiles,
    profile_options_summary,
)

__all__ = [
    "PROFILE_MANAGED_MODEL_FIELDS",
    "ReActProfile",
    "get_react_profile",
    "list_react_profiles",
    "profile_options_summary",
]
