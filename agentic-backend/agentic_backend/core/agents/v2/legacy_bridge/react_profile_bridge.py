"""
Legacy bridge for Basic ReAct profile lookups.

Why this module exists:
- Basic ReAct profiles are owned by the Basic ReAct agent package, not by the
  generic v2 runtime SDK
- legacy controller, service, and settings code still need one stable place to
  read those profiles while Fred completes the migration away from
  profile-driven `AgentSettings`

How to use it:
- import from this module only in legacy compatibility code
- do not use this module for generic v2 authoring; Basic ReAct profile modules
  should import their model and registry directly from the Basic ReAct package

Example:
- `profile = get_react_profile("custodian")`
- `profiles = list_react_profiles_filtered({"custodian", "sentinel"})`
"""

from __future__ import annotations

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
    Normalize optional Basic ReAct profile allowlist values.

    Why this helper exists:
    - legacy controller and settings code may receive profile allowlists from
      query params, config, or persisted values in mixed shapes
    - downstream code should compare one strict `set[str]` shape instead of
      repeating trimming and empty-value filtering

    How to use it:
    - pass `None` to mean "no restriction"
    - pass any iterable of raw values to get a trimmed `set[str]`

    Example:
    - `allowed = normalize_react_profile_allowlist(["custodian", " sentinel "])`
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
    """
    Return only the Basic ReAct profiles allowed by one optional allowlist.

    Why this helper exists:
    - legacy API/controller code frequently needs "all profiles" or "only these
      profiles" without repeating allowlist normalization logic

    How to use it:
    - pass `None` to return all Basic ReAct profiles
    - pass an iterable of profile ids to keep only matching profiles

    Example:
    - `profiles = list_react_profiles_filtered({"custodian"})`
    """
    profiles = list_react_profiles()
    normalized = normalize_react_profile_allowlist(allowlist)
    if normalized is None:
        return profiles
    return tuple(profile for profile in profiles if profile.profile_id in normalized)


def is_react_profile_allowed(profile_id: str, allowlist: Iterable[str] | None) -> bool:
    """
    Check whether one Basic ReAct profile id is allowed by an optional allowlist.

    Why this helper exists:
    - service-layer permission and settings code should ask one direct question
      instead of open-coding allowlist normalization every time

    How to use it:
    - pass the candidate `profile_id`
    - pass `None` to allow every profile

    Example:
    - `allowed = is_react_profile_allowed("sentinel", {"sentinel", "custodian"})`
    """
    normalized = normalize_react_profile_allowlist(allowlist)
    if normalized is None:
        return True
    return profile_id in normalized


__all__ = [
    "PROFILE_MANAGED_MODEL_FIELDS",
    "ReActProfile",
    "get_react_profile",
    "is_react_profile_allowed",
    "list_react_profiles",
    "list_react_profiles_filtered",
    "normalize_react_profile_allowlist",
    "profile_options_summary",
]
