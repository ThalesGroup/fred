"""Tests for control_plane_backend.migration.agent_map."""

from __future__ import annotations

from typing import Any

import pytest

from control_plane_backend.migration.agent_map import (
    IGNORED_KEA_TEMPLATES,
    KEA_TO_SWIFT_TEMPLATE,
    AgentMapOutcome,
    classify_agent,
    resolve_kea_template,
)


def _payload(**overrides: Any) -> dict[str, Any]:
    """Build a minimal exported-agent payload_json for tests."""
    base: dict[str, Any] = {"id": "agent-1", "type": "agent", "enabled": True}
    base.update(overrides)
    return base


# --- resolve_kea_template ----------------------------------------------------


def test_resolve_prefers_definition_ref_over_class_path() -> None:
    payload = _payload(definition_ref="v2.react.basic", class_path="x.y.Z")
    assert resolve_kea_template(payload) == "v2.react.basic"


def test_resolve_falls_back_to_class_path() -> None:
    payload = _payload(
        class_path="agentic_backend.agents.v1.production.prometheus.prometheus_expert.Spot"
    )
    assert (
        resolve_kea_template(payload)
        == "agentic_backend.agents.v1.production.prometheus.prometheus_expert.Spot"
    )


@pytest.mark.parametrize(
    "payload",
    [
        _payload(),
        _payload(definition_ref="", class_path=""),
        _payload(definition_ref="   "),
        _payload(definition_ref=None, class_path=None),
    ],
)
def test_resolve_returns_none_when_no_template(payload: dict[str, Any]) -> None:
    assert resolve_kea_template(payload) is None


# --- classify_agent ----------------------------------------------------------


def test_classify_maps_react_basic_to_assistant() -> None:
    result = classify_agent(_payload(definition_ref="v2.react.basic"))
    assert result.outcome is AgentMapOutcome.MAPPED
    assert result.kea_template == "v2.react.basic"
    assert result.swift_template_id == "fred-agents:fred.github.assistant"


def test_classify_maps_sql_analyst_to_sql_expert() -> None:
    result = classify_agent(_payload(definition_ref="v2.production.sql_analyst"))
    assert result.outcome is AgentMapOutcome.MAPPED
    assert result.swift_template_id == "fred-agents:fred.github.sql_expert"


def test_classify_maps_legacy_class_path() -> None:
    result = classify_agent(
        _payload(
            class_path="agentic_backend.agents.v1.production.prometheus.prometheus_expert.Spot"
        )
    )
    assert result.outcome is AgentMapOutcome.MAPPED
    assert result.swift_template_id == "fred-agents:fred.github.sentinel"


def test_classify_ignores_known_sample() -> None:
    result = classify_agent(_payload(definition_ref="v2.sample.bank_transfer"))
    assert result.outcome is AgentMapOutcome.IGNORED
    assert result.kea_template == "v2.sample.bank_transfer"
    assert result.swift_template_id is None


def test_classify_reports_unknown_template_as_gap() -> None:
    result = classify_agent(_payload(definition_ref="v2.production.unknown_future"))
    assert result.outcome is AgentMapOutcome.GAP
    assert result.kea_template == "v2.production.unknown_future"
    assert result.swift_template_id is None


def test_classify_reports_missing_template_as_gap() -> None:
    result = classify_agent(_payload())
    assert result.outcome is AgentMapOutcome.GAP
    assert result.kea_template is None
    assert result.swift_template_id is None


# --- table invariants --------------------------------------------------------


def test_mapped_and_ignored_sets_are_disjoint() -> None:
    assert not (set(KEA_TO_SWIFT_TEMPLATE) & IGNORED_KEA_TEMPLATES)


def test_all_swift_ids_are_runtime_qualified() -> None:
    # template_id must be "{source_runtime_id}:{source_agent_id}" (single colon).
    for swift_id in KEA_TO_SWIFT_TEMPLATE.values():
        runtime_id, _, agent_id = swift_id.partition(":")
        assert runtime_id and agent_id and swift_id.count(":") == 1
