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

"""Backward-compatible policy contracts.

This module intentionally re-exports the scheduler policy models so older imports keep
working while the source of truth stays under `scheduler/policies`.
"""

from __future__ import annotations

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicies,
    ConversationPolicyCatalog,
    MatchValue,
    PurgeMatch,
    PurgeMode,
    PurgePolicy,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger as PurgeTrigger,
)
from control_plane_backend.scheduler.policies.policy_models import (
    PolicyAction as PurgeAction,
)
from control_plane_backend.scheduler.policies.policy_models import (
    PolicyActionOverride as PurgeActionOverride,
)
from control_plane_backend.scheduler.policies.policy_models import (
    PolicyRule as PurgeRule,
)

__all__ = [
    "ConversationPolicies",
    "ConversationPolicyCatalog",
    "MatchValue",
    "PurgeAction",
    "PurgeActionOverride",
    "PurgeMatch",
    "PurgeMode",
    "PurgePolicy",
    "PurgeRule",
    "PurgeTrigger",
]
