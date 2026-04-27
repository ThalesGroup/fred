"""Offline tests for fred_runtime.cli.scenario helpers."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from fred_runtime.cli.scenario import (
    ScenarioSkipped,
    _scenario_apply_checks,
    _scenario_resolve,
)


def test_scenario_resolve_replaces_run_id() -> None:
    result = _scenario_resolve("session-${run_id}", run_id="abc123")
    assert result == "session-abc123"


def test_scenario_resolve_substitutes_env_var() -> None:
    with patch.dict(os.environ, {"MY_INSTANCE": "inst-42"}):
        result = _scenario_resolve("${env:MY_INSTANCE}", run_id="x")
    assert result == "inst-42"


def test_scenario_resolve_unknown_env_var_raises_skipped() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ScenarioSkipped, match="MISSING_VAR"):
            _scenario_resolve("${env:MISSING_VAR}", run_id="x")


def test_scenario_apply_checks_kind_passes() -> None:
    final_event = {"kind": "final", "content": "done"}
    _scenario_apply_checks(
        [{"kind": "final"}],
        events=[final_event],
        final_event=final_event,
        step_id="s1",
    )


def test_scenario_apply_checks_kind_fails() -> None:
    final_event = {"kind": "error"}
    with pytest.raises(AssertionError, match="kind"):
        _scenario_apply_checks(
            [{"kind": "final"}],
            events=[final_event],
            final_event=final_event,
            step_id="s1",
        )


def test_scenario_apply_checks_content_contains() -> None:
    final_event = {"kind": "final", "content": "hello world"}
    _scenario_apply_checks(
        [{"content_contains": "hello"}],
        events=[final_event],
        final_event=final_event,
        step_id="s1",
    )


def test_scenario_apply_checks_content_not_contains_fails() -> None:
    final_event = {"kind": "final", "content": "hello world"}
    with pytest.raises(AssertionError):
        _scenario_apply_checks(
            [{"content_not_contains": "hello"}],
            events=[final_event],
            final_event=final_event,
            step_id="s1",
        )


def test_scenario_apply_checks_unknown_check_raises() -> None:
    with pytest.raises(ValueError, match="Unknown check"):
        _scenario_apply_checks(
            [{"bogus_check": True}],
            events=[],
            final_event={},
            step_id="s1",
        )
