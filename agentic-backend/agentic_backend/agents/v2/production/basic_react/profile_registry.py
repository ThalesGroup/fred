# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    """Return all discovered profiles, sorted by ID."""
    profiles = _react_profiles()
    return tuple(profile for _, profile in sorted(profiles.items()))


def get_react_profile(profile_id: str) -> ReActProfile:
    """
    Return one discovered Basic ReAct profile by its stable profile id.

    Why this function exists:
    - legacy bridge and service code often need to validate or resolve one
      profile id directly instead of scanning the whole profile list
    - keeping the single-profile lookup here avoids duplicating lookup and error
      handling across controller, service, and bridge layers

    How to use it:
    - pass the exact `profile_id` declared by one `ReActProfile`
    - expect `ValueError` when the id is unknown

    Example:
    ```python
    profile = get_react_profile("custodian")
    ```
    """

    normalized_profile_id = profile_id.strip()
    if not normalized_profile_id:
        raise ValueError("ReAct profile id must not be empty.")
    profile = _react_profiles().get(normalized_profile_id)
    if profile is None:
        raise ValueError(
            f"Unknown ReAct profile '{normalized_profile_id}'. "
            "Define it under basic_react/profiles or choose one of the "
            "registered profile ids."
        )
    return profile


def profile_options_summary() -> str:
    """Generate a help string listing available profiles for the CLI/UI."""
    lines = ["Available starting profiles:"]
    for profile in list_react_profiles():
        lines.append(f"- {profile.profile_id}: {profile.description}")
    return "\n".join(lines)
