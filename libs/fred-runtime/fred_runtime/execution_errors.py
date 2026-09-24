# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""The narrow opt-out from support-reference redaction, for pod-internal use."""

from __future__ import annotations


def sanitize_identifier(value: str, limit: int = 64) -> str:
    """Bound an untrusted id before it lands in a sentence a user reads."""

    printable = "".join(c if c.isprintable() else " " for c in str(value))
    collapsed = " ".join(printable.split())
    if not collapsed:
        return "(unnamed)"
    return collapsed[:limit] + "…" if len(collapsed) > limit else collapsed


class UserFacingExecutionError(RuntimeError):
    """An execution error carrying a sentence the user is meant to read.

    An execution error is otherwise redacted to a support reference, because a
    stringified exception may carry a token, an upstream body or a URL. A
    subclass builds `user_message` itself, from a fixed sentence or from an
    id put through `sanitize_identifier`; the exception's own text stays
    internal, and is neither surfaced nor logged.
    """

    def __init__(self, user_message: str, internal_message: str | None = None) -> None:
        super().__init__(internal_message or user_message)
        self.user_message = user_message
