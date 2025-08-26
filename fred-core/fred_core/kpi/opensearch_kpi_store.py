# fred_core/kpi/opensearch_kpi_store.py
# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch, RequestsHttpConnection, OpenSearchException

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_core.kpi.kpi_reader_structures import (
    KPIQuery,
    KPIQueryResult,
    KPIQueryResultRow,
)

logger = logging.getLogger(__name__)

# ==============================================================================
# Index mapping (OpenSearch-compatible) — single KPI index
# ==============================================================================
KPI_INDEX_MAPPING: Dict[str, Any] = {
    "settings": {
        "index.number_of_shards": 1,
        "index.number_of_replicas": 1,
        "index.refresh_interval": "5s",
        "index.mapping.total_fields.limit": 2000,
    },
    "mappings": {
        "dynamic": "false",
        "properties": {
            "@timestamp": {"type": "date"},
            "metric": {
                "properties": {
                    "name": {"type": "keyword"},
                    "type": {"type": "keyword"},  # counter | gauge | timer
                    "unit": {"type": "keyword"},
                    "value": {"type": "double"},
                    "count": {"type": "long"},
                    "sum": {"type": "double"},
                    "min": {"type": "double"},
                    "max": {"type": "double"},
                    # Elasticsearch-only type "histogram" is NOT supported by OpenSearch.
                    # Keep a store-only object for forward compatibility without indexing.
                    "histogram": {"type": "object", "enabled": False},
                }
            },
            "dims": {
                "properties": {
                    "env": {"type": "keyword"},
                    "cluster": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "exchange_id": {"type": "keyword"},
                    "agent_id": {"type": "keyword"},
                    "agent_step": {"type": "keyword"},
                    "tool_name": {"type": "keyword"},
                    "model": {"type": "keyword"},
                    "doc_uid": {"type": "keyword"},
                    "doc_source": {"type": "keyword"},
                    "index": {"type": "keyword"},
                    "file_type": {"type": "keyword"},
                    "actor_type": {"type": "keyword"},  # "human" | "system"
                    "scope_type": {
                        "type": "keyword"
                    },  # "session" | "project" | "library"
                    "scope_id": {
                        "type": "keyword"
                    },  # session_id | project_id | library tag
                    "status": {"type": "keyword"},  # ok | error | timeout | filtered
                    "http_status": {"type": "keyword"},  # "200".."599"
                    "error_code": {"type": "keyword"},  # e.g., rate_limit, jwt_invalid
                    "exception_type": {"type": "keyword"},  # e.g., TimeoutError
                    "route": {"type": "keyword"},
                    "method": {"type": "keyword"},
                }
            },
            "cost": {
                "properties": {
                    "tokens_prompt": {"type": "long"},
                    "tokens_completion": {"type": "long"},
                    "tokens_total": {"type": "long"},
                    "usd": {"type": "scaled_float", "scaling_factor": 10000},
                }
            },
            "quantities": {
                "properties": {
                    "bytes_in": {"type": "long"},
                    "bytes_out": {"type": "long"},
                    "chunks": {"type": "integer"},
                    "vectors": {"type": "integer"},
                }
            },
            "labels": {"type": "keyword"},
            "source": {"type": "keyword"},
            "trace": {
                "properties": {
                    "trace_id": {"type": "keyword"},
                    "span_id": {"type": "keyword"},
                    "parent_span_id": {"type": "keyword"},
                }
            },
        },
    },
}


# ==============================================================================
# Store
# ==============================================================================
class OpenSearchKPIStore(BaseKPIStore):
    """
    OpenSearch-backed KPI store (writes + generic aggregated reads).
    - Auto-creates index with KPI_INDEX_MAPPING if missing.
    - Exposes `index_event`, `bulk_index`, and `query` for the KPI DSL.
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
        )
        self.ensure_ready()

    # -- setup -----------------------------------------------------------------
    def ensure_ready(self) -> None:
        try:
            if not self.client.indices.exists(index=self.index):
                self.client.indices.create(index=self.index, body=KPI_INDEX_MAPPING)
                logger.info(f"[KPI] created index '{self.index}'.")
            else:
                logger.info(f"[KPI] index '{self.index}' already exists.")
        except OpenSearchException as e:
            logger.error(f"[KPI] ensure_ready failed: {e}")
            raise

    # -- writes ----------------------------------------------------------------
    def index_event(self, event: KPIEvent) -> None:
        try:
            self.client.index(index=self.index, body=event.to_doc())
        except OpenSearchException as e:
            logger.error(f"[KPI] index_event failed: {e}")
            raise

    def bulk_index(self, events: List[KPIEvent]) -> None:
        if not events:
            return
        actions: List[Dict[str, Any]] = []
        for ev in events:
            actions.append({"index": {"_index": self.index}})
            actions.append(ev.to_doc())
        try:
            resp = self.client.bulk(body=actions)
            if resp.get("errors"):
                logger.warning("[KPI] bulk_index completed with partial errors.")
        except OpenSearchException as e:
            logger.error(f"[KPI] bulk_index failed: {e}")
            raise

    # -- reads -----------------------------------------------------------------
    def query(self, q: KPIQuery) -> KPIQueryResult:
        os_query = self._build_os_query(q)
        resp = self.client.search(index=self.index, body=os_query)
        rows = self._parse_response(q, resp)
        return KPIQueryResult(rows=rows)

    # ---- internal: build OS query -------------------------------------------
    def _build_os_query(self, q: KPIQuery) -> Dict[str, Any]:
        # ---- filters ----
        filters: List[Dict[str, Any]] = [
            {
                "range": {
                    "@timestamp": {
                        "gte": q.since,
                        **({"lte": q.until} if q.until else {}),
                    }
                }
            }
        ]
        for f in q.filters:
            filters.append({"term": {f.field: f.value}})

        base: Dict[str, Any] = {"size": 0, "query": {"bool": {"filter": filters}}}
        aggs: Dict[str, Any] = {}
        root = aggs

        # ---- optional date_histogram (robust) ----
        if q.time_bucket:
            interval = getattr(q.time_bucket, "interval", None)
            tz = getattr(q.time_bucket, "timezone", None)
            if interval:
                root["time"] = {
                    "date_histogram": {
                        "field": "@timestamp",
                        "fixed_interval": interval,
                        **({"time_zone": tz} if tz else {}),
                        "min_doc_count": 0,
                    },
                    "aggs": {},  # ensure key exists before re-rooting
                }
                root = root["time"]["aggs"]
            else:
                logger.debug("[KPI] time_bucket present but missing interval; skipping date_histogram")

        # ---- terms group_bys (safe agg creation) ----
        parent = root
        for i, gb in enumerate(q.group_by or []):
            gkey = f"g{i}"
            parent[gkey] = {
                "terms": {
                    "field": gb,
                    "size": q.limit or 10,  # guard None
                    "order": self._terms_order_clause(q),
                },
                "aggs": {},  # create child aggs inline
            }
            parent = parent[gkey]["aggs"]

        # ---- leaf metrics ----
        for sel in q.select:
            if sel.op == "sum":
                parent[sel.alias] = {"sum": {"field": sel.field}}
            elif sel.op == "avg":
                parent[sel.alias] = {"avg": {"field": sel.field}}
            elif sel.op == "min":
                parent[sel.alias] = {"min": {"field": sel.field}}
            elif sel.op == "max":
                parent[sel.alias] = {"max": {"field": sel.field}}
            elif sel.op == "value_count":
                parent[sel.alias] = {"value_count": {"field": sel.field}}
            elif sel.op == "count":
                # rely on bucket doc_count; parser reads node.doc_count
                # no sub-aggregation needed here
                continue
            elif sel.op == "percentile":
                parent[sel.alias] = {"percentiles": {"field": sel.field, "percents": [sel.p or 95]}}
            else:
                raise ValueError(f"Unsupported op: {sel.op}")

        base["aggs"] = aggs
        return base
    def _terms_order_clause(self, q: KPIQuery) -> Dict[str, Any]:
        if q.order_by and q.order_by.by == "metric" and q.order_by.metric_alias:
            return {q.order_by.metric_alias: q.order_by.direction}
        return {"_count": q.order_by.direction if q.order_by else "desc"}

    # ---- internal: parse OS response ----------------------------------------
    def _parse_response(
        self, q: KPIQuery, resp: Dict[str, Any]
    ) -> List[KPIQueryResultRow]:
        aggs = resp.get("aggregations") or {}
        rows: List[KPIQueryResultRow] = []
        if not aggs:
            return rows

        def collect_metrics(node: Dict[str, Any]) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for sel in q.select:
                if sel.op == "percentile":
                    val = None
                    n = node.get(sel.alias)
                    if n and "values" in n:
                        pkey1 = str(sel.p or 95)
                        pkey2 = f"{float(sel.p or 95):.1f}"
                        val = n["values"].get(pkey1, n["values"].get(pkey2))
                    out[sel.alias] = float(val) if val is not None else 0.0
                elif sel.op == "count":
                    out[sel.alias] = float(node.get("doc_count", 0))
                else:
                    n = node.get(sel.alias)
                    out[sel.alias] = (
                        float(n["value"]) if n and n.get("value") is not None else 0.0
                    )
            return out

        def walk_terms(node: Dict[str, Any], depth: int, group: Dict[str, Any]):
            # If another terms level exists (g{depth}), iterate buckets; else collect metrics.
            gkey = f"g{depth}"
            terms = node.get(gkey)
            if isinstance(terms, dict) and "buckets" in terms:
                for b in terms["buckets"]:
                    g = dict(group)
                    gb_name = q.group_by[depth] if depth < len(q.group_by) else gkey
                    g[gb_name] = b.get("key")
                    # Recurse to next terms depth if present on this bucket
                    next_key = f"g{depth + 1}"
                    if isinstance(b.get(next_key), dict) and "buckets" in b[next_key]:
                        walk_terms(b, depth + 1, g)
                    else:
                        rows.append(
                            KPIQueryResultRow(
                                group=g,
                                metrics=collect_metrics(b),
                                doc_count=int(b.get("doc_count", 0)),
                            )
                        )
                return
            # No more terms at this depth: leaf
            rows.append(
                KPIQueryResultRow(
                    group=group,
                    metrics=collect_metrics(node),
                    doc_count=int(node.get("doc_count", 0)),
                )
            )

        # Entry: time bucket or direct terms or just metrics
        if "time" in aggs and "buckets" in aggs["time"]:
            for tb in aggs["time"]["buckets"]:
                g0 = {"time": tb.get("key_as_string")}
                # If we have group_bys, descend into terms within this time bucket; else collect metrics here.
                if (
                    q.group_by
                    and isinstance(tb.get("g0"), dict)
                    and "buckets" in tb["g0"]
                ):
                    walk_terms(tb, 0, g0)
                else:
                    rows.append(
                        KPIQueryResultRow(
                            group=g0,
                            metrics=collect_metrics(tb),
                            doc_count=int(tb.get("doc_count", 0)),
                        )
                    )
        elif "g0" in aggs:
            walk_terms(aggs, 0, {})
        else:
            # No buckets; only leaf metrics at root
            rows.append(
                KPIQueryResultRow(group={}, metrics=collect_metrics(aggs), doc_count=0)
            )

        return rows
