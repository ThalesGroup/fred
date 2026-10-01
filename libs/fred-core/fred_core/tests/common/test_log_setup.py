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

import io
import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fred_core.logs.base_log_store import LogEventDTO
from fred_core.logs.log_setup import (
    AUDIT_LOGGER_NAME,
    CompactJsonFormatter,
    StoreEmitHandler,
    UvicornSensitiveQueryFilter,
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
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
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
        "access event=request outcome=responded method=POST status=200"
    )
    assert "CANARY" not in repr(record.__dict__)
    assert "ordinary" not in record.getMessage()


@pytest.mark.parametrize("status", [200, "SYNTHETIC-STATUS-CANARY"])
def test_delegation_access_record_excludes_unbounded_metadata(status: object) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
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
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
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
    assert record.getMessage() == (
        "access event=request outcome=responded method=OTHER status=None"
    )
    assert "CANARY" not in repr(record.__dict__)


def test_without_delegation_grant_query_behavior_is_preserved() -> None:
    initialize_delegation(DelegationConfig())
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


def test_acting_for_people_alone_still_keeps_grant_values_out_of_the_log() -> None:
    # A grant sent to a backend that does not believe it is still caller-chosen text.
    initialize_delegation(DelegationConfig(act_for_people=True))
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
        "access event=request outcome=responded method=OTHER status=None"
    )
    assert "synthetic-person" not in repr(record.__dict__)


class _Sink(logging.Handler):
    def __init__(self, level: int) -> None:
        super().__init__(level)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _wired_uvicorn_logging() -> Iterator[tuple[_Sink, _Sink]]:
    """Wire uvicorn through `log_setup`; yield an INFO sink and an all-levels sink."""
    root = logging.getLogger()
    saved_root = (root.level, list(root.handlers))
    saved_uvicorn = [
        (lg, list(lg.filters), list(lg.handlers), lg.level, lg.propagate)
        for lg in map(logging.getLogger, ("uvicorn", "uvicorn.error", "uvicorn.access"))
    ]
    service_name = f"test-uvicorn-wiring-{uuid.uuid4().hex}"
    # Uvicorn's default config gives the access logger its own non-propagating handler.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(logging.StreamHandler(io.StringIO()))
    access_logger.propagate = False
    log_setup(
        service_name=service_name,
        log_level="INFO",
        store=_StubLogStore(),
        use_rich=False,
    )
    info_sink, all_sink = _Sink(logging.INFO), _Sink(logging.NOTSET)
    root.addHandler(info_sink)
    root.addHandler(all_sink)
    try:
        yield info_sink, all_sink
    finally:
        root.setLevel(saved_root[0])
        root.handlers[:] = saved_root[1]
        for lg, filters, handlers, level, propagate in saved_uvicorn:
            lg.filters[:] = filters
            lg.handlers[:] = handlers
            lg.setLevel(level)
            lg.propagate = propagate


def _log_uvicorn_access(path: str) -> None:
    # Same call shape as uvicorn's HTTP protocol implementations.
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", path, "1.1", 200
    )


_DELEGATION_SWITCHES = [
    pytest.param(
        DelegationConfig(accept_delegated_calls=True), id="accept-delegated-calls"
    ),
    pytest.param(DelegationConfig(act_for_people=True), id="act-for-people"),
]


@pytest.mark.parametrize("config", _DELEGATION_SWITCHES)
@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/documents", id="no-grant"),
        pytest.param(
            "/documents?person=SYNTHETIC-PERSON-CANARY&run=SYNTHETIC-RUN-CANARY"
            "&agent=SYNTHETIC-AGENT-CANARY",
            id="query-grant",
        ),
        pytest.param(
            "/teams/SYNTHETIC-TEAM-CANARY/documents/SYNTHETIC-DOCUMENT-CANARY",
            id="path-parameters",
        ),
    ],
)
def test_delegation_access_line_is_neutral_for_every_request(
    config: DelegationConfig, path: str
) -> None:
    initialize_delegation(config)
    with _wired_uvicorn_logging() as (info_sink, _):
        _log_uvicorn_access(path)
        assert logging.getLogger("uvicorn.access").handlers == []

    assert [record.getMessage() for record in info_sink.records] == [
        "access event=request outcome=responded method=GET status=200"
    ]
    assert "CANARY" not in repr(info_sink.records[0].__dict__)


@pytest.mark.parametrize(
    "config",
    [pytest.param(DelegationConfig(), id="delegation-off"), *_DELEGATION_SWITCHES],
)
@pytest.mark.parametrize(
    "path", ["/knowledge-flow/v1/healthz", "/control-plane/v1/ready"]
)
def test_health_probes_stay_below_the_default_level(
    config: DelegationConfig, path: str
) -> None:
    initialize_delegation(config)
    with _wired_uvicorn_logging() as (info_sink, all_sink):
        _log_uvicorn_access(path)

    assert info_sink.records == []
    assert [record.levelno for record in all_sink.records] == [logging.DEBUG]


def test_without_delegation_access_line_keeps_request_details() -> None:
    with _wired_uvicorn_logging() as (info_sink, _):
        _log_uvicorn_access("/documents?token=synthetic-token&ordinary=visible")

    assert [record.getMessage() for record in info_sink.records] == [
        '127.0.0.1:5000 - "GET /documents?token=<redacted>&ordinary=visible '
        'HTTP/1.1" 200'
    ]


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


def test_shared_output_contract_and_repeat_setup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from fred_core.logs.context import log_context

    root = logging.getLogger()
    saved = (root.level, list(root.handlers))
    store = _StubLogStore()
    try:
        for _ in range(2):
            log_setup(
                service_name="contract-test",
                store=store,
                log_format="json",
                service_role="api",
                include_uvicorn=False,
            )
        with log_context(user_id="person-a", correlation_id="operation-a"):
            logging.getLogger("contract.event").warning(
                "first\nsecond",
                extra={
                    "count": 3,
                    "user_id": "spoof",
                    "severity": "spoof",
                    # Synthetic credential tests that forged snapshots are ignored.
                    "_fred_context": {"user_id": "spoof", "token": "SECRET-CANARY"},  # nosec B105
                },
            )
        lines = capsys.readouterr().out.splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["severity"] == "WARNING"
        assert event["message"] == "first\nsecond"
        assert event["user_id"] == "person-a"
        assert event["count"] == 3
        assert event["service_role"] == "api"
        assert event["timestamp"]["seconds"] == int(store.indexed[0].ts)
        assert 0 <= event["timestamp"]["nanos"] < 1_000_000_000
        assert store.indexed[0].extra is not None
        assert store.indexed[0].extra["correlation_id"] == "operation-a"
        assert "\x1b" not in lines[0]
        assert "SECRET-CANARY" not in lines[0]
        log_setup(
            service_name="contract-test",
            store=store,
            log_format="text",
            include_uvicorn=False,
        )
        logging.getLogger("contract.event").info("intentional\nmultiline")
        readable = capsys.readouterr().out
        assert "intentional\nmultiline" in readable
        assert "\x1b" not in readable
    finally:
        root.handlers[:] = saved[1]
        root.setLevel(saved[0])


def test_dependency_child_diagnostics_remain_sanitized(
    capsys: pytest.CaptureFixture[str],
) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=True))
    log_setup(
        service_name="dependency-contract",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )
    logging.getLogger("httpx.transport").warning("SECRET-CANARY signed_url=credential")
    output = capsys.readouterr().out
    assert "SECRET-CANARY" not in output
    assert json.loads(output)["severity"] == "WARNING"


def test_context_rejects_aggregate_metadata_without_stringifying_objects() -> None:
    from fred_core.logs.context import log_context

    with pytest.raises(ValueError):
        with log_context(details=[["x" * 1024] * 32] * 32):
            pass
    with pytest.raises(ValueError):
        with log_context(details=object()):
            pass


def test_startup_diagnostics_wait_for_selected_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_pod.common import config_files
    from fred_pod.common.config_files import ConfigFiles

    monkeypatch.setattr(config_files, "_logging_ready", False)
    files = ConfigFiles(logger=logging.getLogger("config-test"))
    files.mark_config_loaded("/sensitive/customer/configuration.yaml")
    assert not capsys.readouterr().out
    log_setup(
        service_name="bootstrap-test",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )
    output = capsys.readouterr().out
    event = json.loads(output)
    assert event["service"] == "bootstrap-test"
    assert event["severity"] == "INFO"
    assert "sensitive" not in output
    files.mark_config_loaded("/sensitive/lazy/configuration.yaml")
    assert json.loads(capsys.readouterr().out)["service"] == "bootstrap-test"
