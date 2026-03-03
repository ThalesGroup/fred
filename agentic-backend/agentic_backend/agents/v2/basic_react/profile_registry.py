"""Registry helpers for Basic ReAct starting profiles."""

from .profile_model import ReActProfile
from .profiles.custodian import CUSTODIAN_PROFILE
from .profiles.generic_assistant import GENERIC_ASSISTANT_PROFILE
from .profiles.geo_demo import GEO_DEMO_PROFILE
from .profiles.georges import GEORGES_PROFILE
from .profiles.log_genius import LOG_GENIUS_PROFILE
from .profiles.rag_expert import RAG_EXPERT_PROFILE
from .profiles.sentinel import SENTINEL_PROFILE

_REACT_PROFILES: dict[str, ReActProfile] = {
    profile.profile_id: profile
    for profile in (
        GENERIC_ASSISTANT_PROFILE,
        GEORGES_PROFILE,
        CUSTODIAN_PROFILE,
        SENTINEL_PROFILE,
        LOG_GENIUS_PROFILE,
        GEO_DEMO_PROFILE,
        RAG_EXPERT_PROFILE,
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
