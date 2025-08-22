# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Dict, List, Optional, Tuple

from opensearchpy import OpenSearch
from pydantic import BaseModel

# If you don't actually need BaseHistoryStore for this monitor, you can remove the inheritance.
from app.common.utils import truncate_datetime
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse

logger = logging.getLogger(__name__)

# ==============================================================================
# Categorization helpers
# ==============================================================================

# (regex, category)
_CATEGORY_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(session|sessions)\b", "session"),
    (r"\b(history|chat|messages?)\b", "history"),
    (r"\b(meta|metadata)\b", "metadata"),
    (r"\b(tag|tags)\b", "tag"),
    (r"\b(resource|resources)\b", "resource"),
    (r"\b(vector|emb(ed|edding)s?|chunks?)\b", "vector"),
    (r"\b(feedback|ratings?|evals?)\b", "feedback"),
]

_ENV_RE = re.compile(r"-(dev|test|test\d+|qa|stage|staging|preprod|prod)\b", re.I)
_VER_RE = re.compile(r"-v(\d+)\b", re.I)


def _categorize_index(name: str) -> Tuple[str, Optional[str], Optional[int]]:
    """
    Infer (category, env, version) from an index name using simple conventions:
    - category: session/metadata/feedback/history/tag/resource/vector/other (by regex)
    - env: suffix like -dev, -test, -test1, -qa, -stage, -staging, -preprod, -prod
    - version: suffix like -v1, -v2, ...
    """
    n = name.lower()
    category = "other"
    for rx, cat in _CATEGORY_PATTERNS:
        if re.search(rx, n):
            category = cat
            break

    env = None
    m_env = _ENV_RE.search(n)
    if m_env:
        env = m_env.group(1).lower()

    ver: Optional[int] = None
    m_ver = _VER_RE.search(n)
    if m_ver:
        try:
            ver = int(m_ver.group(1))
        except ValueError:
            pass

    return category, env, ver


# ==============================================================================
# Response models
# ==============================================================================

class CategoryTotals(BaseModel):
    indices: int
    docs_count: int
    docs_deleted: int
    store_size_bytes: int
    pri_store_size_bytes: int


class PragmaticIndexRow(BaseModel):
    index: str
    category: str
    env: Optional[str] = None
    version: Optional[int] = None
    pri: Optional[int] = None  # number_of_shards
    rep: Optional[int] = None  # number_of_replicas
    docs_count: int = 0
    docs_deleted: int = 0
    store_size_bytes: int = 0
    pri_store_size_bytes: int = 0


class PragmaticIndicesReport(BaseModel):
    categories: Dict[str, CategoryTotals]
    totals: CategoryTotals
    rows: List[PragmaticIndexRow]


def _sum_totals(rows: List[PragmaticIndexRow]) -> CategoryTotals:
    return CategoryTotals(
        indices=len(rows),
        docs_count=sum(r.docs_count for r in rows),
        docs_deleted=sum(r.docs_deleted for r in rows),
        store_size_bytes=sum(r.store_size_bytes for r in rows),
        pri_store_size_bytes=sum(r.pri_store_size_bytes for r in rows),
    )


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    units = ["KB", "MB", "GB", "TB", "PB", "EB"]
    v = float(n)
    for u in units:
        v /= 1024.0
        if v < 1024:
            return f"{v:.2f} {u}"
    return f"{v:.2f} ZB"


# ==============================================================================
# Monitoring service
# ==============================================================================

class OpensearchMonitoringService():
    """
    Lightweight monitoring service that produces a dashboard-friendly summary of indices,
    grouped by inferred 'category' (based on index naming conventions).
    """

    def __init__(
        self, client: OpenSearch
    ):
        self.client = client

    def get_app_metrics(
        self,
        precision: str = "hour",
        groupby: List[str] | None = None,
        agg_mapping: Dict[str, List[str]] | None = None,
    ):
        
        """
        Produce a MetricsResponse over index monitoring data.        def get_app_report(self, patterns: Optional[List[str]] = None):
            raise NotImplementedError


        - Single 'time bucket' (now, truncated by precision) so it fits your generic UI.
        - Group by any of: 'category', 'env', 'index'
        - Aggregations over numeric fields like 'docs_count', 'store_size_bytes', etc.
        """
        groupby = groupby or []  # e.g. ["category"] or ["category","env"] or ["index"]
        agg_mapping = agg_mapping or {
            # sensible defaults for a dashboard
            "docs_count": ["sum"],
            "docs_deleted": ["sum"],
            "store_size_bytes": ["sum"],
            "pri_store_size_bytes": ["sum"],
        }
        report = self._get_metrics(patterns=None)
        rows: List[PragmaticIndexRow] = report.rows

        # Build flat dicts that match the metrics engine style
        flat_rows: List[Dict] = []
        for r in rows:
            flat_rows.append(
                {
                    "index": r.index,
                    "category": r.category,
                    "env": r.env,
                    "version": r.version,
                    "pri": r.pri,
                    "rep": r.rep,
                    "docs_count": r.docs_count,
                    "docs_deleted": r.docs_deleted,
                    "store_size_bytes": r.store_size_bytes,
                    "pri_store_size_bytes": r.pri_store_size_bytes,
                }
            )

        # Use a single bucket = "now" truncated to precision
        now = datetime.now(timezone.utc)
        bucket_time = truncate_datetime(now, precision)

        # Group by (bucket, *groupby)
        from collections import defaultdict

        grouped = defaultdict(list)
        for row in flat_rows:
            key = [bucket_time] + [row.get(f) for f in groupby]
            grouped[tuple(key)].append(row)

        # Aggregate
        def _values(rows_: List[Dict], field: str) -> List[float]:
            vals = [row.get(field) for row in rows_]
            return [float(v) for v in vals if isinstance(v, (int, float))]

        buckets: List[MetricsBucket] = []
        for key, grp in grouped.items():
            _, *group_vals = key
            group_fields = {f: v for f, v in zip(groupby, group_vals)}

            aggs: Dict[str, float | List[float]] = {}
            for field, ops in agg_mapping.items():
                vals = _values(grp, field)
                if not vals:
                    continue
                for op in ops:
                    if op == "sum":
                        aggs[f"{field}_sum"] = float(sum(vals))
                    elif op == "min":
                        aggs[f"{field}_min"] = float(min(vals))
                    elif op == "max":
                        aggs[f"{field}_max"] = float(max(vals))
                    elif op == "mean":
                        aggs[f"{field}_mean"] = float(sum(vals) / len(vals))
                    elif op == "values":
                        aggs[f"{field}_values"] = vals
                    else:
                        raise ValueError(f"Unsupported aggregation op: {op}")

            # timestamp string in UTC ISO, no microseconds
            ts = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            buckets.append(MetricsBucket(timestamp=ts, group=group_fields, aggregations=aggs))

        return MetricsResponse(precision=precision, buckets=buckets)

    
    def _get_metrics(
        self,
        patterns: Optional[List[str]] = None,
    ) -> PragmaticIndicesReport:
        """
        Build a report grouped by inferred index category.

        Args:
            patterns: Optional list of index patterns (e.g., ["fred-*","kf-*"]).
                      If None, uses "_all".
        """
        idx_selector = ",".join(patterns) if patterns else "_all"

        # 1) Stats (docs + sizes, bytes-accurate)
        stats = self.client.indices.stats(
            index=idx_selector, metric=["docs", "store"]
        )
        indices_stats: Dict[str, dict] = stats.get("indices", {}) or {}
        index_names = sorted(indices_stats.keys())

        # 2) Settings (pri/rep) in one call
        try:
            settings = self.client.indices.get_settings(index=idx_selector)
        except Exception as e:
            logger.warning("get_settings failed for %r: %s", idx_selector, e)
            settings = {}

        rows: List[PragmaticIndexRow] = []
        for idx in index_names:
            s = indices_stats.get(idx, {})
            total_docs = (s.get("total") or {}).get("docs") or {}
            total_store = (s.get("total") or {}).get("store") or {}
            prim_store = (s.get("primaries") or {}).get("store") or {}

            docs_count = int(total_docs.get("count", 0) or 0)
            docs_deleted = int(total_docs.get("deleted", 0) or 0)
            store_bytes = int(total_store.get("size_in_bytes", 0) or 0)
            pri_store_bytes = int(prim_store.get("size_in_bytes", 0) or 0)

            # derive pri/rep + category/env/version
            s_idx = (settings.get(idx) or {}).get("settings", {})
            s_index = s_idx.get("index", {}) if isinstance(s_idx, dict) else {}
            pri = s_index.get("number_of_shards")
            rep = s_index.get("number_of_replicas")

            pri_i = None
            rep_i = None
            try:
                if isinstance(pri, (int, str)):
                    pri_i = int(pri)
            except Exception:
                pass
            try:
                if isinstance(rep, (int, str)):
                    rep_i = int(rep)
            except Exception:
                pass

            category, env, ver = _categorize_index(idx)

            row = PragmaticIndexRow(
                index=idx,
                category=category,
                env=env,
                version=ver,
                pri=pri_i,
                rep=rep_i,
                docs_count=docs_count,
                docs_deleted=docs_deleted,
                store_size_bytes=store_bytes,
                pri_store_size_bytes=pri_store_bytes,
            )
            rows.append(row)

        # group by category
        from collections import defaultdict

        by_cat: Dict[str, List[PragmaticIndexRow]] = defaultdict(list)
        for r in rows:
            by_cat[r.category].append(r)

        categories: Dict[str, CategoryTotals] = {
            cat: _sum_totals(rs) for cat, rs in by_cat.items()
        }
        totals = _sum_totals(rows)

        return PragmaticIndicesReport(categories=categories, totals=totals, rows=rows)

    