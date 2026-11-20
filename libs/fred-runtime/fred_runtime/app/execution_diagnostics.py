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
from fred_runtime.execution_errors import UserFacingExecutionError
from fred_runtime.react.middleware.rate_limit_retry import ProviderRateLimitError
from fred_runtime.runtime_support.llm_diagnostics import (
    classify_error,
    exception_chain,
    failed_calls,
    invocation_failure_reason,
    observed_failure_reason,
)
from fred_runtime.runtime_support.tool_execution import TOOL_FAILURE_MARKER


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


def report_execution_error(
    logger: logging.Logger, exc: Exception, phase: str, *, reference: str | None = None
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
            surfaced = current.user_message
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
    descriptions = {
        "capability_setup": "The agent could not prepare its capabilities.",
        "runtime_setup": "The agent could not initialize its execution.",
        "execution": "The agent encountered an internal error while processing your request.",
    }
    # The reference is on both paths: a specific sentence tells the user what
    # went wrong, it does not exempt the turn from being traceable to a log.
    return (
        f"{surfaced or descriptions.get(phase, descriptions['execution'])} "
        f"Reference: {reference}"
    )
