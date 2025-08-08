# app/core/session/stores/duckdb_session_storage.py

from datetime import timezone
import logging
import json
from typing import List, Dict
from dateutil.parser import isoparse

from pydantic import ValidationError

from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.chatbot.chat_schema import ChatMessagePayload
from app.core.session.stores.base_history_store import BaseHistoryStore
from app.core.session.stores.utils import flatten_message, truncate_datetime
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)


class DuckdbHistoryStore(BaseHistoryStore):
    def __init__(self, db_path):
        self.store = DuckDBTableStore(prefix="history_", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT,
                    user_id TEXT,
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

    def save(self, session_id: str, messages: List[ChatMessagePayload], user_id: str) -> None:
        with self.store._connect() as conn:
            for msg in messages:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO messages (
                        session_id, user_id, rank, timestamp, type, sender,
                        exchange_id, content, metadata_json, subtype
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        user_id,
                        msg.rank,
                        msg.timestamp,
                        msg.type,
                        msg.sender,
                        msg.exchange_id,
                        msg.content,
                        json.dumps(msg.metadata or {}),
                        msg.subtype,
                    )
                )

    def get(self, session_id: str) -> List[ChatMessagePayload]:
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, rank, timestamp, type, sender, exchange_id, content, metadata_json, subtype
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
                    user_id=row[0],
                    rank=row[1],
                    timestamp=row[2],
                    type=row[3],
                    sender=row[4],
                    exchange_id=row[5],
                    content=row[6],
                    metadata=json.loads(row[7]) if row[7] else {},
                    subtype=row[8],
                    session_id=session_id,
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
                SELECT session_id, user_id, rank, timestamp, type, sender, exchange_id, content, metadata_json, subtype
                FROM messages
                ORDER BY timestamp
                """
            ).fetchall()

        for row in rows:
            msg = ChatMessagePayload(
                session_id=row[0],
                user_id=row[1],
                rank=row[2],
                timestamp=row[3],
                type=row[4],
                sender=row[5],
                exchange_id=row[6],
                content=row[7],
                metadata=json.loads(row[8]) if row[8] else {},
                subtype=row[9],
            )
            if msg.type == "human":
                continue

            try:
                msg_dt = isoparse(msg.timestamp)
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.warning(f"[⚠️ Invalid timestamp] msg_id={msg.exchange_id} timestamp={msg.timestamp} error={e}")
                continue
            if not (start_dt <= msg_dt <= end_dt):
                continue

            flat = flatten_message(msg)
            bucket_time = truncate_datetime(msg_dt, precision)
            flat["timestamp"] = bucket_time.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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
