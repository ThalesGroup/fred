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
# OpenSearch-backed LOG store mirroring OpenSearchKPIStore design:
# - Single index with explicit mapping (stable fields)
# - Writes: index_event / bulk_index
# - Reads: query(LogQuery) -> LogQueryResult
#
# Notes for future devs:
# - We store both textual level (INFO) *and* numeric severity (0..4) to support fast "level_at_least".
# - We keep @timestamp as epoch_second so date_histogram and range queries are cheap.
# - "logger" and "service" are keyword; msg is text. For "contains" on logger, we use wildcard on `.keyword`.
# - For msg full-text filter, we use match or simple_query_string depending on the need.

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from opensearchpy import OpenSearch, OpenSearchException, RequestsHttpConnection

from fred_core.logs.base_log_store import BaseLogStore, LogEventDTO, LogQuery
from fred_core.logs.log_structures import LogFilter, LogQueryResult

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# ---- Index mapping -----------------------------------------------------------
logger = logging.getLogger(__name__)

LOG_INDEX_MAPPING: Dict[str, Any] = {
    "settings": {
        "index.number_of_shards": 1,
        "index.number_of_replicas": 1,
        "index.refresh_interval": "5s",
        "index.mapping.total_fields.limit": 2000,
    },
    "mappings": {
        "dynamic": "false",
        "properties": {
            "@timestamp": {
                "type": "date",
                "format": "epoch_millis||strict_date_optional_time",
            },
            "level": {"type": "keyword"},  # DEBUG/INFO/...
            "severity": {"type": "byte"},  # 0..4 for fast >= filter
            "logger": {"type": "keyword"},
            "service": {"type": "keyword"},
            "file": {"type": "keyword"},
            "line": {"type": "integer"},
            "msg": {"type": "text"},
            "extra": {"type": "object", "enabled": True},
        },
    },
}

# ---- Helpers ----------------------------------------------------------------
LEVEL_TO_SEVERITY: Dict[str, int] = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}


def _sev(level: LogLevel) -> int:
    return LEVEL_TO_SEVERITY.get(level, 1)


def _to_epoch_millis(ts: Union[int, float, str]) -> int:
    # Accept seconds(float/int), millis(int > 1e12), or ISO string → epoch_millis int
    if isinstance(ts, (int, float)):
        return int(ts if ts > 1_000_000_000_000 else ts * 1000)
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    raise TypeError(f"Unsupported ts type: {type(ts)}")


def _to_iso_utc(ts: Union[int, float, str]) -> str:
    # Always return ISO-8601 in UTC with trailing 'Z'
    if isinstance(ts, str):
        return (
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    ms = _to_epoch_millis(ts)
    return (
        datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _doc_from_event(ev: LogEventDTO) -> Dict[str, Any]:
    # Why both @timestamp and severity:
    # - @timestamp: native time ops (range, histogram)
    # - severity: numeric range for "level_at_least"
    return {
        "@timestamp": _to_iso_utc(ev.ts),
        "level": ev.level,
        "severity": _sev(ev.level),
        "logger": ev.logger,
        "service": ev.service,
        "file": ev.file,
        "line": ev.line,
        "msg": ev.msg,
        "extra": ev.extra,
    }


# =============================================================================
# Store
# =============================================================================
class OpenSearchLogStore(BaseLogStore):
    """
    OpenSearch-backed LOG store (writes + simple filtered reads).
    Mirrors OpenSearchKPIStore patterns for familiarity.
    """

    def __init__(
        self,
        host: str,
        index: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.index = index
        self.client = OpenSearch(
            host,
            http_auth=(username, password) if username else None,
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
            ssl_show_warn=False,
        )
        self.ensure_ready()

    # -- setup -----------------------------------------------------------------
    def ensure_ready(self) -> None:
        try:
            if not self.client.indices.exists(index=self.index):
                self.client.indices.create(index=self.index, body=LOG_INDEX_MAPPING)
                logger.info(f"[LOG] created index '{self.index}'.")
            else:
                logger.info(f"[LOG] index '{self.index}' already exists.")
                # If you have a generic validator like KPI does, call it here:
                # validate_index_mapping(self.client, self.index, LOG_INDEX_MAPPING)
        except OpenSearchException as e:
            logger.error(f"[LOG] ensure_ready failed: {e}")
            raise

    # -- writes ----------------------------------------------------------------
    def index_event(self, event: LogEventDTO) -> None:
        try:
            self.client.index(index=self.index, body=_doc_from_event(event))
        except OpenSearchException as e:
            raise e

    def bulk_index(self, events: List[LogEventDTO]) -> None:
        if not events:
            return
        actions: List[Dict[str, Any]] = []
        for ev in events:
            actions.append({"index": {"_index": self.index}})
            actions.append(_doc_from_event(ev))
        try:
            resp = self.client.bulk(body=actions)
            if resp.get("errors"):
                print("[LOG] bulk_index completed with partial errors.")
        except OpenSearchException as e:
            print(f"[LOG] bulk_index failed: {e}")
            raise

    # -- reads -----------------------------------------------------------------
    def query(self, q: LogQuery) -> LogQueryResult:
        body = self._build_os_query(q)
        # print("\n[DEBUG][OpenSearchLogStore] === query body ===")
        # import json
        # print(json.dumps(body, indent=2))
        resp = self.client.search(index=self.index, body=body)
        hits = resp.get("hits", {}).get("hits", [])
        events: List[LogEventDTO] = []
        # print(f"[DEBUG][OpenSearchLogStore] hits: {len(hits)}")
        for h in hits:
            s = h.get("_source", {})
            raw_ts = s.get("@timestamp", 0)
            try:
                ts_sec = _to_epoch_millis(raw_ts) / 1000.0
            except Exception:
                # Fallback to 0 if the doc is malformed
                ts_sec = 0.0
            events.append(
                LogEventDTO(
                    ts=ts_sec,
                    level=s.get("level", "INFO"),
                    logger=s.get("logger", ""),
                    file=s.get("file", ""),
                    line=int(s.get("line") or 0),
                    msg=s.get("msg", ""),
                    service=s.get("service"),
                    extra=s.get("extra"),
                )
            )
        return LogQueryResult(events=events)

    # ---- internal: build precise OS query -----------------------------------
    def _build_os_query(self, q: LogQuery) -> Dict[str, Any]:
        """
        Exact OpenSearch JSON returned to the cluster for transparency and debugging.
        Filters implemented:
        - time range: since..until on @timestamp
        - level_at_least: severity >= threshold
        - logger_like: wildcard on logger (keyword) using *contains*
        - service: exact term
        - text_like: match_phrase on msg (fast, low-surprise). Switch to SQS if needed.
        Ordering + limit are applied at top level.
        """

        def _opt_iso(v):
            return _to_iso_utc(v) if v is not None else None

        since_iso = _opt_iso(q.since)
        until_iso = _opt_iso(q.until)
        filters: List[Dict[str, Any]] = [
            {
                "range": {
                    "@timestamp": {
                        k: v for k, v in (("gte", since_iso), ("lte", until_iso)) if v
                    }
                }
            }
        ]
        f = q.filters or LogFilter()
        if f.level_at_least:
            filters.append({"range": {"severity": {"gte": _sev(f.level_at_least)}}})
        if f.service:
            filters.append({"term": {"service": f.service}})
        if f.logger_like:
            # "contains" on keyword via wildcard; case-sensitive. For case-insensitive, store a lowercase subfield.
            filters.append({"wildcard": {"logger": f"*{f.logger_like}*"}})
        # message text filter: keep it optional and independent from filter context
        must: List[Dict[str, Any]] = []
        if f.text_like:
            must.append({"match_phrase": {"msg": f.text_like}})

        body: Dict[str, Any] = {
            "size": q.limit,
            "query": {
                "bool": {
                    "filter": filters,
                    **({"must": must} if must else {}),
                }
            },
            "sort": [{"@timestamp": {"order": q.order}}],
        }
        return body
