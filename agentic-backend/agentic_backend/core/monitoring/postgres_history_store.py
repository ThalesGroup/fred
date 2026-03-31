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

import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional

from fred_core.sql.async_session import make_session_factory, use_session
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
from agentic_backend.core.monitoring.history_models import SessionHistoryRow

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


def _parse_metrics_bound(ts: str, field: str) -> datetime:
    """Parse and validate a metrics time bound as timezone-aware UTC datetime."""
    try:
        parsed = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Invalid '{field}' timestamp: '{ts}'. Expected ISO 8601 datetime with timezone."
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            f"Invalid '{field}' timestamp: timezone information is required."
        )

    return parsed.astimezone(timezone.utc)


def _safe_md(v: Any) -> ChatMetadata:
    if isinstance(v, ChatMetadata):
        return v
    if isinstance(v, dict):
        try:
            return ChatMetadata.model_validate(v)
        except ValidationError:
            return ChatMetadata(extras=v)
    return ChatMetadata()


class PostgresHistoryStore(BaseHistoryStore):
    """
    v2-native Postgres history store. Persists ChatMessage (role/channel/parts/metadata).
    """

    def __init__(self, engine: AsyncEngine):
        self._sessions = make_session_factory(engine)

    # ------------------------------------------------------------------ io
    async def save(
        self,
        session_id: str,
        messages: List[ChatMessage],
        user_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        all_values = []
        for i, msg in enumerate(messages):
            all_values.append(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "rank": msg.rank if msg.rank is not None else i,
                    "timestamp": _normalize_ts(msg.timestamp),
                    "role": msg.role.value if isinstance(msg.role, Role) else msg.role,
                    "channel": msg.channel.value
                    if isinstance(msg.channel, Channel)
                    else msg.channel,
                    "exchange_id": msg.exchange_id,
                    "parts_json": [
                        p.model_dump(mode="json", exclude_none=True)
                        for p in (msg.parts or [])
                    ],
                    "metadata_json": msg.metadata.model_dump(
                        mode="json", exclude_none=True
                    )
                    if msg.metadata
                    else {},
                }
            )

        stmt = insert(SessionHistoryRow).values(all_values)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["session_id", "user_id", "rank"],
            set_={
                k: stmt.excluded[k]
                for k in ["parts_json", "metadata_json", "timestamp"]
            },
        )
        async with use_session(self._sessions, session) as s:
            await s.execute(upsert_stmt)

    async def get(
        self, session_id: str, session: AsyncSession | None = None
    ) -> List[ChatMessage]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(SessionHistoryRow)
                        .where(SessionHistoryRow.session_id == session_id)
                        .order_by(SessionHistoryRow.rank.asc())
                    )
                )
                .scalars()
                .all()
            )

        out: List[ChatMessage] = []
        for row in rows:
            try:
                parts_payload = row.parts_json or []
                parts: List[MessagePart] = MESSAGE_PARTS_ADAPTER.validate_python(
                    parts_payload
                )
                md = _safe_md(row.metadata_json or {})
                out.append(
                    ChatMessage(
                        session_id=session_id,
                        rank=row.rank,
                        timestamp=row.timestamp,
                        role=Role(row.role),
                        channel=Channel(row.channel),
                        exchange_id=row.exchange_id or "",
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
        session: AsyncSession | None = None,
    ) -> MetricsResponse:
        start_dt = _parse_metrics_bound(start, "start")
        end_dt = _parse_metrics_bound(end, "end")
        if end_dt < start_dt:
            raise ValueError("Invalid metrics window: 'end' must be >= 'start'.")

        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(SessionHistoryRow)
                        .where(
                            SessionHistoryRow.timestamp >= start_dt,
                            SessionHistoryRow.timestamp <= end_dt,
                            SessionHistoryRow.user_id == user_id,
                        )
                        .order_by(SessionHistoryRow.timestamp.asc())
                    )
                )
                .scalars()
                .all()
            )

        grouped: Dict[tuple, list] = {}
        for row in rows:
            try:
                parts_payload = row.parts_json or []
                parts: List[MessagePart] = MESSAGE_PARTS_ADAPTER.validate_python(
                    parts_payload
                )
                md = _safe_md(row.metadata_json or {})
                msg = ChatMessage(
                    session_id=row.session_id,
                    rank=row.rank,
                    timestamp=row.timestamp,
                    role=Role(row.role),
                    channel=Channel(row.channel),
                    exchange_id=row.exchange_id or "",
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
        out: Dict = {
            "role": msg.role,
            "channel": msg.channel,
            "session_id": msg.session_id,
            "exchange_id": msg.exchange_id,
            "rank": msg.rank,
            "metadata.model": None,
            "metadata.agent_id": None,
            "metadata.finish_reason": None,
            "metadata.token_usage.input_tokens": None,
            "metadata.token_usage.output_tokens": None,
            "metadata.token_usage.total_tokens": None,
        }
        md = msg.metadata or None
        if md:
            out["metadata.model"] = md.model
            out["metadata.agent_id"] = md.agent_id
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
