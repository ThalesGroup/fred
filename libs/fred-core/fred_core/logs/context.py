# Copyright Thales 2025
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
#

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from itertools import islice
from typing import TypeAlias

from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
    reset_contextvars,
)

LogValue: TypeAlias = (
    str | int | float | bool | None | list["LogValue"] | dict[str, "LogValue"]
)
LogContext: TypeAlias = dict[str, LogValue]


@dataclass
class RequestLogScope:
    """Request-owned snapshot; replace values explicitly, never mutate a shared bag."""

    values: LogContext
    closed: bool = False


_request_scope: ContextVar[RequestLogScope | None] = ContextVar(
    "fred_log_request", default=None
)
_operation_lifetimes: ContextVar[tuple[RequestLogScope, ...]] = ContextVar(
    "fred_log_operations", default=()
)
_completion_binding: ContextVar[bool] = ContextVar(
    "fred_log_completion_binding", default=True
)


@contextmanager
def completion_log_scope(values: Mapping[str, object]) -> Iterator[None]:
    """Emit the owned request snapshot after streaming run scopes have retired."""
    token = _operation_lifetimes.set(())
    try:
        with log_context(values):
            yield
    finally:
        _operation_lifetimes.reset(token)


@contextmanager
def operation_log_scope(
    *, clear: tuple[str, ...] = (), completion: bool | None = None, **values: object
) -> Iterator[None]:
    """Retire inherited run metadata in tasks retained beyond the run's lifetime."""
    lifetime = RequestLogScope({})
    token = _operation_lifetimes.set((*_operation_lifetimes.get(), lifetime))
    completion_token = _completion_binding.set(
        _completion_binding.get() if completion is None else completion
    )
    try:
        with log_context(values, clear=clear):
            yield
    finally:
        lifetime.closed = True
        try:
            _operation_lifetimes.reset(token)
            _completion_binding.reset(completion_token)
        except ValueError:
            # Streaming teardown can run in its dedicated cleanup task. The
            # shared lifetime still retires the producer's inherited metadata.
            pass


def bind_operation_context(*, clear: tuple[str, ...] = (), **values: object) -> None:
    """Retain resolved request IDs for completion; diagnostic limits fail open.

    Call after business admission/resolution, e.g. ``bind_operation_context(session_id=id)``.
    Use ``log_context(tool_name=name)`` for temporary fields that should restore on exit.
    Neither helper is an authorization source.
    """
    validated: LogContext = {}
    for key, value in islice(values.items(), MAX_FIELDS):
        try:
            candidate = safe_context({**validated, key: value})
        except ValueError:
            continue
        validated = candidate
    owner = _request_scope.get()
    try:
        local = safe_context({**current_context(), **dict.fromkeys(clear), **validated})
        completion = safe_context(
            {
                **{
                    key: value
                    for key, value in (
                        owner.values if owner is not None else {}
                    ).items()
                    if key not in clear
                },
                **validated,
            }
        )
    except ValueError:
        return
    bind_contextvars(**local)
    if owner is not None and not owner.closed and _completion_binding.get():
        owner.values = completion


@contextmanager
def request_log_scope(**values: object) -> Iterator[RequestLogScope]:
    """Start an isolated scope and retire it even when a retained task outlives it."""
    previous = get_contextvars()
    clear_contextvars()
    owner = RequestLogScope(safe_context(values))
    token = _request_scope.set(owner)
    operation_token = _operation_lifetimes.set(())
    completion_token = _completion_binding.set(True)
    bind_contextvars(**owner.values)
    try:
        yield owner
    finally:
        owner.closed = True
        clear_contextvars()
        bind_contextvars(**previous)
        _request_scope.reset(token)
        _operation_lifetimes.reset(operation_token)
        _completion_binding.reset(completion_token)


# Event and receiver metadata cannot be supplied by business context.
RESERVED_FIELDS = frozenset(
    {
        "severity",
        "message",
        "timestamp",
        "logger",
        "service",
        "service_role",
        "category",
        "file",
        "line",
        "process",
        "thread",
        "task_name",
        "host",
        "logging.googleapis.com/sourceLocation",
        "httpRequest",
        "trace_id",
        "span_id",
        "ts",
        "level",
        "msg",
        "exception",
        "stack",
        "event",
    }
)
SENSITIVE_FIELDS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "cookie",
        "password",
        "secret",
        "email",
        "user",
        "prompt",
        "completion",
        "content",
        "body",
        "arguments",
        "result",
        "url",
        "signed_url",
    }
)
MAX_FIELDS = 32
MAX_VALUE_BYTES = 1024
MAX_DEPTH = 3


@dataclass
class ValueBudget:
    bytes_left: int = 4096
    nodes_left: int = 128

    def consume(self, size: int) -> None:
        """Bound aggregate validation work as well as serialized metadata size."""
        self.bytes_left -= size
        self.nodes_left -= 1
        if self.bytes_left < 0 or self.nodes_left < 0:
            raise ValueError("logging metadata budget exceeded")


def safe_value(
    value: object, depth: int = 0, *, budget: ValueBudget | None = None
) -> LogValue:
    """Copy bounded JSON values, sharing one budget across nested collections."""
    budget = budget if budget is not None else ValueBudget()
    budget.consume(8)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and -(2**63) <= value < 2**63:
        budget.consume(20)
        return value
    if isinstance(value, float) and math.isfinite(value):
        budget.consume(24)
        return value
    if isinstance(value, str) and len(value) <= MAX_VALUE_BYTES:
        encoded_size = len(value.encode("utf-8"))
        if encoded_size <= MAX_VALUE_BYTES:
            budget.consume(encoded_size)
            return value
    if depth < MAX_DEPTH:
        if isinstance(value, list) and len(value) <= MAX_FIELDS:
            return [safe_value(item, depth + 1, budget=budget) for item in value]
        if isinstance(value, dict) and len(value) <= MAX_FIELDS:
            result: LogContext = {}
            for key, item in value.items():
                name = safe_key(key)
                budget.consume(len(name))
                result[name] = safe_value(item, depth + 1, budget=budget)
            return result
    raise ValueError("unsupported logging value")


def safe_key(key: object) -> str:
    """Restrict metadata names; call at binding and incoming envelope boundaries."""
    if not isinstance(key, str) or not key or len(key) > 64 or not key.isascii():
        raise ValueError("invalid logging key")
    if not all(char.isalnum() or char in "_.-" for char in key):
        raise ValueError("invalid logging key")
    if key.lower() in SENSITIVE_FIELDS or key.startswith("_"):
        raise ValueError("sensitive logging key")
    return key


def safe_context(values: Mapping[str, object]) -> LogContext:
    """Validate a diagnostic bag without accepting core event fields."""
    if len(values) > MAX_FIELDS:
        raise ValueError("too many logging fields")
    budget = ValueBudget()
    result: LogContext = {}
    for key, value in values.items():
        if key in RESERVED_FIELDS:
            continue
        name = safe_key(key)
        budget.consume(len(name))
        result[name] = safe_value(value, budget=budget)
    return result


def current_context() -> LogContext:
    """Snapshot the producing task's validated context for delayed delivery."""
    owner = _request_scope.get()
    if (owner is not None and owner.closed) or any(
        scope.closed for scope in _operation_lifetimes.get()
    ):
        return {}
    context: LogContext = {}
    budget = ValueBudget()
    for key, value in get_contextvars().items():
        if key in RESERVED_FIELDS or len(context) >= MAX_FIELDS:
            continue
        try:
            context[safe_key(key)] = safe_value(value, budget=budget)
        except ValueError:
            continue
    return context


@contextmanager
def log_context(
    values: Mapping[str, object] | None = None,
    *,
    clear: tuple[str, ...] = (),
    **fields: object,
) -> Iterator[None]:
    """Bind nested metadata and restore it on all exits, including cancellation."""
    validated = safe_context({**(values or {}), **fields})
    tokens = bind_contextvars(**{**dict.fromkeys(clear), **validated})
    try:
        yield
    finally:
        try:
            reset_contextvars(**tokens)
        except ValueError:
            # A suspended generator may be closed by a dedicated cleanup task.
            # Its operation lifetime handles retirement in the producing task.
            pass
