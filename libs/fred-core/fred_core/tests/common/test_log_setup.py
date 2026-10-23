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
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import pytest
from fred_core.logs.log_setup import (
    AUDIT_LOGGER_NAME,
    CompactJsonFormatter,
    StoreEmitHandler,
    UvicornSensitiveQueryFilter,
    log_setup,
)
from fred_core.logs.log_structures import LogEventDTO
from fred_core.security.delegation import DelegationConfig, initialize_delegation


@pytest.fixture(autouse=True)
def _reset_delegation() -> Iterator[None]:
    initialize_delegation(DelegationConfig())
    loggers = [
        logging.getLogger(),
        *[
            entry
            for entry in logging.Logger.manager.loggerDict.values()
            if isinstance(entry, logging.Logger)
        ],
    ]
    saved = [
        (
            entry,
            entry.level,
            list(entry.handlers),
            list(entry.filters),
            entry.propagate,
            entry.disabled,
        )
        for entry in loggers
    ]
    factory = logging.getLogRecordFactory()
    try:
        yield
    finally:
        logging.setLogRecordFactory(factory)
        for entry, level, handlers, filters, propagate, disabled in saved:
            entry.setLevel(level)
            entry.handlers[:] = handlers
            entry.filters[:] = filters
            entry.propagate = propagate
            entry.disabled = disabled
        for entry in list(logging.Logger.manager.loggerDict.values()):
            if isinstance(entry, logging.Logger) and entry not in loggers:
                entry.handlers.clear()
                entry.filters.clear()
                entry.disabled = False
                entry.propagate = True
                entry.setLevel(logging.NOTSET)


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


@pytest.mark.parametrize(
    "config",
    [
        DelegationConfig(),
        DelegationConfig(accept_delegated_calls=True),
        DelegationConfig(act_for_people=True),
    ],
)
def test_uvicorn_sanitization_preserves_diagnostics_independently_of_delegation(
    config: DelegationConfig,
) -> None:
    initialize_delegation(config)
    error = RuntimeError("ordinary failure")
    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Failure at %s",
        ("/documents?person=synthetic-person&token=synthetic-token&ordinary=visible",),
        (type(error), error, None),
    )
    record.stack_info = "ordinary stack"
    record.detail = "ordinary extra"
    assert UvicornSensitiveQueryFilter().filter(record)
    assert (
        record.getMessage()
        == "Failure at /documents?person=<redacted>&token=<redacted>&ordinary=visible"
    )
    assert record.exc_info is not None
    assert record.exc_info[1] is error
    assert record.stack_info == "ordinary stack"
    assert record.__dict__["detail"] == "ordinary extra"


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
def test_duplicate_uvicorn_access_is_suppressed_under_delegation(
    config: DelegationConfig, path: str
) -> None:
    initialize_delegation(config)
    with _wired_uvicorn_logging() as (info_sink, _):
        _log_uvicorn_access(path)
        assert logging.getLogger("uvicorn.access").handlers == []

    assert info_sink.records == []


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
    assert all_sink.records == []


def test_duplicate_uvicorn_access_is_suppressed_without_delegation() -> None:
    with _wired_uvicorn_logging() as (info_sink, _):
        _log_uvicorn_access("/documents?token=synthetic-token&ordinary=visible")

    assert info_sink.records == []


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
    logger.setLevel(logging.INFO)
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
    logger.setLevel(logging.INFO)
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

    from fred_core.logs.context import log_context
    from fred_core.logs.processors import ContextSnapshot

    with log_context(user_id="person-canary", tool_name="tool-canary"):
        record = audit_logger.makeRecord(
            AUDIT_LOGGER_NAME, logging.INFO, __file__, 1, "audit", (), None
        )
    snapshot = getattr(record, "_fred_snapshot")
    assert isinstance(snapshot, ContextSnapshot)
    assert snapshot.values == {}


def test_audit_logger_still_accepts_info_when_application_log_level_is_warning() -> (
    None
):
    log_setup(
        service_name="test-log-setup-audit-level",
        log_level="WARNING",
        store=_StubLogStore(),
        include_uvicorn=False,
        use_rich=False,
    )
    assert logging.getLogger(AUDIT_LOGGER_NAME).isEnabledFor(logging.INFO)


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


@pytest.mark.parametrize("log_format", ["json", "text"])
@pytest.mark.parametrize(
    ("message", "args", "expected"),
    [
        ("pool_size=%s max_overflow=%d", (5, 10), "pool_size=5 max_overflow=10"),
        ("pool_size=%(size)s", ({"size": 5},), "pool_size=5"),
        ("Started server process [%d]", (123,), "Started server process [123]"),
        ("literal 50% done", (), "literal 50% done"),
        ("progress=%d%%", (50,), "progress=50%"),
        ("first=%s\nsecond=%s", ("a", "b"), "first=a\nsecond=b"),
    ],
)
def test_shared_output_preserves_legacy_arguments_and_structured_fields(
    capsys: pytest.CaptureFixture[str],
    log_format: Literal["json", "text"],
    message: str,
    args: tuple[object, ...],
    expected: str,
) -> None:
    from fred_core.logs.context import log_context

    with _wired_uvicorn_logging():
        store = _StubLogStore()
        log_setup(
            service_name="legacy-compatibility",
            store=store,
            log_format=log_format,
            use_rich=False,
        )
        logger = logging.getLogger("uvicorn.error")
        with log_context(correlation_id="operation-a"):
            record = logger.makeRecord(
                logger.name,
                logging.INFO,
                __file__,
                1,
                message,
                args,
                None,
                extra={"count": 3},
            )
            original_args = record.args
            logger.handle(record)

        output = capsys.readouterr().out
        if log_format == "json":
            assert len(output.splitlines()) == 1
            event = json.loads(output)
            assert event["message"] == expected
            assert event["count"] == 3
            assert event["correlation_id"] == "operation-a"
        else:
            assert expected in output
            assert "count=3" in output
            assert "correlation_id=operation-a" in output
        assert len(store.indexed) == 1
        assert store.indexed[0].msg == expected
        assert store.indexed[0].extra == {"count": 3, "correlation_id": "operation-a"}
        assert record.msg == message
        assert record.args == original_args


@pytest.mark.parametrize("delegation", [False, True])
@pytest.mark.parametrize("logger_name", ["httpx.transport", "httpx2._client"])
def test_dependency_child_diagnostics_remain_sanitized(
    capsys: pytest.CaptureFixture[str],
    delegation: bool,
    logger_name: str,
) -> None:
    initialize_delegation(DelegationConfig(accept_delegated_calls=delegation))
    log_setup(
        service_name="dependency-contract",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )
    logging.getLogger(logger_name).info(
        "HTTP request to http://tools.invalid/mcp?person=private&run=private&agent=private"
    )
    assert capsys.readouterr().out == ""
    logging.getLogger(logger_name).warning(
        "SECRET-CANARY signed_url=%s",
        "SECRET-CANARY",
        extra={"detail": "SECRET-CANARY"},
        exc_info=(ValueError, ValueError("SECRET-CANARY"), None),
        stack_info=True,
    )
    output = capsys.readouterr().out
    assert "SECRET-CANARY" not in output
    assert json.loads(output)["severity"] == "WARNING"


@pytest.mark.parametrize(
    "config",
    [
        DelegationConfig(),
        DelegationConfig(accept_delegated_calls=True),
        DelegationConfig(act_for_people=True),
    ],
)
@pytest.mark.parametrize("log_format", ["json", "text"])
def test_uvicorn_error_preserves_traceback_with_targeted_redaction(
    capsys: pytest.CaptureFixture[str],
    config: DelegationConfig,
    log_format: Literal["json", "text"],
) -> None:
    initialize_delegation(config)
    url = "https://example.invalid/file?access_token=SYNTHETIC-CREDENTIAL&format=csv"
    with _wired_uvicorn_logging():
        log_setup(
            service_name="server-contract",
            store=_StubLogStore(),
            log_format=log_format,
            use_rich=False,
        )
        try:
            raise RuntimeError("workbook parse failed") from ValueError(
                "Failed request " + url
            )
        except RuntimeError:
            logging.getLogger("uvicorn.error").exception("ASGI operation failed")
        output = capsys.readouterr().out
        assert "SYNTHETIC-CREDENTIAL" not in output
        assert "workbook parse failed" in output
        assert "ValueError" in output
        assert "ASGI operation failed" in output
        if log_format == "json":
            assert len(output.splitlines()) == 1
            event = json.loads(output)
            assert event["severity"] == "ERROR"
            assert "Traceback" in event["exception"]
            assert "test_uvicorn_error_preserves_traceback" in event["exception"]


def test_context_rejects_aggregate_metadata_without_stringifying_objects() -> None:
    from fred_core.logs.context import log_context

    with pytest.raises(ValueError):
        with log_context(details=[["x" * 1024] * 32] * 32):
            pass
    with pytest.raises(ValueError):
        with log_context(details=object()):
            pass


def test_context_clips_an_oversized_string_instead_of_failing_the_scope() -> None:
    from fred_core.logs.context import (
        MAX_VALUE_BYTES,
        current_context,
        log_context,
        operation_log_scope,
    )

    looped = "é" * 4000 + " >>> read_document"
    with operation_log_scope(tool_name=looped):
        bound = current_context()["tool_name"]
    assert isinstance(bound, str) and bound.endswith("...")
    assert len(bound.encode("utf-8")) <= MAX_VALUE_BYTES
    with pytest.raises(ValueError):
        with log_context({"x" * 65: "value"}):
            pass


@pytest.mark.asyncio
async def test_fastapi_unhandled_error_keeps_response_and_log_references(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import Mock

    from fred_core.common.fastapi_handlers import register_exception_handlers
    from fred_core.kpi.base_kpi_writer import BaseKPIWriter
    from fred_core.kpi.http_middleware import KPIMiddleware
    from fred_core.logs.context import bind_operation_context
    from fred_core.logs.http import REFERENCE_HEADERS, RequestLoggingFastAPI
    from httpx import ASGITransport, AsyncClient
    from starlette.middleware.cors import CORSMiddleware

    log_setup(
        service_name="error-contract",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )
    app = RequestLoggingFastAPI()
    app.add_request_middleware(
        CORSMiddleware,
        allow_origins=["https://fred.example"],
        allow_methods=["GET"],
        allow_headers=["Authorization"],
        expose_headers=REFERENCE_HEADERS,
    )
    kpi = Mock(spec=BaseKPIWriter)
    app.add_request_middleware(KPIMiddleware, kpi=kpi)
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure() -> None:
        bind_operation_context(
            user_id="synthetic-user",
            session_id="synthetic-session",
            agent_id="synthetic-agent",
            team_id="synthetic-team",
        )
        raise RuntimeError("ordinary application failure")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/failure", headers={"Origin": "https://fred.example"}
        )
        preflight = await client.options(
            "/failure",
            headers={
                "Origin": "https://fred.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["access-control-allow-origin"] == "https://fred.example"
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-request-id" in exposed and "x-correlation-id" in exposed
    output = capsys.readouterr().out
    assert "ordinary application failure" in output
    events = [json.loads(line) for line in output.splitlines()]
    completed = [
        event
        for event in events
        if event["logger"] == "http" and event["http_method"] == "GET"
    ]
    assert len(completed) == 1
    assert completed[0]["http_status"] == 500
    assert completed[0]["outcome"] == "failed"
    failure_event = next(
        event for event in events if event["message"] == "Unhandled request failure"
    )
    for event in [completed[0], failure_event]:
        assert event["request_id"] == response.headers["x-request-id"]
        assert event["correlation_id"] == response.headers["x-correlation-id"]
        assert event["user_id"] == "synthetic-user"
        assert event["session_id"] == "synthetic-session"
        assert event["agent_id"] == "synthetic-agent"
        assert event["team_id"] == "synthetic-team"
    assert "RuntimeError: ordinary application failure" in failure_event["exception"]
    assert preflight.status_code == 200
    assert [call.kwargs["method"] for call in kpi.api_call.call_args_list] == [
        "GET",
        "OPTIONS",
    ]
    assert kpi.api_call.call_args_list[0].kwargs["exception_type"] == "RuntimeError"
    assert kpi.api_call.call_args_list[1].kwargs["exception_type"] is None


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_startup_diagnostics_wait_for_selected_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    log_format: Literal["json", "text"],
) -> None:
    from fred_pod.common import config_files
    from fred_pod.common.config_files import ConfigFiles

    # Simulate fresh startup, independent of logging initialized by other tests.
    monkeypatch.setattr(config_files, "_logging_ready", False)
    monkeypatch.setattr(config_files, "_startup_events", deque(maxlen=32))
    files = ConfigFiles(logger=logging.getLogger("config-test"))
    # Use a real dotenv file to distinguish its diagnostic path from its contents.
    env_file = tmp_path / ".env"
    env_file.write_text("FRED_TEST=private-value\n", encoding="utf-8")
    monkeypatch.delenv("FRED_TEST", raising=False)
    files.load_environment(str(env_file))
    # Simulate successful YAML loading; this test exercises logging, not parsing.
    config_file = str(tmp_path / "configuration.yaml")
    files.mark_config_loaded(config_file)
    # Both startup events must remain buffered until the output format is known.
    assert not capsys.readouterr().out

    # Real setup flushes the buffer through the selected formatter and fake store.
    store = _StubLogStore()
    log_setup(
        service_name="bootstrap-test",
        store=store,
        log_format=log_format,
        include_uvicorn=False,
    )
    output = capsys.readouterr().out
    # Paths survive as structured metadata, while file contents stay out of output.
    assert "private-value" not in output
    assert store.indexed[-1].extra == {
        "env_file": str(env_file),
        "config_file": config_file,
    }
    if log_format == "json":
        # The last line is the configuration event, queued after the environment event.
        event = json.loads(output.splitlines()[-1])
        assert event["service"] == "bootstrap-test"
        assert event["severity"] == "INFO"
        assert event["env_file"] == str(env_file)
        assert event["config_file"] == config_file
        assert config_file not in event["message"]
    else:
        assert f"env_file={env_file}" in output
        assert f"config_file={config_file}" in output

    # After setup, new events must emit immediately without another buffer flush.
    lazy_config_file = str(tmp_path / "lazy-configuration.yaml")
    files.mark_config_loaded(lazy_config_file)
    output = capsys.readouterr().out
    assert store.indexed[-1].extra == {
        "env_file": str(env_file),
        "config_file": lazy_config_file,
    }
    if log_format == "json":
        assert json.loads(output)["config_file"] == lazy_config_file
    else:
        assert f"config_file={lazy_config_file}" in output


@pytest.mark.asyncio
async def test_interleaved_request_context_survives_stream_and_thread_then_retires(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import asyncio
    import threading
    from types import SimpleNamespace

    from fred_core.common.resilient_sink import ResilientSinkStore
    from fred_core.logs.context import bind_operation_context, operation_log_scope
    from fred_core.logs.http import RequestLoggingMiddleware

    store_release = threading.Event()
    delivered = threading.Event()
    expected_count = [0]

    class DelayedStore(_StubLogStore):
        def index_event(self, event: LogEventDTO) -> None:
            assert store_release.wait(timeout=2)
            super().index_event(event)
            if len(self.indexed) == expected_count[0]:
                delivered.set()

    store = DelayedStore()
    log_setup(
        service_name="request-test",
        store=ResilientSinkStore(store),
        log_format="json",
        include_uvicorn=False,
    )

    both_ready = asyncio.Event()
    release_late = asyncio.Event()
    arrivals = 0
    retained: list[asyncio.Task[None]] = []
    responses: dict[str, list[dict]] = {}

    async def app(scope, receive, send):
        nonlocal arrivals
        person = scope["person"]
        bind_operation_context(user_id=person, session_id=f"session-{person}")

        async def late():
            await release_late.wait()
            logging.getLogger("late").info("Retained task")

        retained.append(asyncio.create_task(late()))
        await asyncio.to_thread(logging.getLogger("thread").info, "Sync work")
        if person != "third":
            arrivals += 1
            if arrivals == 2:
                both_ready.set()
            await asyncio.wait_for(both_ready.wait(), timeout=2)
        if person == "failed":
            raise asyncio.CancelledError()
        if person == "first":

            async def run():
                with operation_log_scope(completion=True):
                    bind_operation_context(
                        template_agent_id="root-template",
                        agent_instance_id="root-instance",
                    )
                    bind_operation_context(document_uid="x" * 1025)

                    async def child():
                        with operation_log_scope(
                            completion=False, clear=("agent_instance_id",)
                        ):
                            bind_operation_context(template_agent_id="child-template")
                            logging.getLogger("child").info("Child work")

                    await asyncio.create_task(child())
                    yield None

            iterator = run()
            await anext(iterator)
            await asyncio.create_task(iterator.aclose())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        assert not any(
            event.get("logger") == "http" and event.get("user_id") == person
            for event in captured()
        )
        await send({"type": "http.response.body", "body": b"last"})

    seen: list[dict] = []

    def captured():
        seen.extend(json.loads(line) for line in capsys.readouterr().out.splitlines())
        return seen

    async def request(person):
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            responses.setdefault(person, []).append(message)

        await RequestLoggingMiddleware(app)(
            {
                "type": "http",
                "method": "GET",
                "path": "/untrusted/raw",
                "person": person,
                "route": SimpleNamespace(path="/items/{item}"),
            },
            receive,
            send,
        )

    results = await asyncio.wait_for(
        asyncio.gather(request("first"), request("failed"), return_exceptions=True),
        timeout=3,
    )
    assert isinstance(results[1], asyncio.CancelledError)
    await asyncio.wait_for(request("third"), timeout=3)
    release_late.set()
    await asyncio.wait_for(asyncio.gather(*retained), timeout=3)
    events = captured()
    expected_count[0] = len(events)
    assert store.indexed == []
    store_release.set()
    assert await asyncio.to_thread(delivered.wait, timeout=2)
    persisted = [event for event in store.indexed if event.logger == "http"]
    assert len(persisted) == 3
    assert all(
        event.extra is not None
        and event.extra["session_id"] == f"session-{event.extra['user_id']}"
        for event in persisted
    )
    completions = [event for event in events if event["logger"] == "http"]
    assert len(completions) == 3
    assert len({event["request_id"] for event in completions}) == 3
    assert all(
        event["session_id"] == f"session-{event['user_id']}" for event in completions
    )
    failed = next(event for event in completions if event["user_id"] == "failed")
    assert failed["outcome"] == "cancelled"
    assert "http_status" not in failed
    assert all(event["route"] == "/items/{item}" for event in completions)
    assert all(
        event["session_id"] == f"session-{event['user_id']}"
        for event in events
        if event["logger"] == "thread"
    )
    assert all(
        "user_id" not in event and "request_id" not in event
        for event in events
        if event["logger"] == "late"
    )
    first = next(event for event in completions if event["user_id"] == "first")
    assert first["template_agent_id"] == "root-template"
    assert first["agent_instance_id"] == "root-instance"
    assert "document_uid" not in first
    child = next(event for event in events if event["logger"] == "child")
    assert child["template_agent_id"] == "child-template"
    for person in ("first", "third"):
        headers = dict(responses[person][0]["headers"])
        completion = next(event for event in completions if event["user_id"] == person)
        assert headers[b"x-request-id"].decode() == completion["request_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("log_format", ["json", "text"])
@pytest.mark.parametrize(
    ("case", "status", "route", "summary"),
    [
        ("responded", 200, "/sessions/{session_id}/runs", "200 | 8ms"),
        ("responded", 403, "/sessions/{session_id}/runs", "403 | 8ms"),
        ("responded", 503, "/sessions/{session_id}/runs", "503 | 8ms"),
        ("responded", 404, None, "404 | 8ms"),
        ("responded", 404, "x" * 1025, "404 | 8ms"),
        ("failed", None, None, "no response | 8ms | failed"),
        ("failed", 200, "/stream", "200 | 8ms | failed"),
        ("cancelled", None, None, "no response | 8ms | cancelled"),
        ("cancelled", 200, None, "200 | 8ms | cancelled"),
        ("disconnected", 200, None, "200 | 8ms | disconnected"),
        ("incomplete", 200, None, "200 | 8ms | incomplete"),
    ],
)
async def test_http_completion_message_is_readable_and_retains_structured_fields(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    log_format: Literal["json", "text"],
    case: str,
    status: int | None,
    route: str | None,
    summary: str,
) -> None:
    import asyncio
    from types import SimpleNamespace

    from fred_core.logs import http as http_logging
    from starlette.requests import ClientDisconnect

    ticks = iter([10.0, 10.008])
    monkeypatch.setattr(
        http_logging, "time", SimpleNamespace(perf_counter=lambda: next(ticks))
    )
    store = _StubLogStore()
    log_setup(
        service_name="completion-test",
        store=store,
        log_format=log_format,
        include_uvicorn=False,
    )

    async def app(scope, receive, send):
        if status is not None:
            await send({"type": "http.response.start", "status": status, "headers": []})
        if case == "failed":
            raise RuntimeError("ordinary application failure")
        if case == "cancelled":
            raise asyncio.CancelledError()
        if case == "disconnected":
            raise ClientDisconnect()
        if case != "incomplete":
            await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/raw-secret-canary",
        "query_string": b"token=query-secret-canary",
    }
    if route is not None:
        scope["route"] = SimpleNamespace(path=route)
    errors = {
        "failed": RuntimeError,
        "cancelled": asyncio.CancelledError,
        "disconnected": ClientDisconnect,
    }
    if case in errors:
        with pytest.raises(errors[case]):
            await http_logging.RequestLoggingMiddleware(app)(scope, receive, send)
    else:
        await http_logging.RequestLoggingMiddleware(app)(scope, receive, send)

    await asyncio.sleep(0)
    output = capsys.readouterr().out
    safe_route = route if route is not None and len(route) <= 1024 else "<unmatched>"
    expected = f"POST {safe_route} → {summary}"
    completions = [event for event in store.indexed if event.logger == "http"]
    assert len(completions) == 1
    event = completions[0]
    assert event.msg == expected
    assert event.extra is not None
    assert event.extra["http_method"] == "POST"
    assert event.extra["duration_ms"] == pytest.approx(8.0)
    assert event.extra["outcome"] == case
    assert event.extra.get("http_status") == status
    assert event.extra.get("route") == (route if safe_route != "<unmatched>" else None)
    if log_format == "json":
        completion = next(
            json.loads(line)
            for line in output.splitlines()
            if json.loads(line)["logger"] == "http"
        )
        assert completion["message"] == expected
    else:
        assert expected in output
    assert "secret-canary" not in output
    assert "x" * 1025 not in output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["disconnect", "failed-probe", "successful-probe", "unmatched"]
)
async def test_completion_handles_real_stream_disconnect_and_probe_failures(
    capsys: pytest.CaptureFixture[str], case: str
) -> None:
    from fred_core.logs.http import RequestLoggingMiddleware
    from starlette.requests import ClientDisconnect
    from starlette.responses import Response, StreamingResponse

    log_setup(
        service_name="completion-test",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )

    async def body():
        yield b"part"

    async def app(scope, receive, send):
        response = (
            StreamingResponse(body())
            if case == "disconnect"
            else Response(
                status_code=200
                if case == "successful-probe"
                else 503
                if case == "failed-probe"
                else 404
            )
        )
        await response(scope, receive, send)

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        if case == "disconnect" and message["type"] == "http.response.body":
            raise OSError("synthetic transport failure")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/healthz" if "probe" in case else "/raw-canary",
        "asgi": {"spec_version": "2.4"},
    }
    if case == "disconnect":
        with pytest.raises(ClientDisconnect):
            await RequestLoggingMiddleware(app)(scope, receive, send)
    else:
        await RequestLoggingMiddleware(app)(scope, receive, send)
    output = capsys.readouterr().out
    if case == "successful-probe":
        assert output == ""
        return
    event = json.loads(output)
    assert "route" not in event
    assert "raw-canary" not in output
    assert event["http_status"] == (
        200 if case == "disconnect" else 503 if case == "failed-probe" else 404
    )
    assert event["severity"] == ("ERROR" if case == "failed-probe" else "WARNING")
    assert event["outcome"] == ("disconnected" if case == "disconnect" else "responded")


@pytest.mark.parametrize(
    "path",
    [
        "/control-plane/v1/platform-access/free/opaque-token/enroll",
        "/ui/join/opaque-token",
    ],
)
def test_free_enrollment_capability_is_redacted_without_delegation(path, monkeypatch):
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, "%s", (path,), None
    )
    UvicornSensitiveQueryFilter().filter(record)
    assert "opaque-token" not in record.getMessage()
    assert "<redacted>" in record.getMessage()


@pytest.mark.parametrize(
    "case", ["absent", "unmarked", "marked", "marked-cause", "empty-info"]
)
def test_reported_exception_filter_is_a_pure_exact_exception_check(case: str) -> None:
    from fred_core.logs.reported_exceptions import (
        AlreadyReportedExceptionFilter,
        mark_reported,
        was_reported,
    )

    error = RuntimeError("same message")
    if case == "marked":
        mark_reported(error)
    elif case == "marked-cause":
        cause = RuntimeError("same message")
        mark_reported(cause)
        error.__cause__ = cause
    info = None if case == "absent" else (type(error), error, None)
    if case == "empty-info":
        info = (None, None, None)
    record = logging.LogRecord(
        "uvicorn.error", logging.ERROR, __file__, 1, "failure", (), info
    )
    before = dict(record.__dict__)
    assert AlreadyReportedExceptionFilter().filter(record) is (case != "marked")
    assert record.__dict__ == before
    assert was_reported(error) is (case == "marked")
    assert not was_reported(RuntimeError("same message"))


def test_reported_exception_marker_supports_frozen_exception_subclasses() -> None:
    from dataclasses import dataclass

    from fred_core.logs.reported_exceptions import mark_reported, was_reported

    @dataclass(frozen=True)
    class FrozenFailure(Exception):
        message: str

    error = FrozenFailure("failure")
    mark_reported(error)
    assert was_reported(error)
    assert "_fred_already_logged" not in str(error)


def test_duplicate_filter_is_separate_and_replaced_on_reinitialization() -> None:
    from fred_core.logs.reported_exceptions import AlreadyReportedExceptionFilter

    with _wired_uvicorn_logging():
        for _ in range(2):
            log_setup(service_name="filter-wiring", store=_StubLogStore())
        filters = logging.getLogger("uvicorn.error").filters
        assert sum(isinstance(f, AlreadyReportedExceptionFilter) for f in filters) == 1
        duplicate = next(
            i
            for i, f in enumerate(filters)
            if isinstance(f, AlreadyReportedExceptionFilter)
        )
        redaction = next(
            i
            for i, f in enumerate(filters)
            if isinstance(f, UvicornSensitiveQueryFilter)
        )
        assert duplicate < redaction


@pytest.mark.asyncio
async def test_concurrent_request_exceptions_keep_the_completion_identity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import asyncio

    from fred_core.common.fastapi_handlers import register_exception_handlers
    from fred_core.logs.context import bind_operation_context
    from fred_core.logs.http import RequestLoggingFastAPI
    from httpx import ASGITransport, AsyncClient
    from starlette.middleware.base import BaseHTTPMiddleware

    log_setup(
        service_name="concurrent-errors",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )
    app = RequestLoggingFastAPI()

    async def dispatch(request, call_next):
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=dispatch)
    register_exception_handlers(app)
    ready: set[str] = set()
    both_ready = asyncio.Event()
    fields = ("user_id", "session_id", "agent_id", "team_id")

    @app.get("/probe/{name}")
    async def probe(name: str) -> dict[str, bool]:
        if name == "fresh":
            return {"ok": True}
        bind_operation_context({field: name + "-" + field for field in fields})
        ready.add(name)
        if len(ready) == 2:
            both_ready.set()
        await asyncio.wait_for(both_ready.wait(), timeout=5)
        raise RuntimeError("failure for " + name)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        first, second = await asyncio.gather(
            client.get("/probe/first"), client.get("/probe/second")
        )
        fresh = await client.get("/probe/fresh")
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    for name, response in [("first", first), ("second", second)]:
        assert response.status_code == 500
        request_events = [
            event
            for event in events
            if event.get("request_id") == response.headers["x-request-id"]
        ]
        assert len(request_events) == 2
        assert {event["logger"] for event in request_events} == {
            "http",
            "fred_core.logs.http",
        }
        for event in request_events:
            assert event["severity"] == "ERROR"
            assert event["correlation_id"] == response.headers["x-correlation-id"]
            assert all(event[field] == name + "-" + field for field in fields)
        diagnostic = next(event for event in request_events if "exception" in event)
        assert "RuntimeError: failure for " + name in diagnostic["exception"]
    fresh_events = [
        event
        for event in events
        if event.get("request_id") == fresh.headers["x-request-id"]
    ]
    assert len(fresh_events) == 1
    assert all(field not in fresh_events[0] for field in fields)
    assert fresh_events[0]["severity"] == "INFO"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["caught", "http", "response", "oserror"])
async def test_http_error_diagnostic_ownership(
    capsys: pytest.CaptureFixture[str], case: str
) -> None:
    from fastapi import HTTPException
    from fred_core.common.fastapi_handlers import register_exception_handlers
    from fred_core.logs.http import RequestLoggingFastAPI
    from httpx import ASGITransport, AsyncClient
    from starlette.responses import JSONResponse

    log_setup(
        service_name="ownership",
        store=_StubLogStore(),
        log_format="json",
        include_uvicorn=False,
    )
    app = RequestLoggingFastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure() -> JSONResponse:
        if case == "caught":
            try:
                raise ValueError("controller failure")
            except ValueError:
                logging.getLogger("synthetic.controller").exception("Controller failed")
                raise HTTPException(500, "Internal server error")
        if case == "http":
            raise HTTPException(500, "Internal server error")
        if case == "oserror":
            raise OSError("application storage failure")
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/failure")
    assert response.status_code == 500
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(events) == (2 if case in {"caught", "oserror"} else 1)
    completion = next(event for event in events if event["logger"] == "http")
    assert completion["http_status"] == 500
    assert completion["severity"] == "ERROR"
    assert "exception" not in completion
    if case in {"caught", "oserror"}:
        diagnostic = next(event for event in events if "exception" in event)
        assert diagnostic["request_id"] == completion["request_id"]
        assert diagnostic["logger"] == (
            "synthetic.controller" if case == "caught" else "fred_core.logs.http"
        )
