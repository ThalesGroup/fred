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
import json
import logging
import os
import re
import sys
import threading

from fred_pod.common.config_files import flush_startup_logs
from fred_pod.common.structures import LogOutputFormat

from fred_core.logs.base_log_store import BaseLogStore, LogEventDTO
from fred_core.logs.log_structures import (
    AUDIT_LOGGER_NAME,
    KPI_LOGGER_NAME,
    LogCategory,
)
from fred_core.logs.processors import (
    ContextSnapshotFilter,
    event_properties,
    install_context_capture,
    output_formatter,
)

logger = logging.getLogger(__name__)

__all__ = ["AUDIT_LOGGER_NAME", "KPI_LOGGER_NAME", "log_setup"]

LEVEL_MAP = {
    "DETAIL": "DEBUG",
    "TRACE": "DEBUG",
}


# Attributes a fresh LogRecord carries by default — anything else on a record's
# __dict__ came from a caller's `extra={...}` and should be surfaced, not dropped.
# Introspected from a throwaway record instead of hand-maintained so it tracks
# whatever the running Python version's logging module actually sets.
_STANDARD_LOG_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {"message", "asctime"}


# --- JSON formatter kept tiny and portable ---
class CompactJsonFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service = service_name

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "service": self.service,
            "msg": record.getMessage(),
        }
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_LOG_RECORD_ATTRS
        }
        if record.name != AUDIT_LOGGER_NAME:
            extra = event_properties(record)
        else:
            extra = {
                key: value
                for key, value in extra.items()
                if not key.startswith("_fred_")
            }
        if extra:
            base["extra"] = extra
        return json.dumps(base, ensure_ascii=False, default=str)


# --- Minimal handler that pushes to a BaseLogStore (or a lazy getter) ---
class StoreEmitHandler(logging.Handler):
    def __init__(
        self,
        service_name: str,
        store: BaseLogStore,
    ):
        super().__init__()
        self.service = service_name
        self.store = store
        self._tls = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        # Hard drop, independent of the audit logger's own propagate=False:
        # real security/audit events (fred.security.audit) must never land in
        # the generic app-log store, even if a future refactor accidentally
        # reattaches a handler or flips propagate to True (see
        # docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6).
        if record.name == AUDIT_LOGGER_NAME:
            return
        if getattr(self._tls, "in_emit", False):
            return
        self._tls.in_emit = True
        try:
            raw = self.format(record)
            payload = None
            try:
                payload = json.loads(raw)
            except Exception:
                print("Log record is not JSON: %s", raw)
                # formatter should be JSON, but we tolerate plain text

            if payload:
                mapped_level = LEVEL_MAP.get(payload.get("level"), record.levelname)
            else:
                mapped_level = record.levelname

            # Closed, structural classification — derived from the LogRecord's
            # own logger identity, never from message text (a message that
            # happens to contain "[KPI]" does not become that category; only
            # a record actually emitted on the reserved KPI logger does). See
            # docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6.
            category: LogCategory = (
                "kpi" if record.name == KPI_LOGGER_NAME else "application"
            )

            e = LogEventDTO(
                ts=payload.get("ts", record.created) if payload else record.created,
                level=mapped_level,  # type: ignore
                logger=payload.get("logger", record.name) if payload else record.name,
                file=payload.get("file", record.filename)
                if payload
                else record.filename,
                line=payload.get("line", record.lineno) if payload else record.lineno,
                msg=payload.get("msg", record.getMessage()) if payload else raw,
                service=payload.get("service", self.service)
                if payload
                else self.service,
                extra=payload.get("extra") if payload else None,
                category=category,
            )

            # Never block the app on logging:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.store.index_event, e)
            except RuntimeError:
                # no running loop (sync context) → call directly
                try:
                    self.store.index_event(e)
                except Exception:
                    self.handleError(record)
        finally:
            self._tls.in_emit = False


class UvicornAccessProbeFilter(logging.Filter):
    def __init__(self, probe_paths: tuple[str, ...]) -> None:
        super().__init__()
        self._probe_paths = probe_paths

    def filter(self, record: logging.LogRecord) -> bool:
        path = None
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
        if isinstance(path, str) and any(path.endswith(p) for p in self._probe_paths):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


class UvicornWebsocketNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "WebSocket" in msg and "[accepted]" in msg:
            return False
        return msg not in {"connection open", "connection closed"}


_SENSITIVE_QUERY_PARAM_RE = re.compile(
    r"([?&](?:token|access_token|id_token)=)[^&\s\"]+",
    re.IGNORECASE,
)


def _sanitize_sensitive_query_params(value: str) -> str:
    return _SENSITIVE_QUERY_PARAM_RE.sub(r"\1<redacted>", value)


def _delegation_in_use() -> bool:
    # Local import avoids coupling logging module import order to security/audit
    # initialization, which itself imports the logging package.
    from fred_core.security.delegation import get_delegation_config

    return get_delegation_config().in_use


def _clear_unrestricted_diagnostic_details(record: logging.LogRecord) -> None:
    record.__dict__.pop("message", None)
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    for key in tuple(record.__dict__):
        if key not in _STANDARD_LOG_RECORD_ATTRS and key != "_fred_snapshot":
            record.__dict__.pop(key, None)


class UvicornSensitiveQueryFilter(logging.Filter):
    """
    Redact sensitive query parameter values from uvicorn log records.

    Why this exists:
    - Frontend websocket connections often pass JWT via `?token=...`.
    - Uvicorn access/error logs would otherwise print raw tokens.

    How to use:
    - Attach this filter to `uvicorn.access` and `uvicorn.error` loggers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        delegation_in_use = _delegation_in_use()
        if delegation_in_use or (
            record.name != "uvicorn.access"
            and (record.levelno >= logging.WARNING or record.exc_info is not None)
        ):
            if record.name == "uvicorn.access":
                method = None
                status = None
                if isinstance(record.args, tuple) and len(record.args) >= 5:
                    method = record.args[1]
                    status = record.args[4]
                if method not in {
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                    "HEAD",
                    "OPTIONS",
                }:
                    method = "OTHER"
                if not isinstance(status, int) or not 100 <= status <= 599:
                    status = None
                # Uvicorn writes the access line when the response starts.
                record.msg = (
                    "access event=request outcome=responded method=%s status=%s"
                )
                record.args = (method, status)
            else:
                outcome = (
                    "failed"
                    if record.levelno >= logging.ERROR or record.exc_info
                    else "observed"
                )
                record.msg = "server event=uvicorn outcome=%s reason=%s"
                record.args = (
                    outcome,
                    "server_error" if outcome == "failed" else "lifecycle",
                )
            _clear_unrestricted_diagnostic_details(record)
            return True
        if isinstance(record.msg, str):
            record.msg = _sanitize_sensitive_query_params(record.msg)

        if isinstance(record.args, tuple):
            sanitized_args: list[object] = []
            for arg in record.args:
                if isinstance(arg, str):
                    sanitized = _sanitize_sensitive_query_params(arg)
                    sanitized_args.append(sanitized)
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        return True


class DependencyDiagnosticFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """Retain dependency severity/source without exporting upstream text or content."""
        record.msg = "Dependency diagnostic"
        record.args = ()
        _clear_unrestricted_diagnostic_details(record)
        return True


def log_setup(
    *,
    service_name: str,
    log_level: str = "INFO",
    store: BaseLogStore,
    include_uvicorn: bool = True,
    use_rich: bool = True,
    log_format: LogOutputFormat = "text",
    service_role: str | None = None,
) -> None:
    """
    Configure Fred root logging plus targeted third-party noise suppression.

    Why this exists:
    - keep one consistent console/store logging pipeline across Fred services
    - preserve useful app debug logs while downgrading or isolating noisy
      library loggers that would otherwise drown them out

    How to use:
    - call once during service startup with the service name and active log store

    Example:
    - `log_setup(service_name="fred-runtime", log_level="DEBUG", store=store)`
    """
    # Route Python warnings.warn(...) through logging so they share
    # Fred formatting/handlers instead of raw stderr lines.
    logging.captureWarnings(True)

    root = logging.getLogger()
    root.setLevel(log_level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    install_context_capture()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        output_formatter(
            service_name,
            service_role,
            json_output=log_format == "json",
            colors=use_rich and sys.stdout.isatty() and "NO_COLOR" not in os.environ,
        )
    )
    console_handler.addFilter(ContextSnapshotFilter())
    console_handler.setLevel(log_level.upper())
    root.addHandler(console_handler)

    # 3) Store (machine) — optional for sandbox compatibility
    store_h = StoreEmitHandler(service_name=service_name, store=store)
    store_h.addFilter(ContextSnapshotFilter())
    store_h.setLevel(log_level.upper())
    store_h.setFormatter(CompactJsonFormatter(service_name))
    root.addHandler(store_h)

    dependency_handler = logging.StreamHandler(sys.stdout)
    dependency_handler.setFormatter(console_handler.formatter)
    dependency_handler.addFilter(DependencyDiagnosticFilter())
    dependency_handler.addFilter(ContextSnapshotFilter())
    dependency_handler.setLevel(max(logging.WARNING, root.level))

    # Fred: prevent client libraries from bouncing through our StoreEmitHandler.
    noisy_libs = (
        "opensearch",
        "urllib3",
        "elastic_transport",
        "elasticsearch",
        "aiohttp",
        "httpx",
        "httpcore",
        "azure",
        "azure.core",
        "azure.identity",
        "msal",
        "websockets",
        "websockets.server",
        "websockets.protocol",
        "websockets.client",
        "aiosqlite",
        "httptools",
        "mcp.client.streamable_http",
        "openai",
        "openai._base_client",
    )
    for noisy in noisy_libs:
        lg = logging.getLogger(noisy)
        lg.handlers.clear()  # their own handlers (if any) → gone
        lg.addHandler(dependency_handler)
        lg.setLevel(max(logging.WARNING, root.level))
        lg.propagate = False  # <-- key: do NOT bubble up to root
    extra_noisy = (
        "pdfminer",
        "pdfminer.pdfinterp",
    )
    for noisy in extra_noisy:
        lg = logging.getLogger(noisy)
        lg.setLevel(logging.ERROR)  # even more severe
    # 4) Make uvicorn loggers flow into our handlers (no duplicates)
    if include_uvicorn:
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            lg.handlers.clear()  # remove uvicorn’s own console handlers
            lg.filters[:] = [
                f
                for f in lg.filters
                if not isinstance(
                    f,
                    (
                        UvicornAccessProbeFilter,
                        UvicornSensitiveQueryFilter,
                        UvicornWebsocketNoiseFilter,
                    ),
                )
            ]
            if name == "uvicorn.access":
                # Reads the raw request path, which the sensitive filter below can drop.
                lg.addFilter(UvicornAccessProbeFilter(("/healthz", "/ready")))
                # The ASGI completion event owns HTTP access, including streams.
                lg.disabled = True
            lg.addFilter(UvicornSensitiveQueryFilter())
            lg.setLevel(log_level.upper())
            lg.propagate = True  # forward to our root handlers
        logging.getLogger("uvicorn.error").addFilter(UvicornWebsocketNoiseFilter())

    # 5) Dedicated single-line JSON path for the security/audit logger.
    # Structured audit events (authz decisions, tool-call invocations) must
    # reach stdout as valid, self-contained JSON so a platform-native log
    # pipeline (Cloud Logging or equivalent) can parse and route them without
    # scraping free text — the human-readable console formatter above is not
    # JSON. propagate=False keeps an audit line from also printing through
    # that console handler.
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.handlers.clear()
    audit_handler = logging.StreamHandler(sys.stdout)
    audit_handler.setFormatter(CompactJsonFormatter(service_name))
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(log_level.upper())
    audit_logger.propagate = False
    flush_startup_logs()
