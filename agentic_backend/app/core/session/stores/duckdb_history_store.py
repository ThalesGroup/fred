# app/core/session/stores/duckdb_session_storage.py

from datetime import datetime, timezone
import logging
import json
from typing import Any, List, Dict

from pydantic import ValidationError

from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.chatbot.chat_schema import ChatMessagePayload, ChatMessageMetadata, MessageType
from app.core.session.stores.base_history_store import BaseHistoryStore
from app.core.session.stores.utils import flatten_message, truncate_datetime
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)


def _to_iso_utc(ts: datetime | str) -> str:
    """Normalize to ISO-8601 in UTC with 'Z' (DuckDB column is TEXT)."""
    if isinstance(ts, str):
        return ts
    dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _enum_val(x):
    """Return enum.value or the original if not an enum/None."""
    return getattr(x, "value", x)

def _as_metadata(v: Any) -> ChatMessageMetadata:
    if isinstance(v, ChatMessageMetadata):
        return v
    if isinstance(v, dict):
        try:
            return ChatMessageMetadata.model_validate(v)
        except ValidationError:
            # keep unknown keys in extras, don’t crash
            return ChatMessageMetadata(extras=v)
        
    return ChatMessageMetadata()
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msgs_user_time ON messages(user_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msgs_session ON messages(session_id)")

    def save(
        self, session_id: str, messages: List[ChatMessagePayload], user_id: str
    ) -> None:
        with self.store._connect() as conn:
            for msg in messages:
                # Ensure JSON-friendly values in storage
                metadata_dict = (
                    msg.metadata.model_dump(mode="json")
                    if isinstance(msg.metadata, ChatMessageMetadata)
                    else (msg.metadata or {})
                )
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
                        _to_iso_utc(msg.timestamp),
                        _enum_val(msg.type),
                        _enum_val(msg.sender),
                        msg.exchange_id,
                        msg.content,
                        json.dumps(metadata_dict),
                        _enum_val(msg.subtype),
                    ),
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
                (session_id,),
            ).fetchall()

        out: List[ChatMessagePayload] = []
        for row in rows:
            try:
                out.append(
                    ChatMessagePayload(
                        user_id=row[0],
                        rank=row[1],
                        timestamp=row[2],              # Pydantic parses ISO string -> datetime
                        type=row[3],                    # Pydantic parses to MessageType
                        sender=row[4],
                        exchange_id=row[5],
                        content=row[6],
                        metadata=_as_metadata(json.loads(row[7]) if row[7] else {}),
                        subtype=row[8],
                        session_id=session_id,
                    )
                )
            except ValidationError as e:
                logger.error(f"Failed to parse ChatMessagePayload: {e}")
        return out

    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        # Push date filter down to SQL (timestamps are ISO strings)
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, user_id, rank, timestamp, type, sender, exchange_id, content, metadata_json, subtype
                FROM messages
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
                """,
                (start, end),
            ).fetchall()

        grouped: Dict[tuple, list] = {}

        for row in rows:
            try:
                msg = ChatMessagePayload(
                    session_id=row[0],
                    user_id=row[1],
                    rank=row[2],
                    timestamp=row[3],          # parsed to datetime by Pydantic
                    type=row[4],
                    sender=row[5],
                    exchange_id=row[6],
                    content=row[7],
                    metadata=_as_metadata(json.loads(row[8]) if row[8] else {}),
                    subtype=row[9],
                )
            except ValidationError as e:
                logger.warning(f"[metrics] Skipping invalid message: {e}")
                continue

            # Only aggregate assistant (AI) messages
            if msg.type is not MessageType.ai:
                continue

            # Use the already-parsed datetime
            msg_dt = msg.timestamp
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=timezone.utc)

            flat = flatten_message(msg)
            bucket_time = truncate_datetime(msg_dt, precision)
            flat["timestamp"] = (
                bucket_time.astimezone(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

            group_key = (flat["timestamp"], *(flat.get(g) for g in groupby))
            grouped.setdefault(group_key, []).append(flat)

        buckets = []
        for key, group in grouped.items():
            timestamp = key[0]
            group_values = {g: v for g, v in zip(groupby, key[1:])}

            # ✅ Strongly type this dict to what MetricsBucket expects
            aggs: Dict[str, float | List[float]] = {}

            for field, ops in agg_mapping.items():
                raw_values = [row.get(field) for row in group if row.get(field) is not None]

                # Coerce to floats and drop non-numerics to satisfy the type
                num_values: List[float] = []
                for v in raw_values:
                    try:
                        num_values.append(float(v))
                    except (TypeError, ValueError):
                        continue

                if not num_values:
                    continue

                for op in ops:
                    match op:
                        case "sum":
                            aggs[f"{field}_sum"] = float(sum(num_values))
                        case "min":
                            aggs[f"{field}_min"] = float(min(num_values))
                        case "max":
                            aggs[f"{field}_max"] = float(max(num_values))
                        case "mean":
                            aggs[f"{field}_mean"] = float(sum(num_values) / len(num_values))
                        case "values":
                            # ensure a List[float], not List[object]
                            aggs[f"{field}_values"] = list(num_values)
                        case _:
                            raise ValueError(f"Unsupported aggregation op: {op}")

            buckets.append(
                MetricsBucket(
                    timestamp=timestamp,
                    group=group_values,
                    aggregations=aggs,  # ✅ types now align
                )
            )
        return MetricsResponse(precision=precision, buckets=buckets)
