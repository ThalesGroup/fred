from __future__ import annotations

from pathlib import Path

import pytest

from control_plane_backend.scheduler.policies.policy_engine import (
    _merge_action,
    evaluate_policy_for_request,
    evaluate_purge_policy,
)
from control_plane_backend.scheduler.policies.policy_loader import (
    load_conversation_policy_catalog,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
    LifecycleTrigger,
    PolicyAction,
    PolicyActionOverride,
    PolicyResolutionRequest,
    parse_iso8601_duration,
)


def _catalog_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "config"
        / "conversation_policy_catalog_test.yaml"
    )


def test_policy_engine_resolves_team_override() -> None:
    catalog = load_conversation_policy_catalog(_catalog_path())

    resolved = evaluate_policy_for_request(
        PolicyResolutionRequest(
            team_id="swiftpost",
            trigger=LifecycleTrigger.MEMBER_REMOVED,
        ),
        catalog,
    )

    assert resolved.retention == "PT60S"
    assert resolved.retention_seconds == 60
    assert resolved.matched_rule_id == "purge.team.swiftpost"


def test_policy_engine_resolves_second_team_override() -> None:
    catalog = load_conversation_policy_catalog(_catalog_path())

    resolved = evaluate_policy_for_request(
        PolicyResolutionRequest(
            team_id="northbridge",
            trigger=LifecycleTrigger.MEMBER_REMOVED,
        ),
        catalog,
    )

    assert resolved.mode == "deferred_delete"
    assert resolved.retention == "PT120S"
    assert resolved.retention_seconds == 120


def test_policy_action_optional_retention_fields_parse_and_merge() -> None:
    # A catalog with team_delete_grace/max_idle in `default` and a `rules`
    # override parses through the frozen models.
    catalog = ConversationPolicyCatalog.model_validate(
        {
            "conversation_policies": {
                "purge": {
                    "default": {"team_delete_grace": "P7D", "max_idle": "P30D"},
                    "rules": [
                        {
                            "rule_id": "purge.team.swiftpost",
                            "match": {"team_id": "swiftpost"},
                            "action": {"team_delete_grace": "P1D"},
                        }
                    ],
                }
            }
        }
    )

    purge = catalog.conversation_policies.purge
    default_action = purge.default
    assert default_action.team_delete_grace == "P7D"
    assert default_action.max_idle == "P30D"

    # _merge_action takes the override when present, else the default.
    merged = _merge_action(default_action, purge.rules[0].action)
    assert merged.team_delete_grace == "P1D"  # override present
    assert merged.max_idle == "P30D"  # falls back to default

    # No override at all → default values are preserved.
    empty = _merge_action(default_action, PolicyActionOverride())
    assert empty.team_delete_grace == "P7D"
    assert empty.max_idle == "P30D"


def test_evaluate_purge_policy_surfaces_grace_and_idle() -> None:
    # B3 forward note: evaluate_purge_policy must now surface team_delete_grace
    # and max_idle so the per-team resolver can read the caps.
    catalog = ConversationPolicyCatalog.model_validate(
        {
            "conversation_policies": {
                "purge": {
                    "default": {"team_delete_grace": "P7D", "max_idle": "P30D"},
                    "rules": [
                        {
                            "rule_id": "purge.team.swiftpost",
                            "match": {"team_id": "swiftpost"},
                            "action": {"team_delete_grace": "P1D"},
                        }
                    ],
                }
            }
        }
    )
    purge = catalog.conversation_policies.purge

    # Default branch (no matching rule): both fields come from `default`.
    no_match = evaluate_purge_policy(purge, team_id="northbridge", trigger="x")
    assert no_match.team_delete_grace == "P7D"
    assert no_match.max_idle == "P30D"

    # Matched branch: override wins for grace, default fills max_idle.
    matched = evaluate_purge_policy(purge, team_id="swiftpost", trigger="x")
    assert matched.matched_rule_id == "purge.team.swiftpost"
    assert matched.team_delete_grace == "P1D"
    assert matched.max_idle == "P30D"


def test_policy_action_optional_fields_default_to_none() -> None:
    action = PolicyAction()
    assert action.team_delete_grace is None
    assert action.max_idle is None


@pytest.mark.parametrize("duration", ["P7D", "PT12H", "PT0S", "P1DT2H30M"])
def test_parse_iso8601_duration_supported_values(duration: str) -> None:
    assert parse_iso8601_duration(duration).total_seconds() >= 0


@pytest.mark.parametrize("duration", ["P", "PT"])
def test_parse_iso8601_duration_rejects_empty_duration(duration: str) -> None:
    with pytest.raises(ValueError):
        parse_iso8601_duration(duration)
