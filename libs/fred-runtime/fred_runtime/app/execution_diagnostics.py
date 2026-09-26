# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Safe support diagnostics: code locations only, never exception values or locals."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fred_runtime.execution_errors import UserFacingExecutionError


def report_execution_error(logger: logging.Logger, exc: Exception, phase: str) -> str:
    reference = uuid4().hex
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
    logger.error(
        "event=execution_error outcome=failed error_ref=%s phase=%s diagnostics=%s",
        reference,
        phase,
        " | ".join(diagnostics),
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
        f"Contact support with reference {reference}."
    )
