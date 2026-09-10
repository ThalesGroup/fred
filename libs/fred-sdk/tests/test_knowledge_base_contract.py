# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0

"""Behavioral tests for the Knowledge Base authoring surface."""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from fred_sdk import knowledge_base as kb_module
from fred_sdk.contracts.models import FieldSpec
from fred_sdk.knowledge_base import (
    MAX_ISSUE_MESSAGE_CHARS,
    MAX_ISSUES,
    MAX_SUMMARY_CHARS,
    KnowledgeBase,
    KnowledgeBaseDeclarationError,
    KnowledgeBaseIssue,
    KnowledgeBaseManifest,
    KnowledgeBaseRunContext,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
)
from pydantic import BaseModel, ValidationError


def _fields() -> list[FieldSpec]:
    return [
        FieldSpec(key="base_url", type="url", title="Base URL", required=True),
        FieldSpec(key="token", type="secret", title="Token"),
    ]


def _declaration(**overrides: Any) -> KnowledgeBase:
    kwargs: dict[str, Any] = {
        "id": "http-markdown",
        "version": "1.0.0",
        "name": "HTTP Markdown",
        "description": "Synchronize Markdown documents",
        "configuration_fields": _fields(),
    }
    kwargs.update(overrides)
    return KnowledgeBase(**kwargs)


# --------------------------------------------------------------------------
# 1.1 declaration
# --------------------------------------------------------------------------


def test_valid_declaration_keeps_its_fields() -> None:
    kb = _declaration()
    assert kb.id == "http-markdown"
    assert kb.version == "1.0.0"
    assert [f.key for f in kb.configuration_fields] == ["base_url", "token"]


@pytest.mark.parametrize("bad_id", ["", "-leading-dash", "has space", "sla/sh"])
def test_malformed_identifier_is_rejected(bad_id: str) -> None:
    with pytest.raises(KnowledgeBaseDeclarationError, match="must match"):
        _declaration(id=bad_id)


@pytest.mark.parametrize("empty_field", ["version", "name", "description"])
def test_empty_required_declaration_field_is_rejected(empty_field: str) -> None:
    with pytest.raises(KnowledgeBaseDeclarationError, match=empty_field):
        _declaration(**{empty_field: "   "})


def test_duplicate_field_key_is_rejected_naming_the_key() -> None:
    duplicated = [
        FieldSpec(key="base_url", type="url", title="Base URL"),
        FieldSpec(key="base_url", type="string", title="Again"),
    ]
    with pytest.raises(KnowledgeBaseDeclarationError, match="base_url"):
        _declaration(configuration_fields=duplicated)


def test_declaration_reuses_the_canonical_field_vocabulary() -> None:
    assert all(isinstance(f, FieldSpec) for f in _declaration().configuration_fields)


# --------------------------------------------------------------------------
# 1.2 handler registration
# --------------------------------------------------------------------------


def test_one_async_handler_is_accepted_and_returned_unchanged() -> None:
    kb = _declaration()

    @kb.synchronize
    async def synchronize(
        context: KnowledgeBaseRunContext,
    ) -> KnowledgeBaseSyncResult:
        return KnowledgeBaseSyncResult(outcome=KnowledgeBaseRunOutcome.succeeded)

    assert kb.resolve_handler() is synchronize
    assert inspect.iscoroutinefunction(synchronize)


def test_second_handler_is_rejected() -> None:
    kb = _declaration()

    @kb.synchronize
    async def first(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
        return KnowledgeBaseSyncResult(outcome=KnowledgeBaseRunOutcome.succeeded)

    with pytest.raises(KnowledgeBaseDeclarationError, match="already declares"):

        @kb.synchronize
        async def second(
            context: KnowledgeBaseRunContext,
        ) -> KnowledgeBaseSyncResult:
            return KnowledgeBaseSyncResult(outcome=KnowledgeBaseRunOutcome.succeeded)


def test_synchronous_handler_is_rejected() -> None:
    kb = _declaration()

    with pytest.raises(KnowledgeBaseDeclarationError, match="must be async"):

        @kb.synchronize  # type: ignore[arg-type]
        def not_async(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
            return KnowledgeBaseSyncResult(outcome=KnowledgeBaseRunOutcome.succeeded)


def test_resolution_without_a_handler_fails_clearly() -> None:
    with pytest.raises(KnowledgeBaseDeclarationError, match="@kb.synchronize"):
        _declaration().resolve_handler()


# --------------------------------------------------------------------------
# 1.3 context and result
# --------------------------------------------------------------------------


def test_run_context_is_json_safe_and_carries_identifiers() -> None:
    context = KnowledgeBaseRunContext(
        definition_id="http-markdown",
        instance_id="inst-1",
        team_id="team-1",
        run_id="run-1",
        configuration={"base_url": "https://example.invalid", "depth": 3},
    )
    dumped = context.model_dump(mode="json")
    assert json.loads(json.dumps(dumped)) == dumped
    assert dumped["run_id"] == "run-1"


@pytest.mark.parametrize(
    "counter", ["discovered", "created", "updated", "removed", "unchanged"]
)
def test_negative_counters_are_rejected(counter: str) -> None:
    payload: dict[str, Any] = {
        "outcome": KnowledgeBaseRunOutcome.succeeded,
        counter: -1,
    }
    with pytest.raises(ValidationError):
        KnowledgeBaseSyncResult(**payload)


def test_oversized_summary_is_truncated_not_rejected() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.failed, summary="x" * (MAX_SUMMARY_CHARS + 500)
    )
    assert len(result.summary) == MAX_SUMMARY_CHARS


def test_oversized_issue_lists_and_messages_are_truncated() -> None:
    issues = [
        KnowledgeBaseIssue(code="e", message="m" * (MAX_ISSUE_MESSAGE_CHARS + 10))
        for _ in range(MAX_ISSUES + 10)
    ]
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.failed, warnings=issues, errors=issues
    )
    assert len(result.warnings) == MAX_ISSUES
    assert len(result.errors) == MAX_ISSUES
    assert len(result.errors[0].message) == MAX_ISSUE_MESSAGE_CHARS


def test_json_safe_metrics_round_trip() -> None:
    metrics = {"pages": 12, "bytes": 3.5, "sources": ["a", "b"], "ok": True}
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded, metrics=metrics
    )
    dumped = result.model_dump(mode="json")
    assert json.loads(json.dumps(dumped))["metrics"] == metrics


def test_non_json_safe_metrics_are_rejected() -> None:
    with pytest.raises(ValidationError, match="JSON-safe"):
        KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded, metrics={"when": object()}
        )


def test_outcome_offers_only_terminal_states() -> None:
    assert {o.value for o in KnowledgeBaseRunOutcome} == {
        "succeeded",
        "failed",
        "cancelled",
    }


# --------------------------------------------------------------------------
# 1.4 manifest artifact
# --------------------------------------------------------------------------


def test_manifest_round_trips_through_json() -> None:
    manifest = KnowledgeBaseManifest.from_declaration(_declaration())
    payload = json.loads(json.dumps(manifest.model_dump(mode="json")))
    assert KnowledgeBaseManifest.model_validate(payload) == manifest
    assert [f.key for f in manifest.configuration_fields] == ["base_url", "token"]


def test_manifest_declares_a_secret_field_but_carries_no_value() -> None:
    payload = KnowledgeBaseManifest.from_declaration(_declaration()).model_dump(
        mode="json"
    )
    token = next(f for f in payload["configuration_fields"] if f["key"] == "token")
    assert token["type"] == "secret"
    assert token.get("default") is None
    assert "value" not in token


def test_manifest_carries_no_handler_and_no_runtime_state() -> None:
    kb = _declaration()

    @kb.synchronize
    async def synchronize(
        context: KnowledgeBaseRunContext,
    ) -> KnowledgeBaseSyncResult:
        return KnowledgeBaseSyncResult(outcome=KnowledgeBaseRunOutcome.succeeded)

    payload = KnowledgeBaseManifest.from_declaration(kb).model_dump(mode="json")
    assert set(payload) == {
        "id",
        "version",
        "name",
        "description",
        "configuration_fields",
    }
    assert "synchronize" not in json.dumps(payload)


def test_manifest_is_isolated_from_later_declaration_edits() -> None:
    kb = _declaration()
    manifest = KnowledgeBaseManifest.from_declaration(kb)
    kb.configuration_fields[0].title = "Mutated"
    assert manifest.configuration_fields[0].title == "Base URL"


# --------------------------------------------------------------------------
# 1.5 author-facing API purity
# --------------------------------------------------------------------------

_ENGINE_TERMS = (
    "workflow",
    "activity",
    "taskqueue",
    "task_queue",
    "task queue",
    "retry",
    "heartbeat",
    "schedule",
)


def _offending(text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in _ENGINE_TERMS if term in lowered]


def test_public_export_names_carry_no_engine_terms() -> None:
    for name in kb_module.__all__:
        assert not _offending(name), f"{name} exposes an execution-engine term"


def test_public_signatures_and_model_fields_carry_no_engine_terms() -> None:
    for name in kb_module.__all__:
        obj = getattr(kb_module, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            for field_name, field in obj.model_fields.items():
                rendered = f"{field_name} {field.annotation}"
                assert not _offending(rendered), f"{name}.{field_name}"
        if isinstance(obj, type):
            for member_name, member in vars(obj).items():
                if member_name.startswith("_") or not callable(member):
                    continue
                rendered = f"{member_name}{inspect.signature(member)}"
                assert not _offending(rendered), f"{name}.{member_name}"
