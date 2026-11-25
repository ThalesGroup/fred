# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Safe support diagnostics: code locations only, never exception values or locals."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fred_core.history.history_schema import TraceFailureCategory
from fred_sdk.authoring.api import ToolInvocationError
from langchain_core.tools import ToolException

from fred_runtime.capabilities.errors import CapabilityError
from fred_runtime.execution_errors import (
    UserFacingExecutionError,
    localize,
    sanitize_identifier,
)
from fred_runtime.react.middleware.rate_limit_retry import ProviderRateLimitError
from fred_runtime.runtime_support.llm_diagnostics import (
    Scalar,
    classify_error,
    exception_chain,
    failed_calls,
    invocation_failure_reason,
    observed_failure_reason,
)
from fred_runtime.runtime_support.tool_execution import TOOL_FAILURE_MARKER

_PHASES = {
    "capability_setup": {
        "en": "The agent could not prepare its capabilities.",
        "fr": "L'agent n'a pas pu préparer ses capacités.",
    },
    "runtime_setup": {
        "en": "The agent could not initialize its execution.",
        "fr": "L'agent n'a pas pu initialiser son exécution.",
    },
    "execution": {
        "en": "The agent encountered an internal error while processing your request.",
        "fr": "L'agent a rencontré une erreur interne en traitant votre demande.",
    },
}
_REFERENCE = {
    "en": "Contact support with reference {reference}.",
    "fr": "Contactez le support en indiquant la référence {reference}.",
}
_MODEL = {"en": "model {model}", "fr": "modèle {model}"}
_UNAVAILABLE = {
    "en": "The model provider is temporarily unavailable{detail}. Please try again in a moment.",
    "fr": "Le fournisseur du modèle est momentanément indisponible{detail}. Réessayez dans un instant.",
}
_TIMEOUT = {
    "en": "The model provider did not answer in time{detail}. Please try again.",
    "fr": "Le fournisseur du modèle n'a pas répondu à temps{detail}. Réessayez.",
}
# Provider conditions a retry can fix, keyed by the `error_code` that
# `classify_error` attached to the failed model call; a 5xx is `_UNAVAILABLE`.
_PROVIDER = {
    "rate_limited": {
        "en": "The model provider is limiting the number of requests{detail}. Please try again in a moment.",
        "fr": "Le fournisseur du modèle limite le nombre de requêtes{detail}. Réessayez dans un instant.",
    },
    "connection_error": {
        "en": "The model provider could not be reached{detail}. Please try again in a moment.",
        "fr": "Le fournisseur du modèle est injoignable{detail}. Réessayez dans un instant.",
    },
    "remote_protocol_error": _UNAVAILABLE,
    **dict.fromkeys(
        (
            "stream_idle_timeout",
            "connect_timeout",
            "read_timeout",
            "write_timeout",
            "pool_timeout",
        ),
        _TIMEOUT,
    ),
}


def _provider_sentence(
    calls: list[dict[str, Scalar]], language: str | None
) -> str | None:
    """Name a model-call failure a retry can fix; upstream text never enters."""

    for call in calls:
        raw_status = call.get("http_status")
        status = raw_status if isinstance(raw_status, int) else None
        sentences = (
            _UNAVAILABLE
            if call.get("error_code") == "provider_http_error"
            and status is not None
            and status >= 500
            else _PROVIDER.get(str(call.get("error_code")))
        )
        if sentences is None:
            continue
        details = []
        if model := call.get("model_name"):
            model_name = sanitize_identifier(str(model))
            details.append(localize(_MODEL, language).format(model=model_name))
        if status is not None:
            details.append(f"HTTP {status}")
        detail = f" ({', '.join(details)})" if details else ""
        return localize(sentences, language).format(detail=detail)
    return None


def report_execution_error(
    logger: logging.Logger,
    exc: Exception,
    phase: str,
    *,
    language: str | None = None,
    reference: str | None = None,
) -> str:
    reference = reference or uuid4().hex
    # Walk causes without formatting exceptions: HTTP errors may embed tokens,
    # delegated identities, request bodies or URLs in their messages. The same
    # walk picks the sentence to surface, so both honour one traversal order:
    # the outer error, then its explicit cause, then a group's children in the
    # order they were declared — and never a deliberately suppressed context.
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    diagnostics: list[str] = []
    surfaced: str | None = None
    while pending and len(seen) < 16:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        if surfaced is None and isinstance(current, UserFacingExecutionError):
            surfaced = current.user_message(language)
        frames: list[str] = []
        tb = current.__traceback__
        while tb is not None:
            code = tb.tb_frame.f_code
            frames.append(
                f"{Path(code.co_filename).name}:{tb.tb_lineno}:{code.co_name}"
            )
            tb = tb.tb_next
        diagnostics.append(f"{type(current).__name__}: " + " -> ".join(frames[-32:]))
        cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        if cause is not None:
            pending.append(cause)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions[:8])
    calls, calls_truncated = failed_calls(exc)
    logger.error(
        "event=execution_error outcome=failed error_ref=%s phase=%s diagnostics=%s llm_failures=%s truncated=%s",
        reference,
        phase,
        " | ".join(diagnostics),
        calls,
        calls_truncated,
        extra={
            "error_ref": reference,
            "llm_failures": calls,
            "llm_failures_truncated": calls_truncated,
        },
    )
    # A provider condition is the user's to retry, not support's to trace, so
    # its sentence goes without the reference the log line still carries. A
    # specific sentence keeps it: it says what broke, the log says why.
    if surfaced is None and (sentence := _provider_sentence(calls, language)):
        return sentence
    description = surfaced or localize(
        _PHASES.get(phase, _PHASES["execution"]), language
    )
    return f"{description} {localize(_REFERENCE, language).format(reference=reference)}"


def classify_terminal_failure(exc: Exception, phase: str) -> TraceFailureCategory:
    """Classify the exception that ended the turn using its attached evidence."""
    observed = observed_failure_reason(exc)
    if observed is not None:
        return observed

    chain, _ = exception_chain(exc)
    if any(isinstance(error, ProviderRateLimitError) for error in chain):
        return TraceFailureCategory.HTTP_429
    if phase == "capability_setup" or any(
        isinstance(error, (CapabilityError, ToolException, ToolInvocationError))
        or getattr(error, TOOL_FAILURE_MARKER, False) is True
        for error in chain
    ):
        return TraceFailureCategory.TOOL_OR_CAPABILITY
    return invocation_failure_reason(classify_error(exc))
