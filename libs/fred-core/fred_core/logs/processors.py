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

import asyncio
import logging
from datetime import datetime, timezone
from structlog.typing import EventDict

from structlog.processors import JSONRenderer, format_exc_info
from structlog.stdlib import ProcessorFormatter

from fred_core.logs.context import (
    RESERVED_FIELDS,
    current_context,
    safe_key,
    safe_value,
)

STANDARD_ATTRIBUTES = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "_fred_context",
    "_fred_task",
}


class ContextSnapshotFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """Capture once in the emitter, before any store/thread handoff."""
        if not hasattr(record, "_fred_context"):
            record._fred_context = current_context()
            try:
                task = asyncio.current_task()
                record._fred_task = task.get_name() if task is not None else "Main"
            except RuntimeError:
                record._fred_task = "Sync"
        return True


def event_properties(record: logging.LogRecord) -> dict[str, object]:
    """Keep JSON-safe extras while protecting bound identity and event metadata."""
    context = getattr(record, "_fred_context", {})
    properties: dict[str, object] = {}
    for key, value in vars(record).items():
        if key in STANDARD_ATTRIBUTES or key in RESERVED_FIELDS or key in context:
            continue
        try:
            properties[safe_key(key)] = safe_value(value)
        except ValueError:
            continue
    return {**properties, **context}


class EventProcessor:
    def __init__(self, service: str, role: str | None) -> None:
        self.service = service
        self.role = role

    def __call__(
        self, logger: object, method: str, event: EventDict
    ) -> EventDict:  # structlog event adapter
        """Build output from the LogRecord, never from a listener's context."""
        record: logging.LogRecord = event["_record"]
        seconds = int(record.created)
        severity = next(
            (
                name
                for level, name in (
                    (50, "CRITICAL"),
                    (40, "ERROR"),
                    (30, "WARNING"),
                    (20, "INFO"),
                    (10, "DEBUG"),
                )
                if record.levelno >= level
            ),
            "DEFAULT",
        )
        result = {
            **event_properties(record),
            "severity": severity,
            "timestamp": {
                "seconds": seconds,
                "nanos": int((record.created - seconds) * 1_000_000_000),
            },
            "message": record.getMessage(),
            "logger": record.name,
            "service": self.service,
            "category": "kpi" if record.name == "KPI" else "application",
            "logging.googleapis.com/sourceLocation": {
                "file": record.filename,
                "line": str(record.lineno),
                "function": record.funcName,
            },
            "process": record.process,
            "thread": record.threadName,
            "task_name": getattr(record, "_fred_task", "Sync"),
        }
        if self.role is not None:
            result["service_role"] = self.role
        if record.exc_info:
            # Delegated call sites and the server filter supply bounded diagnostics.
            from fred_core.security.delegation import get_delegation_config

            if not get_delegation_config().in_use:
                result["exc_info"] = record.exc_info
                result = format_exc_info(logger, method, result)
        return result


class TextRenderer:
    def __init__(self, colors: bool) -> None:
        self.colors = colors

    def __call__(
        self, logger: object, method: str, event: EventDict
    ) -> str:  # structlog event adapter
        """Render readable diagnostics without terminal-width layout or truncation."""
        stamp = datetime.fromtimestamp(
            event["timestamp"]["seconds"], timezone.utc
        ).isoformat()
        severity = event["severity"]
        if self.colors:
            color = (
                "31"
                if severity in {"ERROR", "CRITICAL"}
                else "33"
                if severity == "WARNING"
                else "36"
            )
            severity = f"\x1b[{color}m{severity}\x1b[0m"
        detail = " ".join(
            f"{key}={value}"
            for key, value in event.items()
            if key not in RESERVED_FIELDS
        )
        output = f"{stamp} {severity} {event['service']}/{event['logger']} {event['message']}"
        if detail:
            output += " " + detail
        if "exception" in event:
            output += "\n" + event["exception"]
        return output


def output_formatter(
    service: str, role: str | None, *, json_output: bool, colors: bool
) -> ProcessorFormatter:
    """Configure stdlib events through the same structlog processors/renderers."""
    return ProcessorFormatter(
        processors=[
            EventProcessor(service, role),
            JSONRenderer(ensure_ascii=False, allow_nan=False)
            if json_output
            else TextRenderer(colors),
        ]
    )
