# Copyright Thales 2026
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

"""
Bounded, cursor-paged reader over ``session_history`` for evaluation capture.

Why this module exists (separate from the conversational store):
- the conversational store (``get`` / ``list_sessions``) is per-session, per-user.
  Capture needs a *transversal* read: all conversations of one managed agent in one
  team over a period, across all users — a different access pattern.
- it is deliberately isolated and host-agnostic so the HTTP endpoint that exposes it
  can be mounted on either fred-agents or the control-plane without rewrite.

Bounding rules (volume + RGPD), enforced here so no caller can "dump everything":
- ``team_id`` + ``agent_instance_id`` + period are mandatory; the period is capped
  (``MAX_PERIOD_DAYS``).
- keyset cursor + hard page limit (``DEFAULT_PAGE_LIMIT`` / ``MAX_PAGE_LIMIT``) so a
  large history is streamed page by page, never loaded whole in RAM.
- only ``user`` / ``assistant`` roles, projected to the minimal fields needed.

Authorization (who may read which team's history) is NOT done here — it belongs to
the HTTP layer that mounts this reader.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Sequence

from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_core.history.history_models import SessionHistoryRow
from fred_core.history.history_schema import Role
from fred_core.sql.async_session import make_session_factory, use_session

MAX_PERIOD_DAYS = 90
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 1000

_DEFAULT_ROLES: tuple[str, ...] = (Role.user.value, Role.assistant.value)


class CapturedMessage(BaseModel):
    """One projected history message — the minimal capture contract."""

    session_id: str
    user_id: str
    exchange_id: str | None
    role: str
    content: str
    timestamp: datetime


class CapturePage(BaseModel):
    """One page of captured messages plus an opaque cursor for the next page."""

    messages: list[CapturedMessage]
    next_cursor: str | None = None


def _encode_cursor(ts: datetime, session_id: str, rank: int) -> str:
    raw = f"{ts.isoformat()}|{session_id}|{rank}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str, int]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, session_id, rank_str = raw.rsplit("|", 2)
    return datetime.fromisoformat(ts_str), session_id, int(rank_str)


def _extract_text(parts_json: object) -> str:
    """Join the text of all ``text`` parts; ignore non-text parts (tool calls…)."""
    if not isinstance(parts_json, list):
        return ""
    texts = [
        part["text"]
        for part in parts_json
        if isinstance(part, dict) and part.get("type") == "text" and "text" in part
    ]
    return "\n".join(texts)


class HistoryCaptureReader:
    """Streams ``session_history`` filtered by team + agent + period, page by page.

    Pages are keyset-ordered by ``(timestamp, session_id, rank)`` so each call reads
    at most ``limit`` rows — a large history never inflates memory or the response.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def fetch_page(
        self,
        *,
        team_id: str,
        agent_instance_id: str,
        period_from: datetime,
        period_to: datetime,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        roles: Sequence[str] = _DEFAULT_ROLES,
    ) -> CapturePage:
        if period_to < period_from:
            raise ValueError("period_to must be >= period_from")
        if period_to - period_from > timedelta(days=MAX_PERIOD_DAYS):
            raise ValueError(f"period exceeds the {MAX_PERIOD_DAYS}-day cap")
        limit = max(1, min(limit, MAX_PAGE_LIMIT))

        conditions = [
            SessionHistoryRow.team_id == team_id,
            SessionHistoryRow.agent_instance_id == agent_instance_id,
            SessionHistoryRow.role.in_(list(roles)),
            SessionHistoryRow.timestamp >= period_from,
            SessionHistoryRow.timestamp <= period_to,
        ]

        if cursor is not None:
            c_ts, c_session, c_rank = _decode_cursor(cursor)
            # Keyset: rows strictly after (timestamp, session_id, rank).
            conditions.append(
                or_(
                    SessionHistoryRow.timestamp > c_ts,
                    and_(
                        SessionHistoryRow.timestamp == c_ts,
                        SessionHistoryRow.session_id > c_session,
                    ),
                    and_(
                        SessionHistoryRow.timestamp == c_ts,
                        SessionHistoryRow.session_id == c_session,
                        SessionHistoryRow.rank > c_rank,
                    ),
                )
            )

        # Fetch one extra row to know whether a further page exists.
        query = (
            select(SessionHistoryRow)
            .where(and_(*conditions))
            .order_by(
                SessionHistoryRow.timestamp.asc(),
                SessionHistoryRow.session_id.asc(),
                SessionHistoryRow.rank.asc(),
            )
            .limit(limit + 1)
        )

        async with use_session(self._sessions) as s:
            rows = (await s.execute(query)).scalars().all()

        has_more = len(rows) > limit
        page_rows = rows[:limit]

        messages = [
            CapturedMessage(
                session_id=row.session_id,
                user_id=row.user_id,
                exchange_id=row.exchange_id,
                role=row.role,
                content=_extract_text(row.parts_json),
                timestamp=row.timestamp,
            )
            for row in page_rows
        ]

        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_cursor(last.timestamp, last.session_id, last.rank)

        return CapturePage(messages=messages, next_cursor=next_cursor)
