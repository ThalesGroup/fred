# app/core/session/stores/duckdb_session_storage.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import TypeAdapter, ValidationError

from app.common.utils import truncate_datetime
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.chatbot.chat_schema import (
    ChatMessage,
    ChatMetadata,
    ChatTokenUsage,
    Role,
    Channel,
    MessagePart,
)
from app.core.monitoring.base_history_store import BaseHistoryStore
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)

# one part
MESSAGE_PART_ADAPTER = TypeAdapter(MessagePart)
# list of parts
MESSAGE_PARTS_ADAPTER = TypeAdapter(List[MessagePart])


def _to_iso_utc(ts: datetime | str) -> str:
    """Normalize to ISO-8601 in UTC with 'Z' (DuckDB column is TEXT)."""
    if isinstance(ts, str):
        return ts
    dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _safe_md(v: Any) -> ChatMetadata:
    if isinstance(v, ChatMetadata):
        return v
    if isinstance(v, dict):
        try:
            return ChatMetadata.model_validate(v)
        except ValidationError:
            return ChatMetadata(extras=v)  # keep unknown keys safely
    return ChatMetadata()


class DuckdbHistoryStore(BaseHistoryStore):
    """
    v2-native DuckDB history store. Persists ChatMessage (role/channel/parts/metadata).
    """

    def __init__(self, db_path: Path):
        self.store = DuckDBTableStore(prefix="history_", db_path=db_path)
        self._ensure_schema()

    # ------------------------------------------------------------------ schema
    def _ensure_schema(self) -> None:
        with self.store._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    session_id   TEXT,
                    user_id      TEXT,
                    rank         INTEGER,
                    timestamp    TEXT,       -- ISO-8601 Z
                    role         TEXT,       -- user|assistant|tool|system
                    channel      TEXT,       -- final|plan|thought|observation|tool_call|tool_result|error|system_note
                    exchange_id  TEXT,
                    parts_json   TEXT,       -- JSON list[MessagePart]
                    metadata_json TEXT,      -- JSON ChatMetadata
                    PRIMARY KEY (session_id, rank)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_msgs_user_time ON messages(user_id, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_msgs_session ON messages(session_id)"
            )

    # ------------------------------------------------------------------ io
    def save(self, session_id: str, messages: List[ChatMessage], user_id: str) -> None:
        with self.store._connect() as conn:
            for i, msg in enumerate(messages):
                parts_json = json.dumps(
                    [
                        p.model_dump(mode="json", exclude_none=True)
                        for p in (msg.parts or [])
                    ]
                )
                metadata_json = json.dumps(
                    msg.metadata.model_dump(mode="json", exclude_none=True)
                    if msg.metadata
                    else {}
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO messages (
                        session_id, user_id, rank, timestamp, role, channel,
                        exchange_id, parts_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        user_id,
                        msg.rank,
                        _to_iso_utc(msg.timestamp),
                        msg.role.value,
                        msg.channel.value,
                        msg.exchange_id,
                        parts_json,
                        metadata_json,
                    ),
                )

    def get(self, session_id: str) -> List[ChatMessage]:
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, rank, timestamp, role, channel, exchange_id,
                       parts_json, metadata_json
                FROM messages
                WHERE session_id = ?
                ORDER BY rank ASC
                """,
                (session_id,),
            ).fetchall()

        out: List[ChatMessage] = []
        for row in rows:
            try:
                parts_payload = json.loads(row[6]) if row[6] else []
                # Pydantic will validate each part against the discriminator "type"
                parts: List[MessagePart] = MESSAGE_PARTS_ADAPTER.validate_python(
                    parts_payload
                )

                md = _safe_md(json.loads(row[7]) if row[7] else {})
                out.append(
                    ChatMessage(
                        session_id=session_id,
                        rank=row[1],
                        timestamp=row[2],  # Pydantic parses ISO string to datetime
                        role=row[3],  # → Role enum
                        channel=row[4],  # → Channel enum
                        exchange_id=row[5],
                        parts=parts,
                        metadata=md,
                    )
                )
            except ValidationError as e:
                logger.error(f"[DuckDB] Failed to parse ChatMessage: {e}")
        return out

    # ------------------------------------------------------------------ metrics

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
        Aggregates over assistant/final messages. `groupby` supports flattened keys like:
          - 'metadata.model'
          - 'metadata.agent_name'
          - 'metadata.token_usage.total_tokens'
        """
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, user_id, rank, timestamp, role, channel,
                       exchange_id, parts_json, metadata_json
                FROM messages
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
                """,
                (start, end),
            ).fetchall()

        grouped: Dict[tuple, list] = {}
        for row in rows:
            try:
                parts_payload = json.loads(row[7]) if row[7] else []
                parts: List[MessagePart] = MESSAGE_PARTS_ADAPTER.validate_python(
                    parts_payload
                )
                md = _safe_md(json.loads(row[8]) if row[8] else {})
                msg = ChatMessage(
                    session_id=row[0],
                    rank=row[2],
                    timestamp=row[3],
                    role=row[4],
                    channel=row[5],
                    exchange_id=row[6],
                    parts=parts,
                    metadata=md,
                )
            except ValidationError as e:
                logger.warning(f"[metrics] Skipping invalid message: {e}")
                continue

            # Only aggregate assistant / final messages
            if not (msg.role == Role.assistant and msg.channel == Channel.final):
                continue

            # Bucket timestamp
            msg_dt = msg.timestamp
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=timezone.utc)
            bucket = truncate_datetime(msg_dt, precision)
            bucket_iso = (
                bucket.astimezone(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

            # Flatten for grouping/aggregation
            flat = self._flatten_message_v2(msg)
            flat["timestamp"] = bucket_iso

            key = (bucket_iso, *(flat.get(g) for g in groupby))
            grouped.setdefault(key, []).append(flat)

        # Aggregate
        buckets: List[MetricsBucket] = []
        from statistics import mean

        for key, group in grouped.items():
            timestamp = key[0]
            group_values = {g: v for g, v in zip(groupby, key[1:])}

            aggs: Dict[str, float | List[float]] = {}
            for field, ops in agg_mapping.items():
                vals = [self._get_path(group[i], field) for i in range(len(group))]
                vals = [v for v in vals if isinstance(v, (int, float))]
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
                        aggs[f"{field}_mean"] = float(mean(vals))
                    elif op == "values":
                        aggs[f"{field}_values"] = list(map(float, vals))  # type: ignore[assignment]
                    else:
                        raise ValueError(f"Unsupported aggregation op: {op}")

            buckets.append(
                MetricsBucket(
                    timestamp=timestamp, group=group_values, aggregations=aggs
                )
            )
        return MetricsResponse(precision=precision, buckets=buckets)

    # ------------------------------------------------------------------ helpers
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
            tu: Optional[ChatTokenUsage] = getattr(md, "token_usage", None)
            if tu:
                out["metadata.token_usage.input_tokens"] = tu.input_tokens
                out["metadata.token_usage.output_tokens"] = tu.output_tokens
                out["metadata.token_usage.total_tokens"] = tu.total_tokens
        return out

    @staticmethod
    def _get_path(d: Dict, path: str):
        # Keys are already flattened in _flatten_message_v2 (e.g., "metadata.model")
        return d.get(path)
