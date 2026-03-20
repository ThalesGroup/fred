from __future__ import annotations

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    ConversationPolicyCatalog,
    MatchValue,
    PolicyAction,
    PolicyActionOverride,
    PolicyEvaluationResult,
    PolicyResolutionRequest,
    PurgePolicy,
    duration_to_seconds,
)


def _value_matches(expected: MatchValue | None, actual: str | None) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    if isinstance(expected, str):
        return expected == actual
    return actual in expected


def _merge_action(
    default: PolicyAction, override: PolicyActionOverride
) -> PolicyAction:
    return PolicyAction(
        mode=override.mode or default.mode,
        retention=override.retention or default.retention,
        cancel_on_rejoin=(
            default.cancel_on_rejoin
            if override.cancel_on_rejoin is None
            else override.cancel_on_rejoin
        ),
    )


def evaluate_purge_policy(
    policy: PurgePolicy,
    *,
    team_id: str | None,
    trigger: str,
) -> PolicyEvaluationResult:
    default_action = policy.default
    candidates: list[tuple[int, int]] = []

    for idx, rule in enumerate(policy.rules):
        if not _value_matches(rule.match.team_id, team_id):
            continue
        if not _value_matches(rule.match.trigger, trigger):
            continue
        candidates.append((idx, rule.match.defined_criteria_count()))

    if not candidates:
        return PolicyEvaluationResult(
            mode=default_action.mode,
            retention=default_action.retention,
            retention_seconds=default_action.retention_seconds,
            cancel_on_rejoin=default_action.cancel_on_rejoin,
        )

    best_idx, best_specificity = sorted(candidates, key=lambda x: (-x[1], x[0]))[0]
    rule = policy.rules[best_idx]
    action = _merge_action(default_action, rule.action)
    return PolicyEvaluationResult(
        mode=action.mode,
        retention=action.retention,
        retention_seconds=duration_to_seconds(action.retention),
        cancel_on_rejoin=action.cancel_on_rejoin,
        matched_rule_id=rule.rule_id,
        matched_rule_specificity=best_specificity,
    )


def evaluate_conversation_policy(
    event: ConversationLifecycleEvent,
    catalog: ConversationPolicyCatalog,
) -> PolicyEvaluationResult:
    return evaluate_purge_policy(
        catalog.conversation_policies.purge,
        team_id=event.team_id,
        trigger=event.trigger.value,
    )


def evaluate_policy_for_request(
    request: PolicyResolutionRequest,
    catalog: ConversationPolicyCatalog,
) -> PolicyEvaluationResult:
    return evaluate_purge_policy(
        catalog.conversation_policies.purge,
        team_id=request.team_id,
        trigger=request.trigger.value,
    )
