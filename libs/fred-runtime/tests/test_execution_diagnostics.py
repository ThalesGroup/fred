# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
import logging
import uuid

from fred_runtime.app.execution_diagnostics import report_execution_error
from fred_runtime.execution_errors import UserFacingExecutionError, sanitize_identifier


class _Named(UserFacingExecutionError):
    def __init__(self, name: str, internal_message: str | None = None) -> None:
        super().__init__(f"The thing '{name}' is missing.", internal_message)


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
