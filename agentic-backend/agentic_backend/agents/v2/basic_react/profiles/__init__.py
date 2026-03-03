"""Basic ReAct profile declarations and registry helpers."""

from .custodian import CUSTODIAN_PROFILE
from .generic_assistant import GENERIC_ASSISTANT_PROFILE
from .geo_demo import GEO_DEMO_PROFILE
from .georges import GEORGES_PROFILE
from ..profile_ids import (
    CUSTODIAN_PROFILE_ID,
    GENERIC_ASSISTANT_PROFILE_ID,
    GEO_DEMO_PROFILE_ID,
    GEORGES_PROFILE_ID,
    LOG_GENIUS_PROFILE_ID,
    RAG_EXPERT_PROFILE_ID,
    SENTINEL_PROFILE_ID,
)
from .log_genius import LOG_GENIUS_PROFILE
from ..profile_model import PROFILE_MANAGED_MODEL_FIELDS, ReActProfile
from .rag_expert import RAG_EXPERT_PROFILE
from ..profile_registry import (
    get_react_profile,
    list_react_profiles,
    profile_options_summary,
)
from .sentinel import SENTINEL_PROFILE

__all__ = [
    "CUSTODIAN_PROFILE",
    "CUSTODIAN_PROFILE_ID",
    "GENERIC_ASSISTANT_PROFILE",
    "GENERIC_ASSISTANT_PROFILE_ID",
    "GEO_DEMO_PROFILE",
    "GEO_DEMO_PROFILE_ID",
    "GEORGES_PROFILE",
    "GEORGES_PROFILE_ID",
    "LOG_GENIUS_PROFILE",
    "LOG_GENIUS_PROFILE_ID",
    "PROFILE_MANAGED_MODEL_FIELDS",
    "RAG_EXPERT_PROFILE",
    "RAG_EXPERT_PROFILE_ID",
    "ReActProfile",
    "SENTINEL_PROFILE",
    "SENTINEL_PROFILE_ID",
    "get_react_profile",
    "list_react_profiles",
    "profile_options_summary",
]
