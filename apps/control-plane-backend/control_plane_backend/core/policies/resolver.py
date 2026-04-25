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
