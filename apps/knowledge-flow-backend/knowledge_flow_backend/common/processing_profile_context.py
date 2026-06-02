# Copyright Thales 2025
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

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from knowledge_flow_backend.common.structures import IngestionProcessingProfile

_CURRENT_PROCESSING_PROFILE: ContextVar[IngestionProcessingProfile | None] = ContextVar(
    "knowledge_flow_processing_profile",
    default=None,
)


def coerce_processing_profile(profile: IngestionProcessingProfile | str | None) -> IngestionProcessingProfile | None:
    if profile is None:
        return None
    if isinstance(profile, IngestionProcessingProfile):
        return profile
    if isinstance(profile, (list, tuple)):
        # Defensive compatibility: some payload paths may deserialize enums as char lists, e.g. ['f','a','s','t'].
        if profile and all(isinstance(item, str) and len(item) == 1 for item in profile):
            profile = "".join(profile)
        elif len(profile) == 1 and isinstance(profile[0], str):
            profile = profile[0]
    if isinstance(profile, str):
        return IngestionProcessingProfile(profile.strip().lower())
    raise ValueError(f"{profile!r} is not a valid IngestionProcessingProfile")


def get_current_processing_profile() -> IngestionProcessingProfile | None:
    return _CURRENT_PROCESSING_PROFILE.get()


@contextmanager
def processing_profile_scope(profile: IngestionProcessingProfile | str | None) -> Iterator[IngestionProcessingProfile | None]:
    normalized = coerce_processing_profile(profile)
    token = _CURRENT_PROCESSING_PROFILE.set(normalized)
    try:
        yield normalized
    finally:
        _CURRENT_PROCESSING_PROFILE.reset(token)
