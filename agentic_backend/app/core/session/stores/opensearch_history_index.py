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
)
from app.core.session.stores.utils import flatten_message, truncate_datetime

logger = logging.getLogger(__name__)

# ==============================================================================
# MESSAGES_INDEX_MAPPING
# ==============================================================================
# This mapping defines the schema used for chat messages (ChatMessagePayload).
# We optimize for analytics (aggregation, filtering) and full-text search.
# ==============================================================================

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s"
    },
    "mappings": {
        "properties": {
            "exchange_id": {"type": "keyword"},
            "user_id": { "type": "keyword" },
            "type": {"type": "keyword"},
            "sender": {"type": "keyword"},
            "content": {"type": "text"},
            "timestamp": {"type": "date"},
            "session_id": {"type": "keyword"},
            "rank": {"type": "integer"},
            "subtype": {"type": "keyword"},
            "metadata": {
                "type": "object",
                "dynamic": True
            }
        }
    }
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

        self.index = index
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, body=MAPPING)
            logger.info(f"OpenSearch index '{index}' created with mapping.")
        else:
            logger.info(f"OpenSearch index '{index}' already exists.")


    def save(
        self, session_id: str, messages: List[ChatMessagePayload], user_id: str
    ) -> None:
        try:
            actions = [
                {
                    "index": {
                        "_index": self.index,
                        "_id": f"{session_id}-{message.rank or i}",
                    }
                }
                for i, message in enumerate(messages)
            ]
            bodies = [msg.model_dump() for msg in messages]
            bulk_body = [entry for pair in zip(actions, bodies) for entry in pair]

            # OpenSearch Bulk API
            self.client.bulk(body=bulk_body)
            self.client.indices.refresh(
                index=self.index
            )  # Necessary due to indexing delay for whoever wants to access the newly stored data (from save_messages).
            logger.info(f"Saved {len(messages)} messages for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save messages for session {session_id}: {e}")
            raise

    def get(
        self, session_id: str, 
    ) -> List[ChatMessagePayload]:
        try:
            query = {
                "query": {"term": {"session_id.keyword": {"value": session_id}}},
                "sort": [{"rank": {"order": "asc", "unmapped_type": "integer"}}],
                "size": 1000,
            }
            response = self.client.search(
                index=self.index, body=query, params={"size": 10000}
            )
            return [
                ChatMessagePayload(**hit["_source"]) for hit in response["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"Failed to retrieve messages for session {session_id}: {e}")
            return []

    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]]
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
                if msg.type != "ai":
                    continue
                flat = flatten_message(msg)
                flat["_datetime"] = isoparse(flat["timestamp"])
                flat["_bucket"] = truncate_datetime(flat["_datetime"], precision)
                flattened.append(flat)

            # 3. Group by (bucket_time, groupby fields)
            grouped = defaultdict(list)
            for row in flattened:
                group_key = tuple([row["_bucket"]] + [row.get(f) for f in groupby])
                grouped[group_key].append(row)

            # 4. Aggregate
            buckets = []
            logger.debug(f"[metrics] Running OpenSearch query on index '{self.index}' with range: {start} to {end}, precision={precision}")
            logger.debug(f"[metrics] Query body: {query}")
            logger.debug(f"[metrics] Found {len(hits)} hits between {start} and {end}")
            logger.debug(f"[metrics] Truncated into {len(grouped)} groups based on precision={precision}")
            
            for key, group in grouped.items():
                bucket_time = key[0]
                group_fields = {field: value for field, value in zip(groupby, key[1:])}
                aggs = {}

                for field, ops in agg_mapping.items():
                    values = [
                        row.get(field) for row in group if row.get(field) is not None
                    ]
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
                                aggs[field + "_values"] = values
                            case _:
                                raise ValueError(f"Unsupported aggregation op: {op}")

                timestamp = bucket_time.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                buckets.append(
                    MetricsBucket(
                        timestamp=timestamp,
                        group=group_fields,
                        aggregations=aggs,
                    )
                )

            return MetricsResponse(precision=precision, buckets=buckets)

        except Exception as e:
            logger.error(f"Failed to compute metrics: {e}")
            return MetricsResponse(precision=precision, buckets=[])
