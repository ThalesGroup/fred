# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import logging
from datetime import timezone
from statistics import mean
from typing import Dict, List, Optional

from opensearchpy import OpenSearch, RequestsHttpConnection

from app.common.utils import truncate_datetime
from app.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    Role,
)
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.session.stores.base_history_store import BaseHistoryStore
from fred_core import ThreadSafeLRUCache

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


class OpensearchHistoryIndex(BaseHistoryStore):
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

    def get_metrics(
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

            # 2) Filter to assistant/final for default analytics
            rows = []
            for h in hits:
                src = h["_source"]
                try:
                    msg = ChatMessage(**src)
                except Exception:
                    logger.warning("Failed to parse message from OpenSearch: %s", src)
                    continue
                if not (msg.role == Role.assistant and msg.channel == Channel.final):
                    continue
                flat = self._flatten_message_v2(msg)
                # time bucketing
                dt = msg.timestamp  # pydantic parsed
                flat["_datetime"] = dt
                flat["_bucket"] = truncate_datetime(dt, precision)
                rows.append(flat)

            # 3) Group by (_bucket, *groupby_fields)
            from collections import defaultdict as _dd

            grouped = _dd(list)
            for row in rows:
                key_vals = [row["_bucket"]]
                for f in groupby:
                    # support "metadata.model" style
                    key_vals.append(self._get_path(row, f))
                grouped[tuple(key_vals)].append(row)

            # 4) Aggregate
            buckets: List[MetricsBucket] = []
            for key, group in grouped.items():
                bucket_time = key[0]
                group_fields = {field: value for field, value in zip(groupby, key[1:])}
                aggs: Dict[str, float | List[float]] = {}
                for field, ops in agg_mapping.items():
                    vals = [self._get_path(r, field) for r in group]
                    vals = [v for v in vals if isinstance(v, (int, float))]
                    if not vals:
                        continue
                    for op in ops:
                        if op == "sum":
                            aggs[field + "_sum"] = float(sum(vals))
                        elif op == "min":
                            aggs[field + "_min"] = float(min(vals))
                        elif op == "max":
                            aggs[field + "_max"] = float(max(vals))
                        elif op == "mean":
                            aggs[field + "_mean"] = float(mean(vals))
                        elif op == "values":
                            aggs[field + "_values"] = list(vals)  # type: ignore[assignment]
                        else:
                            raise ValueError(f"Unsupported aggregation op: {op}")

                timestamp = (
                    bucket_time.astimezone(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                buckets.append(
                    MetricsBucket(
                        timestamp=timestamp,
                        group=group_fields,
                        aggregations=aggs,
                    )
                )

            return MetricsResponse(precision=precision, buckets=buckets)

        except Exception as e:
            logger.error("Failed to compute metrics: %s", e)
            return MetricsResponse(precision=precision, buckets=[])

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
