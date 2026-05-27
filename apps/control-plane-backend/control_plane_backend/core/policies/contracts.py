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
