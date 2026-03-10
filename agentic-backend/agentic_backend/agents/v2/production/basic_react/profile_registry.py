"""Registry helpers for Basic ReAct starting profiles."""

from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

from . import profiles as profiles_pkg
from .profile_model import ReActProfile


@lru_cache(maxsize=1)
def _react_profiles() -> dict[str, ReActProfile]:
    discovered: dict[str, ReActProfile] = {}
    for module_info in pkgutil.iter_modules(
        profiles_pkg.__path__, f"{profiles_pkg.__name__}."
    ):
        module_name = module_info.name.rsplit(".", 1)[-1]
        if module_name.startswith("_") or module_name.endswith("_agent"):
            continue
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if not isinstance(value, ReActProfile):
                continue
            existing = discovered.get(value.profile_id)
            if existing is not None and existing != value:
                raise ValueError(
                    f"Duplicate ReAct profile_id {value.profile_id!r} declared "
                    f"in module {module_info.name!r}."
                )
            discovered[value.profile_id] = value
    return discovered


def list_react_profiles() -> tuple[ReActProfile, ...]:
    profiles = _react_profiles()
    return tuple(profile for _, profile in sorted(profiles.items()))


def get_react_profile(profile_id: str) -> ReActProfile:
    profiles = _react_profiles()
    try:
        return profiles[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(profiles))
        raise ValueError(
            f"Unknown ReAct profile {profile_id!r}. Known profiles: {known}."
        ) from exc


def profile_options_summary() -> str:
    lines = ["Available starting profiles:"]
    for profile in list_react_profiles():
        lines.append(f"- {profile.profile_id}: {profile.description}")
    return "\n".join(lines)
