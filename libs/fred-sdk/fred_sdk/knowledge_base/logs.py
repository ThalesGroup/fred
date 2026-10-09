# Copyright Thales 2026
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

"""
How a Knowledge Base pod writes its logs.

Standard output is the only log channel a pod has, so every record goes there,
one JSON object per line: the cluster's log pipeline turns each into fields,
and `service` — the pod's `app.runtime_id` — is the same value its metrics
carry, which is what joins a log line to the series it explains. Field names
are those of Fred's own structured logs (`fred_core`'s `CompactJsonFormatter`),
re-written here in a few lines so a pod never imports the agents platform.
Contract: openspec/specs/knowledge-base-pod-metrics/spec.md.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Literal

LogFormat = Literal["json", "text"]


class _Pending(logging.Handler):
    """Records emitted before the pod knows its identity, kept to be replayed.

    Loading the configuration logs, and the configuration is what names the
    pod: without this, those first lines would be the only ones without
    `service`, in another format, on another stream.
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def hold_until_configured(level: int = logging.INFO) -> None:
    """Keep every record until `configure_logging` can write it as the pod."""
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(_Pending())
    root.setLevel(level)


def _take_pending() -> list[logging.LogRecord]:
    root = logging.getLogger()
    records: list[logging.LogRecord] = []
    for handler in list(root.handlers):
        if isinstance(handler, _Pending):
            records.extend(handler.records)
            root.removeHandler(handler)
    return records


def release_unconfigured() -> None:
    """The pod could not name itself: write what was held as text on stderr.

    Used when loading the configuration fails, so the reason is never lost.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)-7s %(name)s | %(message)s"))
    root = logging.getLogger()
    for record in _take_pending():
        handler.handle(record)
    root.addHandler(handler)


class JsonLineFormatter(logging.Formatter):
    """One record, one line: what a log pipeline parses without being told how."""

    def __init__(self, *, service: str, knowledge_base: str) -> None:
        super().__init__()
        self._service = service
        self._knowledge_base = knowledge_base

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "service": self._service,
            "knowledge_base": self._knowledge_base,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


def configure_logging(
    *, service: str, knowledge_base: str, log_format: LogFormat
) -> None:
    """Send every record to standard output in the configured format.

    Replaces whatever handlers the root logger had, so nothing configured before
    the pod's identity was known writes a second, unattributed copy, and
    replays what `hold_until_configured` kept while the configuration loaded.
    """
    if log_format == "json":
        formatter: logging.Formatter = JsonLineFormatter(
            service=service, knowledge_base=knowledge_base
        )
    else:
        # For a person at a terminal; the runtime id stays on every line.
        formatter = logging.Formatter(
            fmt=f"%(asctime)s | %(levelname)s | {service} | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    held = _take_pending()
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    # Written now, as the pod, so the stream has one format from its first line.
    for record in held:
        handler.handle(record)
