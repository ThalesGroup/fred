# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Runtime catalogue facts mirror the Control Plane's serialized response."""

import json
from typing import Any

import pytest
from fred_sdk.contracts.weaver import RuntimeModels
from pydantic import ValidationError


@pytest.fixture
def runtime_models() -> dict[str, Any]:
    # Synthetic wire data, with no deployment identities or credentials.
    key = {"source_id": "source", "upstream_model_id": "model"}
    return {
        "policy": {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "revision": 1,
            "permitted": [key],
            "default": key,
            "fallback": None,
            "creation_assistant": None,
            "transcription": None,
            "created_by": None,
            "created_at": None,
            "updated_by": None,
            "updated_at": None,
        },
        "default": key,
        "recommendation": None,
        "options": {},
        "offers": [
            {
                "key": key,
                "permitted": True,
                "candidate": True,
                "selectable": True,
                "diagnostics": [],
                "metadata": {
                    "chat": True,
                    "chat_provenance": "source_guarantee",
                    "reasoning": True,
                    "reasoning_efforts": ["low", "high"],
                    "display_name": None,
                    "context_window_tokens": None,
                    "max_input_tokens": None,
                    "max_output_tokens": 100,
                    "provenance": {"reasoning": "provider"},
                },
                "uses": {
                    "unverified": False,
                    "chat": True,
                    "embedding": False,
                    "vision": True,
                    "transcription": False,
                },
                "observation": {
                    "source_id": "source",
                    "source_revision": 1,
                    "enabled": True,
                    "state": "ok",
                    "error_code": None,
                    "checked_at": None,
                    "last_success_at": None,
                    "snapshot_revision": 1,
                    "snapshot_source_revision": 1,
                },
            }
        ],
        "reasoning_default_on": [key],
    }


@pytest.mark.parametrize("empty", [False, True])
def test_runtime_model_facts_round_trip(
    runtime_models: dict[str, Any], empty: bool
) -> None:
    if empty:
        runtime_models["default"] = None
        runtime_models["reasoning_default_on"] = []
    facts = RuntimeModels.model_validate_json(json.dumps(runtime_models))
    serialized = facts.model_dump(mode="json")
    assert serialized["default"] == runtime_models["default"]
    assert serialized["reasoning_default_on"] == runtime_models["reasoning_default_on"]
    assert isinstance(facts.reasoning_default_on, tuple)
    assert RuntimeModels.model_validate_json(facts.model_dump_json()) == facts


@pytest.mark.parametrize("field", ["default", "reasoning_default_on"])
def test_runtime_model_facts_are_required(
    runtime_models: dict[str, Any], field: str
) -> None:
    del runtime_models[field]
    with pytest.raises(ValidationError) as error:
        RuntimeModels.model_validate(runtime_models)
    assert (field,) in [item["loc"] for item in error.value.errors()]
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    "field,value",
    [
        ("default", "model"),
        ("default", {"source_id": "source"}),
        ("reasoning_default_on", None),
        ("reasoning_default_on", True),
        ("reasoning_default_on", ["model"]),
        ("reasoning_default_on", [{"source_id": "source"}]),
        ("legacy_profile_id", None),
        ("requires_reselection", False),
        ("unexpected", True),
    ],
)
def test_invalid_or_unknown_runtime_model_facts_are_refused(
    runtime_models: dict[str, Any], field: str, value: Any
) -> None:
    runtime_models[field] = value
    with pytest.raises(ValidationError) as error:
        RuntimeModels.model_validate(runtime_models)
    assert error.value.errors()[0]["loc"][0] == field
    if field in {"unexpected", "legacy_profile_id", "requires_reselection"}:
        assert error.value.errors()[0]["type"] == "extra_forbidden"
