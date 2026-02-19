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
import threading
from typing import Any, Optional

from fred_core.logs.base_log_store import BaseLogStore, LogEventDTO

try:
    from rich.logging import RichHandler
except Exception:  # optional in prod images
    RichHandler = None  # type: ignore

logger = logging.getLogger(__name__)

LEVEL_MAP = {
    "DETAIL": "DEBUG",
    "TRACE": "DEBUG",
}


# --- JSON formatter kept tiny and portable ---
class CompactJsonFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service = service_name

    def format(self, record: logging.LogRecord) -> str:
        import json

        base = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "service": self.service,
            "msg": record.getMessage(),
        }
        return json.dumps(base, ensure_ascii=False)


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
                pass  # formatter should be JSON, but we tolerate plain text

            if payload:
                mapped_level = LEVEL_MAP.get(payload.get("level"), record.levelname)
            else:
                mapped_level = record.levelname

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
            )

            # Never block the app on logging:
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(self.store.index_event, e)
            except RuntimeError:
                # no running loop (sync context) → call directly
                try:
                    self.store.index_event(e)
                except Exception:
                    self.handleError(record)
        finally:
            self._tls.in_emit = False


class TaskNameFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """Adds the current asyncio Task name to the log record."""
        try:
            current_task: Optional[asyncio.Task[Any]] = asyncio.current_task()
            if current_task is not None:
                # Add a custom attribute to the record
                record.task_name = current_task.get_name() or str(id(current_task))
            else:
                record.task_name = "Main"
        except RuntimeError:
            # Handles cases where not inside an asyncio loop (e.g., initial sync setup)
            record.task_name = "Sync"
        return True


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


def log_setup(
    *,
    service_name: str,
    log_level: str = "INFO",
    store: BaseLogStore,
    include_uvicorn: bool = True,
    use_rich: bool = True,
) -> None:
    # Route Python warnings.warn(...) through logging so they share
    # Fred formatting/handlers instead of raw stderr lines.
    logging.captureWarnings(True)

    root = logging.getLogger()
    root.setLevel(log_level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    marker = f"_fred_handlers_{service_name}"
    if getattr(root, marker, False):
        return

    # 1) Human console (Rich or plain)
    formatter = logging.Formatter(
        # Include process ID, task name, and thread name for concurrency diagnostics.
        fmt="%(asctime)s | %(levelname)s | [pid=%(process)d %(threadName)s/%(task_name)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if use_rich and RichHandler is not None:
        console_handler: logging.Handler = RichHandler(
            rich_tracebacks=False,
            show_time=False,  # Time is now in the custom formatter
            show_level=True,
            show_path=True,
            log_time_format="%Y-%m-%d %H:%M:%S",
        )
    else:
        console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(TaskNameFilter())
    console_handler.setLevel(log_level.upper())
    root.addHandler(console_handler)

    # 3) Store (machine) — optional for sandbox compatibility
    store_h = StoreEmitHandler(service_name=service_name, store=store)
    store_h.setLevel(log_level.upper())
    store_h.setFormatter(CompactJsonFormatter(service_name))
    root.addHandler(store_h)

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
        "httptools",
        "mcp.client.streamable_http",
    )
    for noisy in noisy_libs:
        lg = logging.getLogger(noisy)
        lg.handlers.clear()  # their own handlers (if any) → gone
        lg.setLevel(logging.WARNING)
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
            # Access logs are particularly chatty; keep only warnings+
            if name == "uvicorn.access":
                lg.addFilter(UvicornAccessProbeFilter(("/healthz", "/ready")))
                lg.setLevel(log_level.upper())
            else:
                lg.setLevel(log_level.upper())
            lg.propagate = True  # forward to our root handlers
        logging.getLogger("uvicorn.error").addFilter(UvicornWebsocketNoiseFilter())

    setattr(root, marker, True)
