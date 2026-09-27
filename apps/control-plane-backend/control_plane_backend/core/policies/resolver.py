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

"""Backward-compatible policy resolver wrappers."""

from __future__ import annotations

from control_plane_backend.scheduler.policies.policy_engine import evaluate_purge_policy
from control_plane_backend.scheduler.policies.policy_models import (
    PolicyEvaluationResult as PurgeResolution,
)
from control_plane_backend.scheduler.policies.policy_models import (
    PolicyResolutionRequest as PurgeSelectionRequest,
)
from control_plane_backend.scheduler.policies.policy_models import (
    PurgePolicy,
)

__all__ = [
    "PurgeResolution",
    "PurgeSelectionRequest",
    "resolve_purge_policy",
]


def resolve_purge_policy(
    policy: PurgePolicy,
    request: PurgeSelectionRequest,
) -> PurgeResolution:
    return evaluate_purge_policy(
        policy,
        team_id=request.team_id,
        trigger=request.trigger.value,
    )
