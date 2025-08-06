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

import logging
from typing import List, Dict
from dateutil.parser import isoparse
from collections import defaultdict
from statistics import mean
from opensearchpy import OpenSearch, RequestsHttpConnection
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.session.stores.base_session_store import BaseSessionStore
from app.core.session.stores.base_secure_resource_access import (
    BaseSecuredResourceAccess,
)
from app.core.session.session_manager import SessionSchema
from app.core.chatbot.chat_schema import (
    ChatMessagePayload,
)
from app.core.session.stores.utils import flatten_message, truncate_datetime
from app.common.utils import authorization_required
from app.common.error import AuthorizationSentinel, SESSION_NOT_INITIALIZED

logger = logging.getLogger(__name__)


class OpensearchSessionStore(BaseSessionStore, BaseSecuredResourceAccess):
    def __init__(
        self,
        host: str,
        sessions_index: str,
        history_index: str,
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

        self.sessions_index = sessions_index
        self.history_index = history_index

        for index in [sessions_index, history_index]:
            if not self.client.indices.exists(index=index):
                self.client.indices.create(index=index)
                logger.info(f"Opensearch index '{index}' created.")
            else:
                logger.debug(f"Opensearch index '{index}' already exists.")

    def get_authorized_user_id(self, session_id: str) -> str | AuthorizationSentinel:
        try:
            session = self.client.get(index=self.sessions_index, id=session_id)
            return session["_source"].get("user_id")
        except Exception as e:
            logger.warning(f"Could not get user_id for session {session_id}: {e}")
            return SESSION_NOT_INITIALIZED

    def save_session(self, session: SessionSchema) -> None:
        try:
            session_dict = session.model_dump()
            self.client.index(
                index=self.sessions_index, id=session.id, body=session_dict
            )
            logger.debug(f"Session {session.id} saved for user {session.user_id}")
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            raise

    @authorization_required
    def get_session(self, session_id: str, user_id: str) -> SessionSchema | None:
        try:
            response = self.client.get(index=self.sessions_index, id=session_id)
            session_data = response["_source"]
            return SessionSchema(**session_data)
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    @authorization_required
    def delete_session(self, session_id: str, user_id: str) -> bool:
        try:
            self.client.delete(index=self.sessions_index, id=session_id)
            query = {"query": {"term": {"session_id.keyword": {"value": session_id}}}}
            self.client.delete_by_query(index=self.history_index, body=query)
            logger.info(f"Deleted session {session_id} and its messages")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        try:
            query = {"query": {"term": {"user_id.keyword": {"value": user_id}}}}
            response = self.client.search(
                params={"size": 10000}, index=self.sessions_index, body=query
            )
            sessions = [
                SessionSchema(**hit["_source"]) for hit in response["hits"]["hits"]
            ]
            logger.debug(f"Retrieved {len(sessions)} sessions for user {user_id}")
            return sessions
        except Exception as e:
            logger.error(f"Failed to fetch sessions for user {user_id}: {e}")
            return []

    @authorization_required
    def save_messages(
        self, session_id: str, messages: List[ChatMessagePayload], user_id: str
    ) -> None:
        try:
            actions = [
                {
                    "index": {
                        "_index": self.history_index,
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
                index=self.history_index
            )  # Necessary due to indexing delay for whoever wants to access the newly stored data (from save_messages).
            logger.info(f"Saved {len(messages)} messages for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save messages for session {session_id}: {e}")
            raise

    @authorization_required
    def get_message_history(
        self, session_id: str, user_id: str
    ) -> List[ChatMessagePayload]:
        try:
            query = {
                "query": {"term": {"session_id.keyword": {"value": session_id}}},
                "sort": [{"rank": {"order": "asc", "unmapped_type": "integer"}}],
                "size": 1000,
            }
            response = self.client.search(
                index=self.history_index, body=query, params={"size": 10000}
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
    ) -> List[MetricsResponse]:
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

            response = self.client.search(index=self.history_index, body=query)
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

                buckets.append(
                    MetricsBucket(
                        timestamp=bucket_time
                        if isinstance(bucket_time, str)
                        else bucket_time.isoformat(),
                        group=group_fields,
                        aggregations=aggs,
                    )
                )

            return [MetricsResponse(precision=precision, buckets=buckets)]

        except Exception as e:
            logger.error(f"Failed to compute metrics: {e}")
            return [MetricsResponse(precision=precision, buckets=[])]
