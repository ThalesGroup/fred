# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional

from fred_core.sql import AsyncBaseSqlStore, json_for_engine
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.common.utils import truncate_datetime
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    ChatTokenUsage,
    MessagePart,
    Role,
)
from agentic_backend.core.chatbot.metric_structures import (
    MetricsBucket,
    MetricsResponse,
)
from agentic_backend.core.monitoring.base_history_store import BaseHistoryStore

logger = logging.getLogger(__name__)

MESSAGE_PARTS_ADAPTER = TypeAdapter(List[MessagePart])


def _normalize_ts(ts: datetime | str) -> datetime:
    """Ensure a timezone-aware datetime in UTC for storage."""
    if isinstance(ts, str):
        try:
            ts_str = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
        except Exception:
            logger.warning("[HISTORY][PG] Failed to parse timestamp '%s'", ts)
            dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    else:
        dt = ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_md(v: Any) -> ChatMetadata:
    if isinstance(v, ChatMetadata):
        return v
    if isinstance(v, dict):
        try:
            return ChatMetadata.model_validate(v)
        except ValidationError:
            return ChatMetadata(extras=v)  # preserve unknown keys
    return ChatMetadata()


class PostgresHistoryStore(BaseHistoryStore):
    """
    v2-native Postgres history store. Persists ChatMessage (role/channel/parts/metadata).
    """

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = "history_"):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        json_type = json_for_engine(self.store.engine)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("session_id", String, primary_key=True),
            Column("user_id", String, primary_key=True),
            Column("rank", Integer, primary_key=True),
            Column("timestamp", DateTime(timezone=True), nullable=False),
            Column("role", String, nullable=False),
            Column("channel", String, nullable=False),
            Column("exchange_id", String),
            Column("parts_json", json_type),
            Column("metadata_json", json_type),
            keep_existing=True,
        )

        async def _create():
            async with self.store.engine.begin() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(metadata.create_all)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[HISTORY][PG][ASYNC] Table ready: %s", self.table_name)

    # ------------------------------------------------------------------ io
    async def save(
        self, session_id: str, messages: List[ChatMessage], user_id: str
    ) -> None:
        async with self.store.begin() as conn:
            await self.save_with_conn(conn, session_id, messages, user_id)

    async def save_with_conn(
        self, conn, session_id: str, messages: List[ChatMessage], user_id: str
    ) -> None:
        """
        Same as save(), but reuses the provided AsyncConnection so callers can
        group history + session writes in one transaction.
        """
        for i, msg in enumerate(messages):
            parts_json = [
                p.model_dump(mode="json", exclude_none=True) for p in (msg.parts or [])
            ]
            metadata_json = (
                msg.metadata.model_dump(mode="json", exclude_none=True)
                if msg.metadata
                else {}
            )

            await self.store.upsert(
                conn,
                self.table,
                values={
                    "session_id": session_id,
                    "user_id": user_id,
                    "rank": msg.rank if msg.rank is not None else i,
                    "timestamp": _normalize_ts(msg.timestamp),
                    "role": msg.role.value if isinstance(msg.role, Role) else msg.role,
                    "channel": msg.channel.value
                    if isinstance(msg.channel, Channel)
                    else msg.channel,
                    "exchange_id": msg.exchange_id,
                    "parts_json": parts_json,
                    "metadata_json": metadata_json,
                },
                pk_cols=["session_id", "user_id", "rank"],
            )

    async def get(self, session_id: str) -> List[ChatMessage]:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(
                    self.table.c.user_id,
                    self.table.c.rank,
                    self.table.c.timestamp,
                    self.table.c.role,
                    self.table.c.channel,
                    self.table.c.exchange_id,
                    self.table.c.parts_json,
                    self.table.c.metadata_json,
                )
                .where(self.table.c.session_id == session_id)
                .order_by(self.table.c.rank.asc())
            )
            rows = result.fetchall()

        out: List[ChatMessage] = []
        for row in rows:
            try:
                parts_payload = row[6] or []
                parts: List[MessagePart] = MESSAGE_PARTS_ADAPTER.validate_python(
                    parts_payload
                )
                md = _safe_md(row[7] or {})
                out.append(
                    ChatMessage(
                        session_id=session_id,
                        rank=row[1],
                        timestamp=row[2],
                        role=row[3],
                        channel=row[4],
                        exchange_id=row[5],
                        parts=parts,
                        metadata=md,
                    )
                )
            except ValidationError as e:
                logger.error("[HISTORY][PG] Failed to parse ChatMessage: %s", e)
        return out

    # ------------------------------------------------------------------ metrics
    async def get_chatbot_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(
                    self.table.c.session_id,
                    self.table.c.user_id,
                    self.table.c.rank,
                    self.table.c.timestamp,
                    self.table.c.role,
                    self.table.c.channel,
                    self.table.c.exchange_id,
                    self.table.c.parts_json,
                    self.table.c.metadata_json,
                )
                .where(
                    self.table.c.timestamp >= start,
                    self.table.c.timestamp <= end,
                    self.table.c.user_id == user_id,
                )
                .order_by(self.table.c.timestamp.asc())
            )
            rows = result.fetchall()

        grouped: Dict[tuple, list] = {}
        for row in rows:
            try:
                parts_payload = row[7] or []
                parts: List[MessagePart] = MESSAGE_PARTS_ADAPTER.validate_python(
                    parts_payload
                )
                md = _safe_md(row[8] or {})
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
                logger.warning("[metrics][PG] Skipping invalid message: %s", e)
                continue

            if not (msg.role == Role.assistant and msg.channel == Channel.final):
                continue

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

            flat = self._flatten_message_v2(msg)
            flat["timestamp"] = bucket_iso

            key = (bucket_iso, *(flat.get(g) for g in groupby))
            grouped.setdefault(key, []).append(flat)

        buckets: List[MetricsBucket] = []
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
        TOKEN_ALIAS = {
            "input_tokens": "metadata.token_usage.input_tokens",
            "output_tokens": "metadata.token_usage.output_tokens",
            "total_tokens": "metadata.token_usage.total_tokens",
        }
        if path in TOKEN_ALIAS:
            path = TOKEN_ALIAS[path]
        return d.get(path)
