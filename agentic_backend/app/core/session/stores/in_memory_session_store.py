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
from typing import Dict, List
from dateutil.parser import isoparse
from collections import defaultdict
from statistics import mean

from app.core.session.stores.abstract_session_backend import AbstractSessionStorage
from app.core.session.stores.abstract_user_authentication_backend import (
    AbstractSecuredResourceAccess,
)
from app.core.session.session_manager import SessionSchema
from app.core.chatbot.chat_schema import ChatMessagePayload, MetricsBucket, MetricsResponse
from app.core.session.stores.utils import flatten_message, truncate_datetime
from app.common.error import AuthorizationSentinel, SESSION_NOT_INITIALIZED
from app.common.utils import authorization_required

logger = logging.getLogger(__name__)


class InMemorySessionStorage(AbstractSessionStorage, AbstractSecuredResourceAccess):
    def __init__(self):
        self.sessions: Dict[str, SessionSchema] = {}
        self.history: Dict[str, List[ChatMessagePayload]] = {}

    def get_authorized_user_id(
        self, session_id: str
    ) -> str | AuthorizationSentinel:
        session = self.sessions.get(session_id)
        if session is None:
            return SESSION_NOT_INITIALIZED
        return session.user_id

    def save_session(self, session: SessionSchema) -> None:
        self.sessions[session.id] = session

    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        logger.debug(f"Retrieving sessions for user: {user_id}")
        user_sessions = (
            session for session in self.sessions.values() if session.user_id == user_id
        )
        session_ids = []
        for session in user_sessions:
            session_ids.append(session.id)
        logger.debug(
            f"Retrieved {len(session_ids)} session{'s' if len(session_ids) > 1 else ''} for {user_id}"
        )
        return [s for s in self.sessions.values() if s.user_id == user_id]

    @authorization_required
    def get_session(self, session_id: str, user_id: str) -> SessionSchema | None:
        if session_id not in self.sessions:
            return None
        return self.sessions[session_id]

    @authorization_required
    def delete_session(self, session_id: str, user_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.history.pop(session_id, None)
            return True
        return False

    @authorization_required
    def save_messages(
        self, session_id: str, messages: List[ChatMessagePayload], user_id: str
    ) -> None:
        if session_id not in self.history:
            self.history[session_id] = []
        self.history[session_id].extend(messages)
        logger.info(f"Saved {len(messages)} messages to session {session_id}")

    @authorization_required
    def get_message_history(
        self, session_id: str, user_id: str
    ) -> List[ChatMessagePayload]:
        history = self.history.get(session_id, [])
        return sorted(history, key=lambda m: m.rank if m.rank is not None else 0)

    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, str],
    ) -> MetricsResponse:
        start_dt = isoparse(start)
        end_dt = isoparse(end)

        grouped = defaultdict(list)

        for session_messages in self.history.values():
            for msg in session_messages:
                if msg.type == "human":
                    continue

                msg_dt = isoparse(msg.timestamp)
                if not (start_dt <= msg_dt <= end_dt):
                    continue

                flat = flatten_message(msg)
                bucket_time = truncate_datetime(msg_dt, precision)
                flat["timestamp"] = bucket_time.isoformat()

                group_key = (flat["timestamp"], *(flat.get(g) for g in groupby))
                grouped[group_key].append(flat)

        buckets = []
        for key, group in grouped.items():
            timestamp = key[0]
            group_values = {g: v for g, v in zip(groupby, key[1:])}
            aggs = {}

            for field, ops in agg_mapping.items():
                values = [row.get(field) for row in group if row.get(field) is not None]
                if not values:
                        continue
                for op in ops:
                    match op:
                        case "sum":
                            aggs[field+"_sum"] = sum(values)
                        case "min":
                            aggs[field+"_min"] = min(values)
                        case "max":
                            aggs[field+"_max"] = max(values)
                        case "mean":
                            aggs[field+"_mean"] = mean(values)
                        case "values":
                            aggs[field+"_values"] = values
                        case _:
                            raise ValueError(f"Unsupported aggregation op: {op}")

            buckets.append(MetricsBucket(timestamp=timestamp, group=group_values, aggregations=aggs))

        return MetricsResponse(precision=precision, buckets=buckets)



