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
from logging import Handler
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Union

from fred_core.logs.base_log_store import (
    BaseLogStore,
    LogEventDTO
)

try:
    from rich.logging import RichHandler
except Exception:  # optional in prod images
    RichHandler = None  # type: ignore


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
        store_or_getter: Union[BaseLogStore, Callable[[], BaseLogStore]],
    ):
        super().__init__()
        self.service = service_name
        self.store_or_getter = store_or_getter

    def _store(self) -> BaseLogStore:
        return (
            self.store_or_getter()
            if callable(self.store_or_getter)
            else self.store_or_getter
        )

    def emit(self, record: logging.LogRecord) -> None:
        import json
        import asyncio

        raw = self.format(record)
        payload = None
        try:
            payload = json.loads(raw)
        except Exception:
            pass  # formatter should be JSON, but we tolerate plain text

        e = LogEventDTO(
            ts=payload.get("ts", record.created) if payload else record.created,
            level=payload.get("level", record.levelname)
            if payload
            else record.levelname,  # type: ignore
            logger=payload.get("logger", record.name) if payload else record.name,
            file=payload.get("file", record.filename) if payload else record.filename,
            line=payload.get("line", record.lineno) if payload else record.lineno,
            msg=payload.get("msg", record.getMessage()) if payload else raw,
            service=payload.get("service", self.service) if payload else self.service,
            extra=payload.get("extra") if payload else None,
        )

        store = self._store()
        # Never block the app on logging:
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(store.index_event, e)
        except RuntimeError:
            # no running loop (sync context) → call directly
            try:
                store.index_event(e)
            except Exception:
                self.handleError(record)


def log_setup(
    *,
    service_name: str,
    log_level: str = "INFO",
    store_or_getter: Union[BaseLogStore, Callable[[], BaseLogStore]],
    file_max_mb: int = 20,
    file_backups: int = 5,
    include_uvicorn: bool = True,
) -> None:
    root = logging.getLogger()
    root.setLevel(log_level.upper())

    marker = f"_fred_handlers_{service_name}"
    if getattr(root, marker, False):
        return

    # 1) Human console (Rich)
    if RichHandler is not None:
        console = RichHandler(
            rich_tracebacks=False,
            show_time=True,
            show_level=True,
            show_path=True,                 # shows module/filename:line
            log_time_format="%Y-%m-%d %H:%M:%S",
            omit_repeated_times=False,      # ← force time on every line
        )
        console.setLevel(log_level.upper())
        root.addHandler(console)

    # 2) Rolling JSON file (machine)
    log_dir = Path.home() / ".fred" / "agentic.logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_h: Handler = RotatingFileHandler(
        log_dir / f"{service_name}.log",
        maxBytes=file_max_mb * 1024 * 1024,
        backupCount=file_backups,
        encoding="utf-8",
    )
    file_h.setLevel(log_level.upper())
    file_h.setFormatter(CompactJsonFormatter(service_name))
    root.addHandler(file_h)

    # 3) Store (machine)
    store_h = StoreEmitHandler(service_name=service_name, store_or_getter=store_or_getter)
    store_h.setLevel(log_level.upper())
    store_h.setFormatter(CompactJsonFormatter(service_name))
    root.addHandler(store_h)

    # 4) Make uvicorn loggers flow into our handlers (no duplicates)
    if include_uvicorn:
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            lg.handlers.clear()     # remove uvicorn’s own console handlers
            lg.propagate = True     # forward to our root handlers

    setattr(root, marker, True)

