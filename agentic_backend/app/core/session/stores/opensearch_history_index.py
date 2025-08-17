# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from datetime import timezone
import logging
from typing import List, Dict
from dateutil.parser import isoparse
from collections import defaultdict
from statistics import mean
from opensearchpy import OpenSearch, RequestsHttpConnection
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.session.stores.base_history_store import BaseHistoryStore
from app.core.chatbot.chat_schema import (
    ChatMessagePayload,
    MessageType,
)
from app.core.session.stores.utils import flatten_message, truncate_datetime
from fred_core import ThreadSafeLRUCache

logger = logging.getLogger(__name__)

# ==============================================================================
# MESSAGES_INDEX_MAPPING
# ==============================================================================
# This mapping defines the schema used for chat messages (ChatMessagePayload).
# We optimize for analytics (aggregation, filtering) and full-text search.
# We now add a nested `blocks` field to persist the rich message structure.
# ==============================================================================

BLOCKS_MAPPING = {
    "type": "nested",
    "dynamic": False,
    "properties": {
        # Common discriminator
        "type": {"type": "keyword"},

        # TextBlock
        "text": {"type": "text"},

        # ToolResultBlock
        "name": {"type": "keyword"},
        "content": {"type": "text"},

        # ImageUrlBlock
        "url": {"type": "keyword"},
        "alt": {"type": "text"},
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
            "exchange_id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "type": {"type": "keyword"},
            "sender": {"type": "keyword"},
            "content": {"type": "text"},
            "blocks": BLOCKS_MAPPING,
            "timestamp": {"type": "date"},
            "session_id": {"type": "keyword"},
            "rank": {"type": "integer"},
            "subtype": {"type": "keyword"},
            # Metadata stays dynamic to allow growth (model, token_usage, sources…)
            "metadata": {"type": "object", "dynamic": True},
        }
    },
}


class OpensearchHistoryIndex(BaseHistoryStore):
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
        self._cache = ThreadSafeLRUCache[str, List[ChatMessagePayload]](max_size=1000)
        self.index = index

        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, body=MAPPING)
            logger.info(f"OpenSearch index '{index}' created with mapping.")
        else:
            logger.info(f"OpenSearch index '{index}' already exists.")
            # Safe additive mapping update: ensure `blocks` exists
            try:
                current = self.client.indices.get_mapping(index=index)
                props = (
                    current.get(index, {})
                    .get("mappings", {})
                    .get("properties", {})
                )
                if "blocks" not in props:
                    self.client.indices.put_mapping(
                        index=index,
                        body={"properties": {"blocks": BLOCKS_MAPPING}},
                    )
                    logger.info("Added 'blocks' mapping to existing index '%s'.", index)
            except Exception as e:
                logger.warning(
                    "Could not update mapping to add 'blocks' on index '%s': %s",
                    index,
                    e,
                )

    def save(
        self, session_id: str, messages: List[ChatMessagePayload], user_id: str
    ) -> None:
        try:
            for msg in messages:
                logger.info(
                    "[OpenSearch SAVE] session=%s sender=%s rank=%s subtype=%s content='%s...'",
                    session_id,
                    msg.sender,
                    msg.rank,
                    msg.subtype,
                    (msg.content or "")[:50],
                )
                if msg.rank is None:
                    logger.warning("[OpenSearch WARNING] Message missing rank: %s", msg)

            actions = [
                {
                    "index": {
                        "_index": self.index,
                        "_id": f"{session_id}-{message.rank or i}",
                    }
                }
                for i, message in enumerate(messages)
            ]
            # Use mode="json" + exclude_none to serialize datetimes and omit nulls;
            # Pydantic will include `blocks` if present (list) and already JSON-native.
            bodies = [msg.model_dump(mode="json", exclude_none=True) for msg in messages]
            bulk_body = [entry for pair in zip(actions, bodies) for entry in pair]

            # OpenSearch Bulk API
            self.client.bulk(body=bulk_body)

            # Append to the cached entry if any (simple concat; caller usually appends chronologically)
            existing = self._cache.get(session_id) or []
            updated = existing + messages
            self._cache.set(session_id, updated)

            logger.info("Saved %d messages for session %s", len(messages), session_id)
        except Exception as e:
            logger.error("Failed to save messages for session %s: %s", session_id, e)
            raise

    def get(
        self,
        session_id: str,
    ) -> List[ChatMessagePayload]:
        try:
            if cached := self._cache.get(session_id):
                logger.debug("[HistoryIndex] Cache hit for session '%s'", session_id)
                return cached

            query = {
                "query": {"term": {"session_id.keyword": {"value": session_id}}},
                "sort": [{"rank": {"order": "asc", "unmapped_type": "integer"}}],
                "size": 1000,
            }
            response = self.client.search(
                index=self.index, body=query, params={"size": 10000}
            )
            hits = response["hits"]["hits"]
            logger.info(
                "[OpenSearch GET] Loaded %d messages for session %s",
                len(hits),
                session_id,
            )
            for h in hits:
                src = h["_source"]
                logger.info(
                    "[OpenSearch GET] rank=%s sender=%s content='%s...'",
                    src.get("rank"),
                    src.get("sender"),
                    (src.get("content") or "")[:50],
                )

            return [ChatMessagePayload(**hit["_source"]) for hit in hits]
        except Exception as e:
            logger.error("Failed to retrieve messages for session %s: %s", session_id, e)
            return []

    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        try:
            # 1. Search messages in date range
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
                "sort": [{"rank": {"order": "asc", "unmapped_type": "integer"}}],
                "size": 10000,
            }

            response = self.client.search(index=self.index, body=query)
            hits = response["hits"]["hits"]

            # 2. Filter and flatten AI messages
            flattened = []
            for hit in hits:
                msg = ChatMessagePayload(**hit["_source"])
                # use equality, not identity
                if msg.type != MessageType.ai:
                    continue
                flat = flatten_message(msg)
                # msg.timestamp is already a datetime (Pydantic)
                flat["_datetime"] = msg.timestamp
                flat["_bucket"] = truncate_datetime(flat["_datetime"], precision)
                flattened.append(flat)

            # 3. Group by (bucket_time, groupby fields)
            grouped = defaultdict(list)
            for row in flattened:
                group_key = tuple([row["_bucket"]] + [row.get(f) for f in groupby])
                grouped[group_key].append(row)

            # 4. Aggregate
            buckets = []
            logger.debug(
                "[metrics] Running OpenSearch query on index '%s' with range: %s to %s, precision=%s",
                self.index, start, end, precision
            )
            logger.debug("[metrics] Found %d hits between %s and %s", len(hits), start, end)
            logger.debug("[metrics] Truncated into %d groups", len(grouped))

            for key, group in grouped.items():
                bucket_time = key[0]
                group_fields = {field: value for field, value in zip(groupby, key[1:])}
                aggs: Dict[str, float | List[float]] = {}

                for field, ops in agg_mapping.items():
                    values = [row.get(field) for row in group if row.get(field) is not None]
                    if not values:
                        continue
                    for op in ops:
                        match op:
                            case "sum":
                                aggs[field + "_sum"] = sum(values)
                            case "min":
                                aggs[field + "_min"] = min(values)
                            case "max":
                                aggs[field + "_max"] = max(values)
                            case "mean":
                                aggs[field + "_mean"] = mean(values)
                            case "values":
                                # store numeric series (as-is)
                                aggs[field + "_values"] = values  # type: ignore[assignment]
                            case _:
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
