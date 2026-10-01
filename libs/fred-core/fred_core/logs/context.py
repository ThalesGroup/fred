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
from dataclasses import dataclass
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import TypeAlias

from structlog.contextvars import bind_contextvars, get_contextvars, reset_contextvars

LogValue: TypeAlias = (
    str | int | float | bool | None | list["LogValue"] | dict[str, "LogValue"]
)
LogContext: TypeAlias = dict[str, LogValue]

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
def log_context(*, clear: tuple[str, ...] = (), **values: LogValue) -> Iterator[None]:
    """Bind nested metadata and restore it on all exits, including cancellation."""
    validated = safe_context(values)
    tokens = bind_contextvars(**{**dict.fromkeys(clear), **validated})
    try:
        yield
    finally:
        reset_contextvars(**tokens)
