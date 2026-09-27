# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


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
        library_id="lib-1",
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
# 1.6 the execution boundary a pod's startup depends on
# --------------------------------------------------------------------------


def test_the_workflow_validates_under_the_sandbox_serve_actually_uses() -> None:
    """The check every pod runs at startup, run here where it is cheap.

    Worker construction validates the workflow against the sandbox, so a broken
    sandbox configuration takes `serve()` down for every Knowledge Base at once
    and the only symptom is a pod dying one log line in. The runner comes from
    `serve()`'s own builder, so narrowing the real passthrough cannot leave this
    passing, and `_Definition` is Temporal's own internal accessor so this runs
    against the real sandbox. What it does not cover — the contents of
    `_workflow.py`, which the passthrough hides — is the test below.
    """
    from fred_sdk.knowledge_base._workflow import SynchronizeWorkflow
    from fred_sdk.knowledge_base.worker import build_workflow_runner
    from temporalio.workflow import _Definition

    async def validate() -> None:
        # Temporal reads the running loop while preparing, exactly as it does
        # inside `serve()`.
        build_workflow_runner().prepare_workflow(
            _Definition.must_from_class(SynchronizeWorkflow)
        )

    asyncio.run(validate())


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled"])
def test_a_reported_failure_does_not_leave_a_completed_workflow(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    """A handler's own verdict has to reach the engine's terminal state.

    The engine's history is where a run's fate is read, so a handler reporting
    `failed` while the workflow closes as Completed makes every run look fine.
    Business cancellation is a failure too, under its own type: nothing here
    asked the engine to cancel, so it must not be reported as if it had.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fred_sdk.knowledge_base import _workflow
    from temporalio.exceptions import ApplicationError

    # `_workflow` spells these out rather than importing the enum, so tie the
    # two together here; the vocabulary itself is pinned a few tests above.
    assert outcome in {o.value for o in KnowledgeBaseRunOutcome}

    monkeypatch.setattr(
        _workflow.workflow, "execute_activity", AsyncMock(return_value=outcome)
    )
    monkeypatch.setattr(
        _workflow.workflow, "info", lambda: SimpleNamespace(run_id="run")
    )
    run = _workflow.SynchronizeWorkflow().run(
        _workflow.SynchronizeInput("fred.samples.local-folder", "instance", "team")
    )

    if outcome == "succeeded":
        assert asyncio.run(run) == "succeeded"
        return

    with pytest.raises(ApplicationError) as raised:
        asyncio.run(run)
    assert raised.value.non_retryable
    assert raised.value.type == (
        "KnowledgeBaseSyncFailed"
        if outcome == "failed"
        else "KnowledgeBaseSyncCancelled"
    )


def test_the_workflow_module_imports_only_what_the_sandbox_would_allow() -> None:
    """Reads by hand what the sandbox is configured not to check.

    `build_workflow_runner` passes all of `fred_sdk` through, so an import added
    to `_workflow.py` reaches a deployed pod unchecked — `httpx`, and through it
    `sniffio`, is exactly what broke worker startup once. Imports are the failure
    mode that actually occurred; a non-deterministic *call* on an allowed module
    stays out of reach of any check short of sandboxing the module itself, which
    Temporal's prefix-only passthrough cannot express.
    """
    import ast
    from pathlib import Path

    from fred_sdk.knowledge_base import _workflow

    allowed = {"__future__", "dataclasses", "datetime", "temporalio"}
    tree = ast.parse(Path(_workflow.__file__).read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    assert imported <= allowed, (
        f"_workflow.py may not import {sorted(imported - allowed)}: the sandbox "
        "passes fred_sdk through, so nothing else will catch it"
    )


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
        definition_id="acme.kb.http-markdown",
        instance_id="i",
        team_id="t",
        run_id="r",
        library_id="l",
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
    from fred_pod.common.naming import knowledge_base_catalog_id
    from fred_sdk.knowledge_base.routing import task_queue_for

    assert task_queue_for("acme.kb.local-folder") == knowledge_base_catalog_id(
        "acme.kb.local-folder"
    )


def test_task_queue_refuses_an_empty_name() -> None:
    from fred_sdk.knowledge_base.routing import task_queue_for

    with pytest.raises(ValueError):
        task_queue_for("")


# 2c.5 the pod environment contract


def _valid_configuration() -> dict:
    """The smallest configuration a pod can start from, in Fred's own keys."""
    return {
        "knowledge_base": {
            "prefix": "acme.kb",
            "control_plane_url": "http://example.invalid/control-plane/v1/",
        },
        "security": {
            "m2m": {
                "realm_url": "http://keycloak.invalid/realms/app",
                "client_id": "kb-local-folder",
                "secret_env_var": "ACME_KB_CLIENT_SECRET",  # pragma: allowlist secret
            }
        },
    }


def test_a_pod_is_configured_the_way_every_fred_component_is() -> None:
    """Same keys, same models — `security.m2m` and `scheduler.temporal`.

    The point of this test is not that the values arrive, but that they arrive
    under the paths an operator already knows from every other Fred backend,
    parsed by the models fred-core owns rather than by a second set.
    """
    from fred_pod.common import TemporalSchedulerConfig
    from fred_pod.security.structure import M2MSecurity
    from fred_sdk.knowledge_base.configuration import PodConfiguration

    configuration = PodConfiguration.model_validate(_valid_configuration())

    assert isinstance(configuration.security.m2m, M2MSecurity)
    assert isinstance(configuration.scheduler.temporal, TemporalSchedulerConfig)
    # Read from a browser's address bar with its trailing slash, used without.
    assert configuration.control_plane_url == "http://example.invalid/control-plane/v1"


def test_publish_needs_no_workflow_engine_in_its_configuration() -> None:
    """A publish Job must not depend on a worker it never starts.

    So a configuration that says nothing about Temporal is valid, and only a
    pod that actually serves runs ever reaches it.
    """
    from fred_sdk.knowledge_base.configuration import PodConfiguration

    configuration = PodConfiguration.model_validate(_valid_configuration())

    assert "scheduler" not in _valid_configuration()
    assert configuration.temporal_host
    assert configuration.temporal_namespace


def test_a_configuration_without_credentials_is_refused_at_startup() -> None:
    """A Knowledge Base acts as a workload, and Fred admits it as nothing else.

    So missing credentials are a startup error naming what is absent, not a pod
    that runs and is refused at its first document.
    """
    from fred_sdk.knowledge_base.configuration import PodConfiguration
    from pydantic import ValidationError

    without_security = _valid_configuration()
    del without_security["security"]

    with pytest.raises(ValidationError, match="security"):
        PodConfiguration.model_validate(without_security)


@pytest.mark.parametrize("absent", ["realm_url", "client_id"])
def test_a_configuration_missing_one_credential_names_it(absent: str) -> None:
    from fred_sdk.knowledge_base.configuration import PodConfiguration
    from pydantic import ValidationError

    payload = _valid_configuration()
    del payload["security"]["m2m"][absent]

    with pytest.raises(ValidationError, match=absent):
        PodConfiguration.model_validate(payload)


def test_the_secret_is_named_by_the_configuration_never_carried_in_it() -> None:
    """Which variable holds it is configuration; the value never is.

    The hard-coded variable name this replaces made two pods in one namespace
    unable to read two different secrets.
    """
    from fred_sdk.knowledge_base.configuration import PodConfiguration

    configured = _valid_configuration()
    configuration = PodConfiguration.model_validate(configured)

    assert (
        configuration.m2m.secret_env == configured["security"]["m2m"]["secret_env_var"]
    )
    assert "secret" not in configuration.model_dump_json().replace("secret_env_var", "")


def test_a_missing_configuration_file_is_its_own_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent is catchable; present-and-wrong stops the process.

    A developer tool running with no Fred at all is a legitimate state, so the
    absence of a file is an exception a caller may handle.
    """
    from fred_sdk.knowledge_base.configuration import (
        MissingPodConfiguration,
        PodConfiguration,
    )

    monkeypatch.setenv("CONFIG_FILE", "/nowhere/configuration.yaml")

    with pytest.raises(MissingPodConfiguration, match="CONFIG_FILE"):
        PodConfiguration.load()


def test_the_queue_is_derived_and_a_configured_one_is_not_read() -> None:
    """Both sides derive it, so neither can be configured out of agreement."""
    from fred_sdk.knowledge_base.configuration import PodConfiguration
    from fred_sdk.knowledge_base.routing import task_queue_for

    payload = _valid_configuration()
    payload["scheduler"] = {"temporal": {"task_queue": "somebody-elses-queue"}}
    configuration = PodConfiguration.model_validate(payload)

    assert task_queue_for("acme.kb.local-folder") != (
        configuration.scheduler.temporal.task_queue
    )


# --------------------------------------------------------------------------
# 3.7 the namespace Fred keeps for itself
# --------------------------------------------------------------------------


def test_an_author_declares_only_their_own_fields() -> None:
    """Recurrence is Fred's to own, so it is not an author's to declare.

    It is typed on Fred's own instance schemas rather than declared here as a
    field somebody has to render generically and then fish back out by key.
    """
    kb = KnowledgeBase(
        id="acme.kb.bare",
        version="1.0.0",
        name="Bare",
        description="Declares no field of its own",
    )

    assert kb.configuration_fields == []


def test_the_reserved_namespace_is_recognised_whole() -> None:
    from fred_sdk.knowledge_base.schedule import is_platform_field

    assert is_platform_field("fred")
    assert is_platform_field("fred.anything")
    assert not is_platform_field("fredonia")
    assert not is_platform_field("url")


@pytest.mark.parametrize(
    "key", ["fred.cadence", "fred.suspended", "fred.anything", "fred"]
)
def test_an_author_cannot_declare_a_field_that_collides_with_it(key: str) -> None:
    with pytest.raises(KnowledgeBaseDeclarationError) as raised:
        KnowledgeBase(
            id="acme.kb.greedy",
            version="1.0.0",
            name="Greedy",
            description="Tries to own a key Fred acts on",
            configuration_fields=[FieldSpec(key=key, type="string", title="Mine")],
        )

    assert key in str(raised.value)


def test_a_key_merely_starting_with_the_namespace_is_still_the_author_s() -> None:
    """`fred` is a segment, not a prefix match: `fredsource` belongs to nobody else."""
    kb = KnowledgeBase(
        id="acme.kb.fine",
        version="1.0.0",
        name="Fine",
        description="Declares a key that only looks reserved",
        configuration_fields=[FieldSpec(key="fredsource", type="string", title="Mine")],
    )

    assert [field.key for field in kb.configuration_fields] == ["fredsource"]


def test_the_platform_zone_stays_out_of_the_author_facing_exports() -> None:
    """It is Fred's vocabulary, and task 1.5's surface assertion depends on it."""
    assert "platform_fields" not in kb_module.__all__
    assert not any("cadence" in name.lower() for name in kb_module.__all__)
