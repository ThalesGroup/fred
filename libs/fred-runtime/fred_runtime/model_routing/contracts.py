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

"""Local selection results for the central Weaver policy snapshot."""

from __future__ import annotations

from enum import Enum

from fred_core.common import ModelConfiguration
from fred_sdk.contracts.context import FrozenModel, ModelCapability
from pydantic import Field

from ..execution_errors import UserFacingExecutionError

# `FrozenModel` and `ModelCapability` are canonically defined in
# `fred_sdk.contracts.context` (relocated there so control-plane, which
# depends on fred_sdk but not fred_runtime, can speak `ModelCapability` too).
# Imported and re-exported here unchanged so every existing
# `from .contracts import ModelCapability` / `from fred_runtime.model_routing
# import ModelCapability` caller keeps working without modification.


class ModelRoutingError(UserFacingExecutionError):
    """Only fixed, non-secret routing failure sentences reach the user."""


class ModelSelectionSource(str, Enum):
    """Where the final selection came from."""

    DEFAULT = "default"
    USER_CHOICE = "user_choice"
    INSTANCE_RECOMMENDATION = "instance_recommendation"
    WITHDRAWAL_FALLBACK = "withdrawal_fallback"


class ModelSelection(FrozenModel):
    """Resolver decision with audit metadata."""

    source: ModelSelectionSource
    capability: ModelCapability
    profile_id: str
    model: ModelConfiguration
    capability_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Canonical (source_id, upstream_model_id) encoded as a JSON pair. "
            "The retained profile_id field carries the same audit identity; "
            "it does not reference a pod profile or confer permissions."
        ),
    )
