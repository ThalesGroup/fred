# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
import logging
import uuid

import httpx
import pytest
from fred_sdk import GraphAgent, GraphWorkflow, StepResult, typed_node
from fred_sdk.contracts.context import (
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    NodeErrorRuntimeEvent,
    RuntimeServices,
)
from fred_sdk.graph.runtime import GraphNodeContext
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from weaver_fixtures import local_binding

from fred_runtime.app.agent_app import HitlResumeAlreadyClaimedError
from fred_runtime.execution_diagnostics import report_execution_error
from fred_runtime.capabilities.errors import UnknownCapabilityError
from fred_runtime.common.managed_mcp import ManagedMcpError
from fred_runtime.execution_errors import UserFacingExecutionError, sanitize_identifier
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.model_routing.contracts import ModelRoutingError
from fred_runtime.model_routing.provider import _TEMPERATURE_REFUSED
from fred_runtime.runtime_support.active_turn import ActiveTurnLost
from fred_runtime.runtime_support.llm_diagnostics import attach_failure


class _Named(UserFacingExecutionError):
    def __init__(self, name: str, internal_message: str | None = None) -> None:
        super().__init__(
            {"en": "The thing '{name}' is missing.", "fr": "L'objet '{name}' manque."},
            internal_message,
            name=name,
        )


def _reference(message: str) -> str:
    return message.split("reference ")[1].rstrip(".")


def test_support_reference_and_safe_chained_trace(caplog):
    canary = f"private-person-url-{uuid.uuid4().hex}"
    try:
        try:
            raise ValueError(canary)
        except ValueError as cause:
            raise RuntimeError(canary) from cause
    except RuntimeError as exc:
        message = report_execution_error(logging.getLogger(__name__), exc, "execution")
    reference = _reference(message)
    assert len(reference) == 32
    assert reference in caplog.text
    assert "RuntimeError" in caplog.text
    assert "ValueError" in caplog.text
    assert "test_support_reference_and_safe_chained_trace" in caplog.text
    assert canary not in repr([r.__dict__ for r in caplog.records])
    assert canary not in message
    assert all(r.exc_info is None for r in caplog.records)


def test_exception_group_includes_child_types_without_messages(caplog):
    exc = ExceptionGroup("private-group", [ValueError("private-child")])
    message = report_execution_error(
        logging.getLogger(__name__), exc, "capability_setup"
    )
    assert "prepare its capabilities" in message
    assert "ExceptionGroup" in caplog.text
    assert "ValueError" in caplog.text
    assert "private-group" not in caplog.text
    assert "private-child" not in caplog.text


def test_a_specific_sentence_still_carries_the_support_reference(caplog):
    """A sentence tells the user what broke; it does not exempt the turn from a log line."""

    internal = f"private-inventory-{uuid.uuid4().hex}"
    message = report_execution_error(
        logging.getLogger(__name__), _Named("ghost", internal), "capability_setup"
    )
    assert message.startswith("The thing 'ghost' is missing. ")
    assert len(_reference(message)) == 32
    assert _reference(message) in caplog.text
    assert "prepare its capabilities" not in message
    # The raising site's internal text reaches neither the user nor the log.
    assert internal not in message
    assert internal not in caplog.text
    assert "_Named" in caplog.text


def test_no_exception_text_is_logged_even_for_an_owned_error(caplog):
    secret = f"private-token-{uuid.uuid4().hex}"
    try:
        raise _Named("thing", secret)
    except _Named as exc:
        report_execution_error(logging.getLogger(__name__), exc, "execution")
    assert secret not in caplog.text
    assert "_Named" in caplog.text
    assert "test_no_exception_text_is_logged_even_for_an_owned_error" in caplog.text


def test_the_outer_error_wins_over_its_cause():
    try:
        try:
            raise _Named("inner")
        except _Named as cause:
            raise _Named("outer") from cause
    except _Named as exc:
        message = report_execution_error(logging.getLogger(__name__), exc, "execution")
    assert message.startswith("The thing 'outer' is missing.")


def test_an_explicit_cause_wins_over_a_group_child():
    try:
        try:
            raise _Named("cause")
        except _Named as cause:
            raise ExceptionGroup("g", [_Named("child")]) from cause
    except ExceptionGroup as exc:
        message = report_execution_error(logging.getLogger(__name__), exc, "execution")
    assert message.startswith("The thing 'cause' is missing.")


def test_group_children_are_read_in_declared_order():
    exc = ExceptionGroup("g", [_Named("first"), _Named("second")])
    message = report_execution_error(
        logging.getLogger(__name__), exc, "capability_setup"
    )
    assert message.startswith("The thing 'first' is missing.")


def test_a_suppressed_context_is_not_read():
    """`raise ... from None` detaches the context; it must not pick the sentence."""

    try:
        try:
            raise _Named("detached")
        except _Named:
            raise RuntimeError("wrapper") from None
    except RuntimeError as exc:
        message = report_execution_error(logging.getLogger(__name__), exc, "execution")
    assert "detached" not in message
    assert "internal error while processing" in message


def test_sanitize_identifier_bounds_an_untrusted_id():
    assert sanitize_identifier("plain.id-1") == "plain.id-1"
    assert sanitize_identifier("with\nnewline\x00and control") == (
        "with newline and control"
    )
    assert sanitize_identifier("   ") == "(unnamed)"
    assert sanitize_identifier("x" * 200) == "x" * 64 + "…"


def _failed_model_call(**fields) -> RuntimeError:
    """A turn error chaining a model call the tracing middleware classified."""

    cause = RuntimeError("private-upstream-body")
    attach_failure(
        cause,
        {"llm_call_id": "call-1", "model_name": "mistral-medium", **fields},
    )
    try:
        raise RuntimeError("private-wrapper") from cause
    except RuntimeError as exc:
        return exc


@pytest.mark.parametrize(
    ("fields", "language", "expected"),
    [
        (
            {"error_code": "provider_http_error", "http_status": 503},
            None,
            "The model provider is temporarily unavailable "
            "(model mistral-medium, HTTP 503). Please try again in a moment.",
        ),
        (
            {"error_code": "provider_http_error", "http_status": 503},
            "fr-FR",
            "Le fournisseur du modèle est momentanément indisponible "
            "(modèle mistral-medium, HTTP 503). Réessayez dans un instant.",
        ),
        (
            {"error_code": "rate_limited", "http_status": 429},
            "en",
            "The model provider is limiting the number of requests "
            "(model mistral-medium, HTTP 429). Please try again in a moment.",
        ),
        (
            {"error_code": "stream_idle_timeout", "model_name": "bad\nname"},
            "fr",
            "Le fournisseur du modèle n'a pas répondu à temps (modèle bad name). "
            "Réessayez.",
        ),
        (
            {"error_code": "connection_error"},
            "de",
            "The model provider could not be reached (model mistral-medium). "
            "Please try again in a moment.",
        ),
    ],
)
def test_a_provider_failure_names_the_condition_in_the_user_language(
    fields, language, expected, caplog
):
    exc = _failed_model_call(stage="before_first_chunk", **fields)
    message = report_execution_error(
        logging.getLogger(__name__), exc, "execution", language=language
    )
    assert message == expected
    # The log line keeps the reference support correlates; the user gets none.
    (record,) = [r for r in caplog.records if hasattr(r, "error_ref")]
    assert record.llm_failures[0]["error_code"] == fields["error_code"]
    assert "private-" not in message


def test_a_provider_rejection_support_must_trace_keeps_the_reference():
    exc = _failed_model_call(error_code="provider_http_error", http_status=401)
    message = report_execution_error(logging.getLogger(__name__), exc, "execution")
    assert message.startswith("The agent encountered an internal error")
    assert len(_reference(message)) == 32


def test_an_unattributed_http_503_is_not_a_model_provider_failure():
    """Only a model call's attached failure names the provider, not a tool's 503."""

    exc = httpx.HTTPStatusError(
        "private-tool-body",
        request=httpx.Request("GET", "http://tool.invalid"),
        response=httpx.Response(503),
    )
    message = report_execution_error(logging.getLogger(__name__), exc, "execution")
    assert "model provider" not in message
    assert len(_reference(message)) == 32


def test_the_generic_sentence_and_its_reference_are_localized(caplog):
    message = report_execution_error(
        logging.getLogger(__name__), ValueError("private"), "execution", language="fr"
    )
    sentence, _, reference = message.partition(
        " Contactez le support en indiquant la référence "
    )
    assert sentence == (
        "L'agent a rencontré une erreur interne en traitant votre demande."
    )
    assert len(reference.rstrip(".")) == 32
    assert reference.rstrip(".") in caplog.text


@pytest.mark.parametrize(
    ("error", "english", "french"),
    [
        (
            ModelRoutingError(_TEMPERATURE_REFUSED),
            "The model client does not accept the admitted temperature.",
            "Le client du modèle n'accepte pas la température admise.",
        ),
        (
            ManagedMcpError("mcp_binding_mismatch"),
            "MCP configuration was refused.",
            "La configuration MCP a été refusée.",
        ),
        (
            UnknownCapabilityError("private-inventory", capability_id="bad\nid"),
            "This agent needs the capability 'bad id', which is not installed "
            "on this pod.",
            "Cet agent a besoin de la capacité 'bad id', qui n'est pas installée "
            "sur ce pod.",
        ),
        (
            ActiveTurnLost(),
            "This response stopped because its conversation turn expired or was "
            "lost. Wait for any other response to finish, then send your message "
            "again.",
            "Cette réponse s'est arrêtée car son tour de conversation a expiré ou "
            "a été perdu. Attendez la fin de toute autre réponse, puis renvoyez "
            "votre message.",
        ),
        (
            HitlResumeAlreadyClaimedError("private-claim"),
            "This HITL request is already being resumed.",
            "Cette demande est déjà en cours de reprise.",
        ),
    ],
)
def test_a_specific_sentence_follows_the_user_language(error, english, french):
    assert error.user_message(None) == english
    assert error.user_message("en-GB") == english
    assert error.user_message("fr-FR") == french
    message = report_execution_error(
        logging.getLogger(__name__), error, "execution", language="fr"
    )
    assert message.startswith(
        f"{french} Contactez le support en indiquant la référence "
    )


class _NodeInput(BaseModel):
    message: str


class _NodeState(BaseModel):
    latest_user_text: str
    node_error: str = ""
    final_text: str | None = None


@typed_node(_NodeState)
async def _raises(state: _NodeState, context: GraphNodeContext) -> StepResult:
    raise RuntimeError("private-upstream-dump https://provider.invalid/v1?key=x")


@typed_node(_NodeState)
async def _recovers(state: _NodeState, context: GraphNodeContext) -> StepResult:
    return StepResult(state_update={"final_text": "recovered"})


class _FailingGraph(GraphAgent):
    agent_id: str = "fred.tests.graph.node_error"
    role: str = "Failure probe"
    description: str = "A node raises and routes to its fallback."
    input_schema = _NodeInput
    state_schema = _NodeState
    input_to_state = {"message": "latest_user_text"}
    workflow = GraphWorkflow(
        entry="call",
        nodes={"call": _raises, "fallback": _recovers},
        error_routes={"call": "fallback"},
    )


@pytest.mark.asyncio
async def test_a_routed_node_error_carries_the_user_sentence_not_the_exception():
    binding = local_binding(
        "fred.tests.graph.node_error",
        runtime_context=RuntimeContext(session_id="s", user_id="u", language="fr"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
        ),
    )
    runtime = GraphRuntime(
        definition=_FailingGraph(),
        services=RuntimeServices(checkpointer=InMemorySaver()),
    )
    runtime.bind(binding)
    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _NodeInput(message="go"), ExecutionConfig(session_id="s")
        )
    ]
    (error,) = [e for e in events if isinstance(e, NodeErrorRuntimeEvent)]
    assert error.routed_to == "fallback"
    assert error.error_message.startswith(
        "L'agent a rencontré une erreur interne en traitant votre demande. "
        "Contactez le support en indiquant la référence "
    )
    assert "private-upstream-dump" not in error.error_message
