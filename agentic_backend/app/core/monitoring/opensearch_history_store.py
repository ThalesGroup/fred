# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional

from fred_core import ThreadSafeLRUCache
from fred_core.store.opensearch_mapping_validator import validate_index_mapping
from opensearchpy import OpenSearch, RequestsHttpConnection

from app.common.utils import truncate_datetime
from app.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    Role,
)
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.monitoring.base_history_store import BaseHistoryStore

logger = logging.getLogger(__name__)

# ==============================================================================
# Chat Protocol v2 OpenSearch Mapping
# ==============================================================================

PARTS_MAPPING = {
    "type": "nested",
    "dynamic": False,
    "properties": {
        "type": {"type": "keyword"},
        # TextPart
        "text": {"type": "text"},
        # CodePart
        "code": {"type": "text"},
        "language": {"type": "keyword"},
        # ImageUrlPart
        "url": {"type": "keyword"},
        "alt": {"type": "text"},
        # ToolCallPartx²
        "call_id": {"type": "keyword"},
        "name": {"type": "keyword"},
        # We stringify args in our messages anyway, but support text here
        "args": {"type": "text"},
        # ToolResultPart
        "ok": {"type": "boolean"},
        "latency_ms": {"type": "integer"},
        "content": {"type": "text"},
    },
}

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
    },
    "mappings": {
        "properties": {
            # Identity & ordering
            "session_id": {"type": "keyword"},
            "exchange_id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "rank": {"type": "integer"},
            "timestamp": {"type": "date"},
            # Chat v2 typing
            "role": {"type": "keyword"},  # user | assistant | tool | system
            "channel": {
                "type": "keyword"
            },  # final | plan | thought | observation | tool_call | tool_result | error | system_note
            # Rich content
            "parts": PARTS_MAPPING,
            # Metadata: keep lean, type the common fields, allow extension
            "metadata": {
                "type": "object",
                "dynamic": True,
                "properties": {
                    "model": {"type": "keyword"},
                    "agent_name": {"type": "keyword"},
                    "finish_reason": {"type": "keyword"},
                    "latency_ms": {"type": "integer"},
                    "token_usage": {
                        "type": "object",
                        "dynamic": False,
                        "properties": {
                            "input_tokens": {"type": "integer"},
                            "output_tokens": {"type": "integer"},
                            "total_tokens": {"type": "integer"},
                        },
                    },
                    # `sources` (VectorSearchHit[]) will be stored as dynamic objects;
                    # we don't pre-map it to avoid mapping bloat.
                },
            },
        }
    },
}


def _merge_unique_by_key(
    existing: List[ChatMessage], new: List[ChatMessage]
) -> List[ChatMessage]:
    bucket: dict[tuple[str, int], ChatMessage] = {
        (m.exchange_id, m.rank): m for m in existing
    }
    for m in new:
        k = (m.exchange_id, m.rank)
        if k not in bucket:
            bucket[k] = m
        else:
            old = bucket[k]
            take_new = (
                getattr(old, "channel", None) != Channel.final
                and m.channel == Channel.final
            ) or ((m.timestamp or "") > (old.timestamp or ""))
            if take_new:
                bucket[k] = m
    # keep session order by rank for readability
    return sorted(bucket.values(), key=lambda x: x.rank)


class OpensearchHistoryStore(BaseHistoryStore):
    """
    v2-native history store: persists ChatMessage (role/channel/parts/metadata).
    """

    def __init__(
        self,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        self._cache = ThreadSafeLRUCache[str, List[ChatMessage]](max_size=1000)
        self.index = index

        # Create or update index mapping
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, body=MAPPING)
            logger.info("OpenSearch index '%s' created with mapping.", index)
        else:
            logger.info("OpenSearch index '%s' already exists.", index)
            # Best-effort additive mapping update for 'parts' and typed metadata fields
            try:
                current = self.client.indices.get_mapping(index=index)
                props = current.get(index, {}).get("mappings", {}).get("properties", {})
                patch: Dict[str, dict] = {}
                if "parts" not in props:
                    patch["parts"] = PARTS_MAPPING
                # Ensure typed sub-fields exist in metadata
                meta_props = props.get("metadata", {}).get("properties", {})
                if "token_usage" not in meta_props:
                    patch.setdefault("metadata", {"type": "object", "properties": {}})
                    patch["metadata"]["properties"]["token_usage"] = MAPPING[
                        "mappings"
                    ]["properties"]["metadata"]["properties"]["token_usage"]
                if patch:
                    self.client.indices.put_mapping(
                        index=index, body={"properties": patch}
                    )
                    logger.info(
                        "Updated mapping for '%s' with: %s",
                        index,
                        ", ".join(patch.keys()),
                    )
            except Exception as e:
                logger.warning("Could not update mapping on index '%s': %s", index, e)

            # Validate existing mapping matches expected mapping
            validate_index_mapping(self.client, index, MAPPING)

    # ----------------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------------

    def save(self, session_id: str, messages: List[ChatMessage], user_id: str) -> None:
        try:
            actions = []
            bodies = []

            for i, msg in enumerate(messages):
                # Log a tiny preview for debugging
                preview = ""
                try:
                    # derive preview from first text part if present
                    for p in msg.parts or []:
                        if getattr(p, "type", None) == "text":
                            preview = (getattr(p, "text", "") or "")[:60]
                            break
                except Exception:
                    logger.exception("Failed to parse message from OpenSearch: %s", msg)
                    raise

                logger.debug(
                    "[OpenSearch SAVE] session=%s role=%s channel=%s rank=%s preview='%s'",
                    session_id,
                    msg.role,
                    msg.channel,
                    msg.rank,
                    preview,
                )

                doc_id = f"{session_id}-{msg.exchange_id}-{msg.rank or i}"
                actions.append({"index": {"_index": self.index, "_id": doc_id}})
                bodies.append(msg.model_dump(mode="json", exclude_none=True))

            bulk_body = [entry for pair in zip(actions, bodies) for entry in pair]
            if bulk_body:
                self.client.bulk(body=bulk_body)

            # Cache append
            existing = self._cache.get(session_id) or []
            updated = _merge_unique_by_key(existing, messages)
            self._cache.set(session_id, updated)

            logger.info("Saved %d messages for session %s", len(messages), session_id)
        except Exception as e:
            logger.error("Failed to save messages for session %s: %s", session_id, e)
            raise

    def get(self, session_id: str) -> List[ChatMessage]:
        try:
            if cached := self._cache.get(session_id):
                logger.debug("[HistoryIndex] Cache hit for session '%s'", session_id)
                return cached

            query = {
                "query": {"term": {"session_id": {"value": session_id}}},
                "sort": [{"rank": {"order": "asc", "unmapped_type": "integer"}}],
                "size": 10000,
            }

            response = self.client.search(index=self.index, body=query)
            hits = response.get("hits", {}).get("hits", [])
            logger.info(
                "[OpenSearch GET] Loaded %d messages for session %s",
                len(hits),
                session_id,
            )

            messages = [ChatMessage(**hit["_source"]) for hit in hits]
            self._cache.set(session_id, messages)
            return messages
        except Exception as e:
            logger.error(
                "Failed to retrieve messages for session %s: %s", session_id, e
            )
            return []

    # ----------------------------------------------------------------------
    # Metrics
    # ----------------------------------------------------------------------
    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------

    @staticmethod
    def _flatten_message_v2(msg: ChatMessage) -> Dict:
        """
        Produce a flat dict for metrics/groupby. Keep it small & stable.
        """
        out: Dict = {
            "role": msg.role,
            "channel": msg.channel,
            "session_id": msg.session_id,
            "exchange_id": msg.exchange_id,
            "rank": msg.rank,
            "metadata.model": None,
            "metadata.agent_name": None,
            "metadata.finish_reason": None,
            "metadata.token_usage.input_tokens": None,
            "metadata.token_usage.output_tokens": None,
            "metadata.token_usage.total_tokens": None,
        }
        md = msg.metadata or None
        if md:
            out["metadata.model"] = md.model
            out["metadata.agent_name"] = md.agent_name
            out["metadata.finish_reason"] = getattr(md, "finish_reason", None)
            tu = getattr(md, "token_usage", None)
            if tu:
                out["metadata.token_usage.input_tokens"] = tu.input_tokens
                out["metadata.token_usage.output_tokens"] = tu.output_tokens
                out["metadata.token_usage.total_tokens"] = tu.total_tokens
        return out

    @staticmethod
    def _get_path(d: Dict, path: str) -> Optional[float]:
        """
        Get "a.b.c" from a flat dict where keys may already be flattened with dots.
        """
        # Our _flatten_message_v2 already uses flattened keys like "metadata.model".
        return d.get(path)

    @staticmethod
    def _to_utc_iso(value: Any) -> Optional[str]:
        """
        Convert a datetime or ISO8601 string (with or without 'Z') to UTC ISO string.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            # try to parse common ISO variants
            try:
                s = str(value)
                # support trailing 'Z'
                if s.endswith("Z"):
                    s = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
            except Exception:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (
            dt.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def get_chatbot_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        """
        Aggregates over assistant/final messages by default (the most meaningful unit of answer),
        while supporting arbitrary 'groupby' fields (e.g., 'metadata.model', 'metadata.agent_name').
        """
        try:
            # -------- Verbosity knobs (raise/lower to your needs) --------
            LOG_LIMIT_HITS = 200
            LOG_LIMIT_PARSED = 200
            LOG_LIMIT_ROWS = 100
            LOG_LIMIT_GROUPS = 200
            LOG_LIMIT_AGG_VALUES = 200
            LOG_LIMIT_BUCKETS = 200

            # --- Normalize inputs (THIS FIXES YOUR CASE) ---
            # 1) Drop empty groupby tokens like '' (from query param groupby=)
            orig_groupby = list(groupby)
            groupby = [g for g in (groupby or []) if isinstance(g, str) and g.strip()]
            if orig_groupby != groupby:
                logger.debug(
                    "[Metrics] normalized groupby: %r -> %r", orig_groupby, groupby
                )

            # 2) Allow short aliases for token fields
            TOKEN_ALIAS = {
                "input_tokens": "metadata.token_usage.input_tokens",
                "output_tokens": "metadata.token_usage.output_tokens",
                "total_tokens": "metadata.token_usage.total_tokens",
            }
            # Build normalized agg_mapping while keeping a reverse map so output keys
            # remain the user-friendly names they asked for (e.g., 'total_tokens_sum')
            resolved_agg: Dict[str, List[str]] = {}
            alias_reverse: Dict[str, str] = {}
            for field, ops in (agg_mapping or {}).items():
                norm = TOKEN_ALIAS.get(field, field)
                resolved_agg.setdefault(norm, []).extend(ops)
                if norm != field:
                    alias_reverse[norm] = field  # for pretty output keys
            if resolved_agg != agg_mapping:
                logger.debug(
                    "[Metrics] normalized agg_mapping: %r -> %r",
                    agg_mapping,
                    resolved_agg,
                )

            logger.debug(
                "[Metrics] INPUTS start=%s end=%s precision=%s groupby=%s agg_mapping=%s user_id=%s",
                start,
                end,
                precision,
                groupby,
                agg_mapping,
                user_id,
            )

            # 1) Query by time range; do message-level filtering client-side
            query = {
                "query": {
                    "range": {
                        "timestamp": {
                            "gte": start,
                            "lte": end,
                            "format": "strict_date_optional_time",
                        }
                    }
                },
                "sort": [{"timestamp": {"order": "asc"}}],
                "size": 10000,
            }
            response = self.client.search(index=self.index, body=query)
            hits = response.get("hits", {}).get("hits", [])
            total_hits = len(hits)
            logger.debug(
                "[Metrics] RAW hits in range %s..%s: %d", start, end, total_hits
            )

            for i, h in enumerate(hits[:LOG_LIMIT_HITS]):
                src = h.get("_source", {})
                logger.debug(
                    "[Metrics] RAW[%d/%d] _id=%s ts=%r role=%r channel=%r",
                    i + 1,
                    total_hits,
                    h.get("_id"),
                    src.get("timestamp"),
                    src.get("role"),
                    src.get("channel"),
                )
            if total_hits > LOG_LIMIT_HITS:
                logger.debug(
                    "[Metrics] ... raw hits truncated at %d lines", LOG_LIMIT_HITS
                )

            # 2) Filter to assistant/final
            rows: List[Dict[str, Any]] = []
            parsed_count = 0
            filtered_count = 0
            parsed_printed = 0

            for h in hits:
                src = h["_source"]
                try:
                    msg = ChatMessage(**src)
                    parsed_count += 1
                    if parsed_printed < LOG_LIMIT_PARSED:
                        logger.debug(
                            "[Metrics] PARSED[%d] ts=%s role=%s channel=%s session=%s exch=%s rank=%s model=%r agent=%r",
                            parsed_count,
                            getattr(msg, "timestamp", None),
                            getattr(msg, "role", None),
                            getattr(msg, "channel", None),
                            getattr(msg, "session_id", None),
                            getattr(msg, "exchange_id", None),
                            getattr(msg, "rank", None),
                            getattr(getattr(msg, "metadata", None), "model", None),
                            getattr(getattr(msg, "metadata", None), "agent_name", None),
                        )
                        parsed_printed += 1
                except Exception:
                    logger.warning("Failed to parse message from OpenSearch: %s", src)
                    continue

                if not (msg.role == Role.assistant and msg.channel == Channel.final):
                    continue

                filtered_count += 1
                flat = self._flatten_message_v2(msg)
                dt = msg.timestamp
                flat["_datetime"] = dt
                flat["_bucket"] = truncate_datetime(dt, precision)
                rows.append(flat)

            logger.debug(
                "[Metrics] PARSE/FILTER summary: parsed_ok=%d assistant_final=%d",
                parsed_count,
                filtered_count,
            )

            for i, r in enumerate(rows[:LOG_LIMIT_ROWS]):
                logger.debug(
                    "[Metrics] ROW[%d/%d] datetime=%r (type=%s) bucket=%r (type=%s) model=%r agent=%r input_tokens=%r output_tokens=%r total_tokens=%r",
                    i + 1,
                    len(rows),
                    r.get("_datetime"),
                    type(r.get("_datetime")).__name__,
                    r.get("_bucket"),
                    type(r.get("_bucket")).__name__,
                    r.get("metadata.model"),
                    r.get("metadata.agent_name"),
                    r.get("metadata.token_usage.input_tokens"),
                    r.get("metadata.token_usage.output_tokens"),
                    r.get("metadata.token_usage.total_tokens"),
                )
            if len(rows) > LOG_LIMIT_ROWS:
                logger.debug(
                    "[Metrics] ... rows dump truncated at %d lines", LOG_LIMIT_ROWS
                )

            # 3) Group by (_bucket, *groupby_fields)
            from collections import defaultdict as _dd

            grouped: Dict[Any, List[Dict[str, Any]]] = _dd(list)
            for row in rows:
                key_vals = [row["_bucket"]]
                for f in groupby:
                    v = self._get_path(row, f)
                    logger.debug(
                        "[Metrics] _get_path path=%r -> %r (type=%s)",
                        f,
                        v,
                        type(v).__name__ if v is not None else "NoneType",
                    )
                    key_vals.append(v)
                grouped[tuple(key_vals)].append(row)

            logger.debug("[Metrics] GROUPS: total=%d", len(grouped))
            for i, (key, group) in enumerate(list(grouped.items())[:LOG_LIMIT_GROUPS]):
                bucket_key = key[0]
                group_fields = {field: value for field, value in zip(groupby, key[1:])}
                logger.debug(
                    "[Metrics] GROUP[%d/%d] bucket=%r (type=%s) fields=%r size=%d",
                    i + 1,
                    len(grouped),
                    bucket_key,
                    type(bucket_key).__name__,
                    group_fields,
                    len(group),
                )
            if len(grouped) > LOG_LIMIT_GROUPS:
                logger.debug(
                    "[Metrics] ... groups dump truncated at %d lines", LOG_LIMIT_GROUPS
                )

            # 4) Aggregate
            buckets: List[MetricsBucket] = []
            for key, group in grouped.items():
                bucket_time = key[0]
                group_fields = {field: value for field, value in zip(groupby, key[1:])}
                aggs: Dict[str, float | List[float]] = {}

                for field_norm, ops in resolved_agg.items():
                    vals_all = [self._get_path(r, field_norm) for r in group]
                    logger.debug(
                        "[Metrics] SERIES bucket=%r field=%s raw=%r",
                        bucket_time,
                        field_norm,
                        vals_all[:LOG_LIMIT_AGG_VALUES]
                        if len(vals_all) > LOG_LIMIT_AGG_VALUES
                        else vals_all,
                    )
                    vals = [v for v in vals_all if isinstance(v, (int, float))]
                    if not vals:
                        logger.debug(
                            "[Metrics] SERIES bucket=%r field=%s -> no numeric values",
                            bucket_time,
                            field_norm,
                        )
                        continue

                    # pretty base name for output keys: keep user's alias if any
                    out_base = alias_reverse.get(field_norm, field_norm)

                    for op in ops:
                        if op == "sum":
                            aggs[out_base + "_sum"] = float(sum(vals))
                        elif op == "min":
                            aggs[out_base + "_min"] = float(min(vals))
                        elif op == "max":
                            aggs[out_base + "_max"] = float(max(vals))
                        elif op == "mean":
                            aggs[out_base + "_mean"] = float(mean(vals))
                        elif op == "values":
                            aggs[out_base + "_values"] = list(vals)  # type: ignore[assignment]
                        else:
                            raise ValueError(f"Unsupported aggregation op: {op}")

                        if len(vals) <= LOG_LIMIT_AGG_VALUES:
                            logger.debug(
                                "[Metrics] AGG bucket=%r field=%s(op=%s) values=%r -> %r",
                                bucket_time,
                                out_base,
                                op,
                                vals,
                                aggs.get(out_base + f"_{op}"),
                            )
                        else:
                            logger.debug(
                                "[Metrics] AGG bucket=%r field=%s(op=%s) values=(%d nums, truncated) -> %r",
                                bucket_time,
                                out_base,
                                op,
                                len(vals),
                                aggs.get(out_base + f"_{op}"),
                            )

                # tolerate datetime or string buckets
                timestamp = self._to_utc_iso(bucket_time)
                if timestamp is None:
                    logger.debug(
                        "[Metrics] SKIP bucket: non-datetime/parseable key=%r (type=%s)",
                        bucket_time,
                        type(bucket_time).__name__,
                    )
                    continue

                logger.debug(
                    "[Metrics] BUCKET timestamp normalization: key=%r (type=%s) -> iso=%s",
                    bucket_time,
                    type(bucket_time).__name__,
                    timestamp,
                )

                buckets.append(
                    MetricsBucket(
                        timestamp=timestamp,
                        group=group_fields,
                        aggregations=aggs,
                    )
                )

            logger.debug("[Metrics] RESULT buckets=%d", len(buckets))
            for i, b in enumerate(buckets[:LOG_LIMIT_BUCKETS]):
                logger.debug(
                    "[Metrics] RESULT[%d/%d] ts=%s group=%r aggs=%r",
                    i + 1,
                    len(buckets),
                    b.timestamp,
                    b.group,
                    b.aggregations,
                )
            if len(buckets) > LOG_LIMIT_BUCKETS:
                logger.debug(
                    "[Metrics] ... result buckets dump truncated at %d lines",
                    LOG_LIMIT_BUCKETS,
                )

            return MetricsResponse(precision=precision, buckets=buckets)

        except Exception as e:
            logger.error("Failed to compute metrics: %s", e)
            return MetricsResponse(precision=precision, buckets=[])
