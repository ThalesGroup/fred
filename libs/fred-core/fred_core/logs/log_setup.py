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

import logging
import os
import sys
import time

from fred_pod.common.config_files import flush_startup_logs
from fred_pod.common.structures import LogOutputFormat

from fred_core.logs.log_structures import AUDIT_LOGGER_NAME, KPI_LOGGER_NAME
from fred_core.logs.processors import (
    STANDARD_ATTRIBUTES,
    ContextSnapshotFilter,
    install_context_capture,
    output_formatter,
)
from fred_core.logs.redaction import (
    sanitize_sensitive_query_params as _sanitize_sensitive_query_params,
)
from fred_core.logs.reported_exceptions import AlreadyReportedExceptionFilter

logger = logging.getLogger(__name__)

__all__ = ["AUDIT_LOGGER_NAME", "KPI_LOGGER_NAME", "dependency_wait_level", "log_setup"]

# Services started together wait for each other (the Control Plane takes about 40 s
# to listen): a dependency retry is routine for this long, then worth a WARNING.
DEPENDENCY_STARTUP_GRACE_SECONDS = 120.0
_started_at = time.monotonic()


def dependency_wait_level() -> int:
    """Level of a "dependency not reachable yet, will retry" line: INFO during the
    startup grace period, WARNING after it."""
    elapsed = time.monotonic() - _started_at
    return (
        logging.INFO if elapsed < DEPENDENCY_STARTUP_GRACE_SECONDS else logging.WARNING
    )


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


def _clear_unrestricted_diagnostic_details(record: logging.LogRecord) -> None:
    record.__dict__.pop("message", None)
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    for key in tuple(record.__dict__):
        if key not in STANDARD_ATTRIBUTES:
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
    service_role: str,
    log_level: str = "INFO",
    include_uvicorn: bool = True,
    use_rich: bool = True,
    log_format: LogOutputFormat = "text",
) -> None:
    """
    Configure Fred root logging plus targeted third-party noise suppression.

    Why this exists:
    - stdout is the only log channel: the platform's collector routes it
    - preserve useful app debug logs while downgrading or isolating noisy
      library loggers that would otherwise drown them out

    How to use:
    - call once during process startup with the service name and its role

    Example:
    - `log_setup(service_name="knowledge-flow", service_role="api", log_level="DEBUG")`
    """
    # Route Python warnings.warn(...) through logging so they share
    # Fred formatting/handlers instead of raw stderr lines.
    logging.captureWarnings(True)

    global _started_at
    _started_at = time.monotonic()
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

    dependency_handler = logging.StreamHandler(sys.stdout)
    dependency_handler.setFormatter(console_handler.formatter)
    dependency_handler.addFilter(DependencyDiagnosticFilter())
    dependency_handler.addFilter(ContextSnapshotFilter())
    dependency_handler.setLevel(max(logging.WARNING, root.level))

    # Client libraries report a fixed diagnostic, never their own text.
    noisy_libs = (
        "opensearch",
        "urllib3",
        "elastic_transport",
        "elasticsearch",
        "aiohttp",
        "httpx",
        "httpx2",
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
        "fastmcp",
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
    # Make uvicorn loggers flow into our handlers (no duplicates)
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
                        AlreadyReportedExceptionFilter,
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
            if name == "uvicorn.error":
                lg.addFilter(AlreadyReportedExceptionFilter())
            lg.addFilter(UvicornSensitiveQueryFilter())
            lg.setLevel(log_level.upper())
            lg.propagate = True  # forward to our root handlers
        logging.getLogger("uvicorn.error").addFilter(UvicornWebsocketNoiseFilter())

    # Dedicated JSON path for the security/audit logger, whatever the output
    # format: same fields as every line, separate logger so a collector can route
    # it, and propagate=False keeps it out of the application handler.
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.handlers.clear()
    audit_handler = logging.StreamHandler(sys.stdout)
    audit_handler.setFormatter(
        output_formatter(service_name, service_role, json_output=True, colors=False)
    )
    audit_handler.addFilter(ContextSnapshotFilter())
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    flush_startup_logs()
