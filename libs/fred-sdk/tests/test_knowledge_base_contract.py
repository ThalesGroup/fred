# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0

"""Behavioral tests for the Knowledge Base authoring surface."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Coroutine
from typing import Any, get_args, get_origin

import pytest
from fred_sdk import knowledge_base as kb_module
from fred_sdk.contracts.models import FieldSpec
from fred_sdk.knowledge_base import (
    MAX_ISSUE_MESSAGE_CHARS,
    MAX_ISSUE_SUBJECT_CHARS,
    MAX_ISSUES,
    MAX_SUMMARY_CHARS,
    KnowledgeBase,
    KnowledgeBaseDeclaration,
    KnowledgeBaseDeclarationError,
    KnowledgeBaseIssue,
    KnowledgeBaseRunContext,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
    SynchronizeHandler,
)
from pydantic import BaseModel, ValidationError


def _fields() -> list[FieldSpec]:
    return [
        FieldSpec(key="base_url", type="url", title="Base URL", required=True),
        FieldSpec(key="token", type="secret", title="Token"),
    ]


def _declaration(**overrides: Any) -> KnowledgeBase:
    kwargs: dict[str, Any] = {
        "id": "acme.kb.http-markdown",
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
    assert kb.id == "acme.kb.http-markdown"
    assert kb.version == "1.0.0"
    assert [f.key for f in kb.configuration_fields] == ["base_url", "token"]


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "-leading-dash",
        "has space",
        "sla/sh",
        "assistant",
        "acme.kb.local__folder",
        "Acme.Kb.Local",
        "acme.kb.local-",
        "acme..local",
    ],
    ids=[
        "empty",
        "leading-separator",
        "space",
        "slash",
        "one-segment-carries-no-provenance",
        "doubled-underscore",
        "uppercase",
        "trailing-separator",
        "empty-segment",
    ],
)
def test_malformed_identifier_is_rejected(bad_id: str) -> None:
    with pytest.raises(KnowledgeBaseDeclarationError, match="contributed name"):
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
        return KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded, reconciliation_complete=True
        )

    assert kb.resolve_handler() is synchronize
    assert inspect.iscoroutinefunction(synchronize)


def test_second_handler_is_rejected() -> None:
    kb = _declaration()

    @kb.synchronize
    async def first(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
        return KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded, reconciliation_complete=True
        )

    with pytest.raises(KnowledgeBaseDeclarationError, match="already declares"):

        @kb.synchronize
        async def second(
            context: KnowledgeBaseRunContext,
        ) -> KnowledgeBaseSyncResult:
            return KnowledgeBaseSyncResult(
                outcome=KnowledgeBaseRunOutcome.succeeded, reconciliation_complete=True
            )


def test_synchronous_handler_is_rejected() -> None:
    kb = _declaration()

    with pytest.raises(KnowledgeBaseDeclarationError, match="must be async"):

        @kb.synchronize  # type: ignore[arg-type]
        def not_async(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
            return KnowledgeBaseSyncResult(
                outcome=KnowledgeBaseRunOutcome.succeeded, reconciliation_complete=True
            )


def test_resolution_without_a_handler_fails_clearly() -> None:
    with pytest.raises(KnowledgeBaseDeclarationError, match="@kb.synchronize"):
        _declaration().resolve_handler()


# --------------------------------------------------------------------------
# 1.3 context and result
# --------------------------------------------------------------------------


def test_run_context_is_json_safe_and_carries_identifiers() -> None:
    context = KnowledgeBaseRunContext(
        definition_id="acme.kb.http-markdown",
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
        "reconciliation_complete": True,
        counter: -1,
    }
    with pytest.raises(ValidationError):
        KnowledgeBaseSyncResult(**payload)


def test_oversized_summary_is_truncated_not_rejected() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.failed,
        reconciliation_complete=True,
        summary="x" * (MAX_SUMMARY_CHARS + 500),
    )
    assert len(result.summary) == MAX_SUMMARY_CHARS


def test_oversized_issue_lists_and_messages_are_truncated() -> None:
    issues = [
        KnowledgeBaseIssue(code="e", message="m" * (MAX_ISSUE_MESSAGE_CHARS + 10))
        for _ in range(MAX_ISSUES + 10)
    ]
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.failed,
        reconciliation_complete=True,
        warnings=issues,
        errors=issues,
    )
    assert len(result.warnings) == MAX_ISSUES
    assert len(result.errors) == MAX_ISSUES
    assert len(result.errors[0].message) == MAX_ISSUE_MESSAGE_CHARS


def test_json_safe_metrics_round_trip() -> None:
    metrics = {"pages": 12, "bytes": 3.5, "sources": ["a", "b"], "ok": True}
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        metrics=metrics,
    )
    dumped = result.model_dump(mode="json")
    assert json.loads(json.dumps(dumped))["metrics"] == metrics


def test_non_json_safe_metrics_are_rejected() -> None:
    with pytest.raises(ValidationError, match="JSON-safe"):
        KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded,
            reconciliation_complete=True,
            metrics={"when": object()},
        )


def test_outcome_offers_only_terminal_states() -> None:
    assert {o.value for o in KnowledgeBaseRunOutcome} == {
        "succeeded",
        "failed",
        "cancelled",
    }


# --------------------------------------------------------------------------
# 1.4 published declaration payload
# --------------------------------------------------------------------------


def test_declaration_payload_round_trips_through_json() -> None:
    declaration = KnowledgeBaseDeclaration.of(_declaration())
    payload = json.loads(json.dumps(declaration.model_dump(mode="json")))
    assert KnowledgeBaseDeclaration.model_validate(payload) == declaration
    assert [f.key for f in declaration.configuration_fields] == ["base_url", "token"]


def test_declaration_payload_declares_a_secret_field_but_carries_no_value() -> None:
    payload = KnowledgeBaseDeclaration.of(_declaration()).model_dump(mode="json")
    token = next(f for f in payload["configuration_fields"] if f["key"] == "token")
    assert token["type"] == "secret"
    assert token.get("default") is None
    assert "value" not in token


def test_declaration_payload_carries_no_handler_and_no_runtime_state() -> None:
    kb = _declaration()

    @kb.synchronize
    async def synchronize(
        context: KnowledgeBaseRunContext,
    ) -> KnowledgeBaseSyncResult:
        return KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded, reconciliation_complete=True
        )

    payload = KnowledgeBaseDeclaration.of(kb).model_dump(mode="json")
    assert set(payload) == {
        "id",
        "version",
        "name",
        "description",
        "configuration_fields",
    }
    assert "synchronize" not in json.dumps(payload)


def test_declaration_payload_is_isolated_from_later_declaration_edits() -> None:
    kb = _declaration()
    declaration = KnowledgeBaseDeclaration.of(kb)
    kb.configuration_fields[0].title = "Mutated"
    assert declaration.configuration_fields[0].title == "Base URL"


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


# --------------------------------------------------------------------------
# Corrections found by the first real consumer (fred-samples proof)
# --------------------------------------------------------------------------


def test_resolved_handler_is_accepted_by_asyncio_run_without_a_cast() -> None:
    """`Coroutine`, not `Awaitable`: a bare awaitable is not runnable.

    The consumer proof had to cast around the old annotation to hand the
    resolved handler to `asyncio.run`, so the type is asserted here rather than
    left to a reviewer's eye.
    """
    kb = _declaration()

    @kb.synchronize
    async def synchronize(
        context: KnowledgeBaseRunContext,
    ) -> KnowledgeBaseSyncResult:
        return KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded, reconciliation_complete=True
        )

    context = KnowledgeBaseRunContext(
        definition_id="acme.kb.http-markdown", instance_id="i", team_id="t", run_id="r"
    )
    result = asyncio.run(kb.resolve_handler()(context))
    assert result.outcome is KnowledgeBaseRunOutcome.succeeded

    origin = get_args(SynchronizeHandler)[1]
    assert get_origin(origin) is Coroutine


def test_reconciliation_completeness_is_required_and_independent_of_outcome() -> None:
    with pytest.raises(ValidationError, match="reconciliation_complete"):
        KnowledgeBaseSyncResult(outcome=KnowledgeBaseRunOutcome.succeeded)  # type: ignore[call-arg]

    bounded = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=False,
        discovered=10,
    )
    assert bounded.outcome is KnowledgeBaseRunOutcome.succeeded
    assert bounded.reconciliation_complete is False


def test_removed_is_a_report_of_executed_retractions() -> None:
    """A partial pass may still have retracted on an explicit tombstone."""
    partial = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=False,
        removed=2,
    )
    assert partial.removed == 2
    assert partial.reconciliation_complete is False
    dumped = partial.model_dump(mode="json")
    assert dumped["removed"] == 2
    assert dumped["reconciliation_complete"] is False


def test_content_truncated_is_serialized_and_false_when_nothing_was_cut() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        summary="short",
        warnings=[KnowledgeBaseIssue(code="w", message="brief")],
    )
    assert result.content_truncated is False
    assert result.model_dump(mode="json")["content_truncated"] is False


def test_content_truncated_reports_a_clipped_summary() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        summary="x" * (MAX_SUMMARY_CHARS + 1),
    )
    assert result.content_truncated is True
    assert result.model_dump(mode="json")["content_truncated"] is True


def test_content_truncated_reports_a_clipped_issue_message() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.failed,
        reconciliation_complete=True,
        errors=[
            KnowledgeBaseIssue(code="e", message="m" * (MAX_ISSUE_MESSAGE_CHARS + 1))
        ],
    )
    assert result.content_truncated is True


def test_content_truncated_reports_a_dropped_issue_beyond_the_cap() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.failed,
        reconciliation_complete=True,
        warnings=[KnowledgeBaseIssue(code="w") for _ in range(MAX_ISSUES + 1)],
    )
    assert len(result.warnings) == MAX_ISSUES
    assert result.content_truncated is True


def test_content_truncated_cannot_be_forced_false_by_the_caller() -> None:
    payload: dict[str, Any] = {
        "outcome": KnowledgeBaseRunOutcome.succeeded,
        "reconciliation_complete": True,
        "summary": "x" * (MAX_SUMMARY_CHARS + 1),
        "content_truncated": False,
    }
    assert KnowledgeBaseSyncResult(**payload).content_truncated is True
    assert "content_truncated" not in KnowledgeBaseSyncResult.model_fields


def test_issue_subject_is_optional_generic_and_bounded() -> None:
    assert KnowledgeBaseIssue(code="w").subject is None

    plain = KnowledgeBaseIssue(code="w", subject="report-2024")
    assert plain.subject == "report-2024"

    # Bounds are applied by the result carrying the issue, which is the only
    # thing that gets recorded.
    reported = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        warnings=[
            KnowledgeBaseIssue(code="w", subject="s" * (MAX_ISSUE_SUBJECT_CHARS + 10))
        ],
    )
    assert len(reported.warnings[0].subject or "") == MAX_ISSUE_SUBJECT_CHARS

    # Severity stays in which list the issue lands in, and the subject stays
    # generic — no `path` field, and no severity field here.
    assert "path" not in KnowledgeBaseIssue.model_fields
    assert "severity" not in KnowledgeBaseIssue.model_fields


def test_published_payload_is_compact_and_carries_no_client_binding() -> None:
    payload = KnowledgeBaseDeclaration.of(_declaration()).to_payload()

    assert json.loads(json.dumps(payload)) == payload
    assert set(payload) == {
        "id",
        "version",
        "name",
        "description",
        "configuration_fields",
    }
    assert "client_id" not in payload
    assert "task_queue" not in payload

    # exclude_defaults/exclude_none: the optional token field declared nothing
    # but its key, type and title, so nothing else is emitted for it.
    token = next(f for f in payload["configuration_fields"] if f["key"] == "token")
    assert token == {"key": "token", "type": "secret", "title": "Token"}


# 2b.6 truncation is detected where the clipping happens


def test_content_exactly_at_its_bound_is_not_reported_as_truncated() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        summary="x" * MAX_SUMMARY_CHARS,
        warnings=[
            KnowledgeBaseIssue(
                code="w",
                message="m" * MAX_ISSUE_MESSAGE_CHARS,
                subject="s" * MAX_ISSUE_SUBJECT_CHARS,
            )
        ]
        * MAX_ISSUES,
    )
    assert result.content_truncated is False
    assert len(result.summary) == MAX_SUMMARY_CHARS
    assert len(result.warnings) == MAX_ISSUES


@pytest.mark.parametrize(
    "over",
    [
        {"summary": "x" * (MAX_SUMMARY_CHARS + 1)},
        {
            "warnings": [
                KnowledgeBaseIssue(
                    code="w", message="m" * (MAX_ISSUE_MESSAGE_CHARS + 1)
                )
            ]
        },
        {
            "errors": [
                KnowledgeBaseIssue(
                    code="e", subject="s" * (MAX_ISSUE_SUBJECT_CHARS + 1)
                )
            ]
        },
        {"errors": [KnowledgeBaseIssue(code="e")] * (MAX_ISSUES + 1)},
    ],
)
def test_content_one_over_its_bound_is_reported_as_truncated(over: dict) -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        **over,
    )
    assert result.content_truncated is True


def test_content_one_under_its_bound_is_untouched() -> None:
    result = KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded,
        reconciliation_complete=True,
        summary="x" * (MAX_SUMMARY_CHARS - 1),
    )
    assert result.content_truncated is False
    assert len(result.summary) == MAX_SUMMARY_CHARS - 1


# 2c.4 routing is derived, identically on both sides


def test_task_queue_is_a_pure_function_of_the_name() -> None:
    from fred_sdk.knowledge_base.routing import task_queue_for

    assert task_queue_for("acme.kb.local-folder") == task_queue_for(
        "acme.kb.local-folder"
    )
    assert task_queue_for("acme.kb.local-folder") != task_queue_for(
        "acme.kb.http-markdown"
    )
    assert "acme.kb.local-folder" in task_queue_for("acme.kb.local-folder")


def test_task_queue_separates_two_contributors_using_the_same_last_segment() -> None:
    from fred_sdk.knowledge_base.routing import task_queue_for

    assert task_queue_for("acme.kb.local-folder") != task_queue_for(
        "globex.kb.local-folder"
    )


def test_task_queue_matches_the_catalog_id_control_plane_derives() -> None:
    from fred_core import knowledge_base_catalog_id
    from fred_sdk.knowledge_base.routing import task_queue_for

    assert task_queue_for("acme.kb.local-folder") == knowledge_base_catalog_id(
        "acme.kb.local-folder"
    )


def test_task_queue_refuses_an_empty_name() -> None:
    from fred_sdk.knowledge_base.routing import task_queue_for

    with pytest.raises(ValueError):
        task_queue_for("")


# 2c.5 the pod environment contract


def test_publish_needs_no_workflow_engine_in_its_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_sdk.knowledge_base import environment as env

    for name in (env.CONTROL_PLANE_URL_ENV, env.KEYCLOAK_REALM_URL_ENV):
        monkeypatch.setenv(name, "http://example.invalid/x/")
    monkeypatch.setenv(env.PREFIX_ENV, "acme.kb")
    monkeypatch.setenv(env.CLIENT_ID_ENV, "kb-local-folder")
    monkeypatch.setenv(env.CLIENT_SECRET_ENV, "shh")
    monkeypatch.delenv(env.TEMPORAL_HOST_ENV, raising=False)

    resolved = env.PodEnvironment.from_env(require_temporal=False)
    assert resolved.control_plane_url == "http://example.invalid/x"

    with pytest.raises(env.MissingPodEnvironment, match=env.TEMPORAL_HOST_ENV):
        env.PodEnvironment.from_env(require_temporal=True)


def test_missing_pod_environment_names_everything_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_sdk.knowledge_base import environment as env

    for name in (
        env.CONTROL_PLANE_URL_ENV,
        env.KEYCLOAK_REALM_URL_ENV,
        env.CLIENT_ID_ENV,
        env.CLIENT_SECRET_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(env.MissingPodEnvironment) as raised:
        env.PodEnvironment.from_env(require_temporal=False)
    for name in (env.CONTROL_PLANE_URL_ENV, env.CLIENT_ID_ENV):
        assert name in str(raised.value)


def test_a_local_stack_needs_neither_keycloak_nor_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors `security.user.enabled: false`: no secret, no token, no Keycloak."""
    from fred_sdk.knowledge_base import environment as env

    monkeypatch.setenv(
        env.CONTROL_PLANE_URL_ENV, "http://localhost:8222/control-plane/v1"
    )
    monkeypatch.setenv(env.PREFIX_ENV, "acme.kb")
    monkeypatch.setenv(env.CLIENT_ID_ENV, "kb-local-folder")
    for name in (env.CLIENT_SECRET_ENV, env.KEYCLOAK_REALM_URL_ENV):
        monkeypatch.delenv(name, raising=False)

    resolved = env.PodEnvironment.from_env(require_temporal=False)
    assert resolved.authenticated is False


def test_a_client_secret_makes_keycloak_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_sdk.knowledge_base import environment as env

    monkeypatch.setenv(env.CONTROL_PLANE_URL_ENV, "http://example.invalid")
    monkeypatch.setenv(env.CLIENT_ID_ENV, "kb-local-folder")
    monkeypatch.setenv(env.CLIENT_SECRET_ENV, "shh")
    monkeypatch.delenv(env.KEYCLOAK_REALM_URL_ENV, raising=False)

    with pytest.raises(env.MissingPodEnvironment, match=env.KEYCLOAK_REALM_URL_ENV):
        env.PodEnvironment.from_env(require_temporal=False)
