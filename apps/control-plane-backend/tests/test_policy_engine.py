from __future__ import annotations

from pathlib import Path

import pytest

from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_policy_for_request,
)
from control_plane_backend.scheduler.policies.policy_loader import (
    load_conversation_policy_catalog,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
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


@pytest.mark.parametrize("duration", ["P7D", "PT12H", "PT0S", "P1DT2H30M"])
def test_parse_iso8601_duration_supported_values(duration: str) -> None:
    assert parse_iso8601_duration(duration).total_seconds() >= 0


@pytest.mark.parametrize("duration", ["P", "PT"])
def test_parse_iso8601_duration_rejects_empty_duration(duration: str) -> None:
    with pytest.raises(ValueError):
        parse_iso8601_duration(duration)
