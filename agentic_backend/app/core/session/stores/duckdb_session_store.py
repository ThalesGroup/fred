# app/core/session/stores/duckdb_session_storage.py

import logging
import json
from typing import List, Optional, Dict
from dateutil.parser import isoparse

from pydantic import ValidationError

from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.session.session_manager import SessionSchema
from app.core.chatbot.chat_schema import ChatMessagePayload
from app.core.session.stores.base_session_store import BaseSessionStore
from app.core.session.stores.base_secure_resource_access import BaseSecuredResourceAccess
from app.core.session.stores.utils import flatten_message, truncate_datetime
from app.common.error import AuthorizationSentinel, SESSION_NOT_INITIALIZED
from app.common.utils import authorization_required
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)


class DuckdbSessionStore(BaseSessionStore, BaseSecuredResourceAccess):
    def __init__(self, db_path):
        self.store = DuckDBTableStore(prefix="", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT,
                    rank INTEGER,
                    timestamp TEXT,
                    type TEXT,
                    sender TEXT,
                    exchange_id TEXT,
                    content TEXT,
                    metadata_json TEXT,
                    subtype TEXT,
                    PRIMARY KEY (session_id, rank)
                )
            """)

    def save_session(self, session: SessionSchema) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, user_id, title, updated_at) VALUES (?, ?, ?, ?)",
                (session.id, session.user_id, session.title, session.updated_at)
            )

    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, title, updated_at FROM sessions WHERE user_id = ?",
                (user_id,)
            ).fetchall()
        return [SessionSchema(id=row[0], user_id=row[1], title=row[2], updated_at=row[3]) for row in rows]

    def get_authorized_user_id(self, session_id: str) -> str | AuthorizationSentinel:
        with self.store._connect() as conn:
            row = conn.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row[0] if row else SESSION_NOT_INITIALIZED

    @authorization_required
    def get_session(self, session_id: str, user_id: str) -> Optional[SessionSchema]:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, updated_at FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
        if not row:
            return None
        return SessionSchema(id=row[0], user_id=row[1], title=row[2], updated_at=row[3])

    @authorization_required
    def delete_session(self, session_id: str, user_id: str) -> bool:
        with self.store._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            rows = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return rows.rowcount > 0

    @authorization_required
    def save_messages(self, session_id: str, messages: List[ChatMessagePayload], user_id: str) -> None:
        with self.store._connect() as conn:
            for msg in messages:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO messages (
                        session_id, rank, timestamp, type, sender,
                        exchange_id, content, metadata_json, subtype
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        msg.rank,
                        msg.timestamp,
                        msg.type,
                        msg.sender,
                        msg.exchange_id,
                        msg.content,
                        json.dumps(msg.metadata or {}),
                        msg.subtype
                    )
                )

    @authorization_required
    def get_message_history(self, session_id: str, user_id: str) -> List[ChatMessagePayload]:
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT rank, timestamp, type, sender, exchange_id, content, metadata_json, subtype
                FROM messages
                WHERE session_id = ?
                ORDER BY rank ASC
                """,
                (session_id,)
            ).fetchall()

        messages = []
        for row in rows:
            try:
                messages.append(ChatMessagePayload(
                    exchange_id=row[4],
                    type=row[2],
                    sender=row[3],
                    content=row[5],
                    timestamp=row[1],
                    session_id=session_id,
                    rank=row[0],
                    metadata=json.loads(row[6]) if row[6] else {},
                    subtype=row[7]
                ))
            except ValidationError as e:
                logger.error(f"Failed to parse ChatMessagePayload: {e}")
        return messages

    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]]
    ) -> MetricsResponse:
        start_dt = isoparse(start)
        end_dt = isoparse(end)
        grouped = {}

        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, rank, timestamp, type, sender, exchange_id, content, metadata_json, subtype
                FROM messages
                ORDER BY timestamp
                """
            ).fetchall()

        for row in rows:
            msg = ChatMessagePayload(
                exchange_id=row[5],
                type=row[3],
                sender=row[4],
                content=row[6],
                timestamp=row[2],
                session_id=row[0],
                rank=row[1],
                metadata=json.loads(row[7]) if row[7] else {},
                subtype=row[8]
            )

            if msg.type == "human":
                continue

            msg_dt = isoparse(msg.timestamp)
            if not (start_dt <= msg_dt <= end_dt):
                continue

            flat = flatten_message(msg)
            bucket_time = truncate_datetime(msg_dt, precision)
            flat["timestamp"] = bucket_time.isoformat()

            group_key = (flat["timestamp"], *(flat.get(g) for g in groupby))
            grouped.setdefault(group_key, []).append(flat)

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
                            aggs[field + "_sum"] = sum(values)
                        case "min":
                            aggs[field + "_min"] = min(values)
                        case "max":
                            aggs[field + "_max"] = max(values)
                        case "mean":
                            aggs[field + "_mean"] = sum(values) / len(values)
                        case "values":
                            aggs[field + "_values"] = values
                        case _:
                            raise ValueError(f"Unsupported aggregation op: {op}")

            buckets.append(
                MetricsBucket(
                    timestamp=timestamp,
                    group=group_values,
                    aggregations=aggs
                )
            )

        return MetricsResponse(precision=precision, buckets=buckets)
