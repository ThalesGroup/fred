# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for details.

"""Bounded diagnostic envelope for explicitly admitted first-party delegation."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Mapping

from fred_core.logs.context import (
    MAX_FIELDS,
    RESERVED_FIELDS,
    LogContext,
    bind_operation_context,
    current_context,
    safe_context,
)

CONTEXT_HEADER = "X-Fred-Log-Context"
CONTEXT_VERSION = 1
MAX_HEADER_BYTES = 8192
MAX_ENVELOPE_BYTES = 4096
RECEIVER_FIELDS = RESERVED_FIELDS | {"request_id"}
logger = logging.getLogger(__name__)


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata key")
        result[key] = value
    return result


def encode_log_context(values: Mapping[str, object]) -> str | None:
    """Encode safe bindings, excluding receiver-owned fields; never credentials/extra."""
    try:
        if len(values) > MAX_FIELDS:
            return None
        context = safe_context(
            {key: value for key, value in values.items() if key not in RECEIVER_FIELDS}
        )
        payload = json.dumps(
            {"v": CONTEXT_VERSION, "context": context},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_ENVELOPE_BYTES:
            return None
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    except (ValueError, UnicodeError):
        return None


def decode_log_context(header: str) -> tuple[LogContext | None, str | None]:
    """Return a bounded reason on rejection, never echoing the envelope."""
    if len(header) > MAX_HEADER_BYTES:
        return None, "oversized"
    if (
        not header
        or not header.isascii()
        or any(not (char.isalnum() or char in "-_") for char in header)
    ):
        return None, "malformed"
    try:
        payload = base64.b64decode(
            header + "=" * (-len(header) % 4), altchars=b"-_", validate=True
        )
        if len(payload) > MAX_ENVELOPE_BYTES:
            return None, "oversized"
        envelope = json.loads(
            payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        if (
            not isinstance(envelope, dict)
            or type(envelope.get("v")) is not int
            or envelope["v"] != CONTEXT_VERSION
        ):
            return None, "unsupported_version"
        values = envelope.get("context")
        if not isinstance(values, dict):
            return None, "invalid_context"
        if len(values) > MAX_FIELDS:
            return None, "invalid_context"
        return safe_context(
            {key: value for key, value in values.items() if key not in RECEIVER_FIELDS}
        ), None
    except (ValueError, UnicodeError, binascii.Error, RecursionError):
        return None, "invalid_context"


def outbound_context_headers() -> dict[str, str]:
    """Call only from a delegated first-party seam; attach to this invocation."""
    encoded = encode_log_context(current_context())
    if encoded is None:
        logger.warning(
            "Outgoing logging metadata dropped", extra={"reason": "invalid_context"}
        )
    return {CONTEXT_HEADER: encoded} if encoded is not None else {}


def admit_delegated_log_context(
    header: str | None, *, user_id: str, run_id: str, agent_id: str
) -> None:
    """Apply only after principal/grant admission; grant identity always wins."""
    if header is not None:
        values, reason = decode_log_context(header)
        if values is not None:
            bind_operation_context(values)
        else:
            logger.warning(
                "Delegated logging metadata dropped", extra={"reason": reason}
            )
    bind_operation_context(user_id=user_id, run_id=run_id, agent_id=agent_id)
