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

from __future__ import annotations

import json
import logging

from fred_core.logs.base_log_store import LogEventDTO
from fred_core.logs.log_setup import (
    AUDIT_LOGGER_NAME,
    CompactJsonFormatter,
    StoreEmitHandler,
    UvicornSensitiveQueryFilter,
    log_setup,
)
from fred_core.logs.log_structures import LogQuery, LogQueryResult


class _StubLogStore:
    def __init__(self) -> None:
        self.indexed: list[LogEventDTO] = []

    def ensure_ready(self) -> None:
        return None

    def index_event(self, event: LogEventDTO) -> None:
        self.indexed.append(event)

    def bulk_index(self, events: list[LogEventDTO]) -> None:
        return None

    def query(self, q: LogQuery) -> LogQueryResult:
        raise NotImplementedError


def test_uvicorn_sensitive_query_filter_redacts_token_in_args() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "WebSocket %s" %d',
        args=(
            "127.0.0.1:12345",
            "/agentic/v1/chatbot/query/ws?token=jwt-value&x=1",
            403,
        ),
        exc_info=None,
    )

    assert UvicornSensitiveQueryFilter().filter(record) is True
    assert isinstance(record.args, tuple)
    assert isinstance(record.args[1], str)
    assert record.args[1] == "/agentic/v1/chatbot/query/ws?token=<redacted>&x=1"


def test_log_setup_suppresses_aiosqlite_debug_noise() -> None:
    log_setup(
        service_name="test-log-setup-aiosqlite",
        log_level="DEBUG",
        store=_StubLogStore(),
        include_uvicorn=False,
        use_rich=False,
    )

    logger = logging.getLogger("aiosqlite")

    assert logger.level == logging.WARNING
    assert logger.propagate is False


def test_compact_json_formatter_surfaces_extra_fields() -> None:
    """extra={...} on a logging call must survive into the JSON payload — this
    is what StoreEmitHandler/LogEventDTO already expect (they read payload
    "extra"), and what audit events depend on to carry their structured
    fields instead of being reduced to a bare message string."""
    logger = logging.getLogger("test-compact-json-formatter")
    logger.propagate = False
    logger.handlers.clear()
    lines: list[str] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    handler = _CapturingHandler()
    handler.setFormatter(CompactJsonFormatter("test-service"))
    logger.addHandler(handler)

    logger.info(
        "[SECURITY] %s",
        "authz_denied",
        extra={"audit_event": "authz_denied", "user_id": "u-1", "team_id": "t-1"},
    )

    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["msg"] == "[SECURITY] authz_denied"
    assert payload["extra"] == {
        "audit_event": "authz_denied",
        "user_id": "u-1",
        "team_id": "t-1",
    }


def test_compact_json_formatter_omits_extra_key_when_absent() -> None:
    logger = logging.getLogger("test-compact-json-formatter-no-extra")
    logger.propagate = False
    logger.handlers.clear()
    lines: list[str] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    handler = _CapturingHandler()
    handler.setFormatter(CompactJsonFormatter("test-service"))
    logger.addHandler(handler)

    logger.info("plain message")

    payload = json.loads(lines[0])
    assert "extra" not in payload


def test_log_setup_gives_audit_logger_a_dedicated_non_propagating_json_handler() -> (
    None
):
    log_setup(
        service_name="test-log-setup-audit",
        log_level="INFO",
        store=_StubLogStore(),
        include_uvicorn=False,
        use_rich=False,
    )

    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)

    assert audit_logger.propagate is False
    assert len(audit_logger.handlers) == 1
    assert isinstance(audit_logger.handlers[0].formatter, CompactJsonFormatter)


def test_store_emit_handler_hard_drops_audit_logger_records() -> None:
    """Issue #2009: belt-and-braces alongside AUDIT_LOGGER_NAME's own
    propagate=False — even if a handler were mistakenly attached directly to
    the audit logger, StoreEmitHandler must never index that record into the
    generic app-log store."""
    store = _StubLogStore()
    handler = StoreEmitHandler(service_name="test-service", store=store)
    handler.setFormatter(CompactJsonFormatter("test-service"))

    record = logging.LogRecord(
        name=AUDIT_LOGGER_NAME,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="[SECURITY] agent.tool.invocation.completed",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert store.indexed == []


def test_store_emit_handler_indexes_ordinary_records() -> None:
    store = _StubLogStore()
    handler = StoreEmitHandler(service_name="test-service", store=store)
    handler.setFormatter(CompactJsonFormatter("test-service"))

    record = logging.LogRecord(
        name="some.ordinary.module",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="an ordinary application log line",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert len(store.indexed) == 1
    assert store.indexed[0].logger == "some.ordinary.module"
