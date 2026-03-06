"""
Compatibility re-export for Basic ReAct profile declarations.

Business ReAct profiles are now owned by the Basic ReAct agent package:
`agentic_backend.agents.v2.production.basic_react.profiles`.

This module stays as a stable import path for existing runtime/catalog code.
"""

from collections.abc import Iterable

from agentic_backend.agents.v2.production.basic_react.profile_model import (
    PROFILE_MANAGED_MODEL_FIELDS,
    ReActProfile,
)
from agentic_backend.agents.v2.production.basic_react.profile_registry import (
    get_react_profile,
    list_react_profiles,
    profile_options_summary,
)


def normalize_react_profile_allowlist(
    allowlist: Iterable[str] | None,
) -> set[str] | None:
    """
    Normalize optional profile allowlist.

    - `None` means no restriction.
    - Empty set means "show/allow none".
    """
    if allowlist is None:
        return None
    normalized: set[str] = set()
    for raw in allowlist:
        profile_id = str(raw).strip()
        if profile_id:
            normalized.add(profile_id)
    return normalized


def list_react_profiles_filtered(
    allowlist: Iterable[str] | None,
) -> tuple[ReActProfile, ...]:
    profiles = list_react_profiles()
    normalized = normalize_react_profile_allowlist(allowlist)
    if normalized is None:
        return profiles
    return tuple(profile for profile in profiles if profile.profile_id in normalized)


def is_react_profile_allowed(profile_id: str, allowlist: Iterable[str] | None) -> bool:
    normalized = normalize_react_profile_allowlist(allowlist)
    if normalized is None:
        return True
    return profile_id in normalized


__all__ = [
    "PROFILE_MANAGED_MODEL_FIELDS",
    "ReActProfile",
    "get_react_profile",
    "list_react_profiles",
    "list_react_profiles_filtered",
    "is_react_profile_allowed",
    "normalize_react_profile_allowlist",
    "profile_options_summary",
]
