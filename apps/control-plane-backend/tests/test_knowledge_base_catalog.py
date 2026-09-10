# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0

"""Startup validation of Knowledge Base definitions configured in a deployment."""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.config.models import PlatformConfig
from control_plane_backend.knowledge_bases.catalog import KnowledgeBaseDefinitionConfig
from fred_sdk.contracts.models import FieldSpec
from pydantic import ValidationError


def _manifest(definition_id: str = "http-markdown") -> dict[str, Any]:
    return {
        "id": definition_id,
        "version": "1.0.0",
        "name": "HTTP Markdown",
        "description": "Synchronize Markdown documents",
        "configuration_fields": [
            FieldSpec(
                key="base_url", type="url", title="Base URL", required=True
            ).model_dump(),
            FieldSpec(key="token", type="secret", title="Token").model_dump(),
        ],
    }


def _definition(
    definition_id: str = "http-markdown", **overrides: Any
) -> KnowledgeBaseDefinitionConfig:
    payload: dict[str, Any] = {
        "manifest": _manifest(definition_id),
        "client_id": f"kb-{definition_id}",
        "task_queue": f"kb-{definition_id}",
    }
    payload.update(overrides)
    return KnowledgeBaseDefinitionConfig(**payload)


def test_valid_definition_is_configured_with_its_bindings() -> None:
    definition = _definition()
    assert definition.definition_id == "http-markdown"
    assert definition.manifest.version == "1.0.0"
    assert [f.key for f in definition.manifest.configuration_fields] == [
        "base_url",
        "token",
    ]
    assert definition.client_id == "kb-http-markdown"


@pytest.mark.parametrize("missing", ["manifest", "client_id", "task_queue"])
def test_each_required_part_is_required(missing: str) -> None:
    payload: dict[str, Any] = {
        "manifest": _manifest(),
        "client_id": "kb-http-markdown",
        "task_queue": "kb-http-markdown",
    }
    del payload[missing]
    with pytest.raises(ValidationError, match=missing):
        KnowledgeBaseDefinitionConfig(**payload)


def test_malformed_manifest_is_rejected() -> None:
    broken = _manifest()
    broken["id"] = "has space"
    with pytest.raises(ValidationError):
        _definition(manifest=broken)


@pytest.mark.parametrize("field", ["client_id", "task_queue"])
def test_unsafe_binding_values_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        _definition(**{field: "kb markdown"})


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _definition(routing_hint="anything")


def test_platform_config_accepts_several_definitions() -> None:
    config = PlatformConfig(
        knowledge_base_definitions=[_definition("http-markdown"), _definition("wiki")]
    )
    assert [e.definition_id for e in config.knowledge_base_definitions] == [
        "http-markdown",
        "wiki",
    ]


def test_platform_config_rejects_duplicate_definition_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate knowledge_base_definitions"):
        PlatformConfig(
            knowledge_base_definitions=[
                _definition("http-markdown"),
                _definition("http-markdown"),
            ]
        )


def test_platform_config_rejects_a_shared_client_id() -> None:
    with pytest.raises(ValidationError, match="Shared knowledge_base_definitions"):
        PlatformConfig(
            knowledge_base_definitions=[
                _definition("http-markdown", client_id="kb-shared"),
                _definition("wiki", client_id="kb-shared"),
            ]
        )


def test_a_deployment_may_configure_no_definitions() -> None:
    assert PlatformConfig().knowledge_base_definitions == []


# --- startup: the deployment configuration is validated where it is loaded ---


def _deployment_payload(definitions: list[dict[str, Any]]) -> dict[str, Any]:
    from fred_core.common import parse_yaml_mapping_file

    payload = parse_yaml_mapping_file("./config/configuration.yaml")
    payload["platform"]["knowledge_base_definitions"] = definitions
    return payload


def _configured(
    definition_id: str = "http-markdown", **overrides: Any
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "manifest": _manifest(definition_id),
        "client_id": f"kb-{definition_id}",
        "task_queue": f"kb-{definition_id}",
    }
    entry.update(overrides)
    return entry


def test_startup_accepts_a_configured_definition() -> None:
    from control_plane_backend.config.models import Configuration

    config = Configuration.model_validate(_deployment_payload([_configured()]))
    assert [e.definition_id for e in config.platform.knowledge_base_definitions] == [
        "http-markdown"
    ]


def test_startup_refuses_an_invalid_configured_definition() -> None:
    from control_plane_backend.config.models import Configuration

    broken = _configured()
    del broken["client_id"]
    with pytest.raises(ValidationError, match="client_id"):
        Configuration.model_validate(_deployment_payload([broken]))


def test_startup_refuses_a_half_valid_catalog() -> None:
    from control_plane_backend.config.models import Configuration

    broken = _configured("wiki")
    broken["manifest"]["version"] = ""
    with pytest.raises(ValidationError):
        Configuration.model_validate(_deployment_payload([_configured(), broken]))
