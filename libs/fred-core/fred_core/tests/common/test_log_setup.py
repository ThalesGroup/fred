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

import pytest
from fred_core.logs.base_log_store import LogEventDTO
from fred_core.logs.log_setup import (
    AUDIT_LOGGER_NAME,
    CompactJsonFormatter,
    StoreEmitHandler,
    UvicornSensitiveQueryFilter,
    _strip_delegation_query,
    log_setup,
)
from fred_core.security.delegation import DelegationConfig, initialize_delegation


@pytest.fixture(autouse=True)
def _reset_delegation() -> None:
    initialize_delegation(DelegationConfig())


class _StubLogStore:
    def __init__(self) -> None:
        self.indexed: list[LogEventDTO] = []

    def ensure_ready(self) -> None:
        return None

    def index_event(self, event: LogEventDTO) -> None:
        self.indexed.append(event)

    def bulk_index(self, events: list[LogEventDTO]) -> None:
        return None


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


def test_delegation_access_record_is_bounded_and_drops_encoded_grant_pairs() -> None:
    initialize_delegation(
        DelegationConfig(enabled=True, allowed_callers=["synthetic-workload"])
    )
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "SYNTHETIC-CLIENT-CANARY",
            "POST",
            "/documents?ordinary=visible&p%65rson=SYNTHETIC-PERSON-CANARY&"
            "run=SYNTHETIC-RUN-CANARY&agent=SYNTHETIC-AGENT-CANARY&last=kept",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert UvicornSensitiveQueryFilter().filter(record) is True
    assert record.getMessage() == (
        "access event=delegated_request outcome=completed method=POST status=200"
    )
    assert "CANARY" not in repr(record.__dict__)
    assert "ordinary" not in record.getMessage()


def test_delegation_query_stripping_preserves_harmless_pairs_and_order() -> None:
    sanitized, found = _strip_delegation_query(
        "/documents?first=one&p%65rson=person-canary&second=two&run=run-canary"
        "&agent=agent-canary&third=three"
    )

    assert found is True
    assert sanitized == "/documents?first=one&second=two&third=three"


@pytest.mark.parametrize("status", [200, "SYNTHETIC-STATUS-CANARY"])
def test_delegation_access_record_excludes_unbounded_metadata(status: object) -> None:
    initialize_delegation(
        DelegationConfig(enabled=True, allowed_callers=["synthetic-workload"])
    )
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "SYNTHETIC-CLIENT-CANARY",
            "SYNTHETIC-METHOD-CANARY",
            "/documents?person=SYNTHETIC-PERSON-CANARY",
            "SYNTHETIC-VERSION-CANARY",
            status,
        ),
        exc_info=None,
    )
    record.message = "SYNTHETIC-MESSAGE-CANARY"
    record.exc_text = "SYNTHETIC-EXCEPTION-CANARY"
    record.stack_info = "SYNTHETIC-STACK-CANARY"

    UvicornSensitiveQueryFilter().filter(record)

    assert "CANARY" not in repr(record.__dict__)
    if status == 200:
        assert record.getMessage().endswith("method=OTHER status=200")


def test_delegation_access_string_url_is_bounded_without_identifiers() -> None:
    initialize_delegation(
        DelegationConfig(enabled=True, allowed_callers=["synthetic-workload"])
    )
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            "POST /documents?ordinary=visible&person=SYNTHETIC-PERSON-CANARY&"
            "run=SYNTHETIC-RUN-CANARY&agent=SYNTHETIC-AGENT-CANARY 200"
        ),
        args=(),
        exc_info=None,
    )

    assert UvicornSensitiveQueryFilter().filter(record) is True
    assert record.getMessage() == "access event=delegated_request outcome=completed"
    assert "CANARY" not in repr(record.__dict__)


def test_delegation_feature_path_is_bounded_without_grant_query() -> None:
    initialize_delegation(
        DelegationConfig(enabled=True, allowed_callers=["synthetic-workload"])
    )
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "SYNTHETIC-CLIENT-CANARY",
            "POST",
            "/internal/agent-run-tasks/SYNTHETIC-TASK-CANARY/events?ordinary=visible",
            "1.1",
            204,
        ),
        exc_info=None,
    )

    UvicornSensitiveQueryFilter().filter(record)

    assert record.getMessage() == (
        "access event=delegated_request outcome=completed method=POST status=204"
    )
    assert "CANARY" not in repr(record.__dict__)


def test_delegation_flag_off_preserves_grant_query_behavior() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET %s",
        args=("/documents?person=synthetic-person&ordinary=visible",),
        exc_info=None,
    )

    UvicornSensitiveQueryFilter().filter(record)

    assert record.getMessage() == (
        "GET /documents?person=synthetic-person&ordinary=visible"
    )


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


def test_store_emit_handler_category_cannot_be_spoofed_by_message_text() -> None:
    """Issue #2009: category is derived from the LogRecord's logger identity,
    never from message text — a line that merely *contains* "[AUDIT]" or
    "[KPI]" on an ordinary module logger must not be classified as that
    category."""
    store = _StubLogStore()
    handler = StoreEmitHandler(service_name="test-service", store=store)
    handler.setFormatter(CompactJsonFormatter("test-service"))

    record = logging.LogRecord(
        name="some.ordinary.module",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="[AUDIT] fake, not on the real audit logger; also mentions [KPI]",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert len(store.indexed) == 1
    assert store.indexed[0].category == "application"


def test_store_emit_handler_categorizes_reserved_kpi_logger_as_kpi() -> None:
    store = _StubLogStore()
    handler = StoreEmitHandler(service_name="test-service", store=store)
    handler.setFormatter(CompactJsonFormatter("test-service"))

    record = logging.LogRecord(
        name="KPI",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="periodic rollup summary",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert len(store.indexed) == 1
    assert store.indexed[0].category == "kpi"
