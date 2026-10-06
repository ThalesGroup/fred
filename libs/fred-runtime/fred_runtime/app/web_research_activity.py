# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Restricted product records for web research, separate from security audit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from fred_sdk.contracts.web_research import WebResearchError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, Integer, String, Text, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def activity_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    # Query parameters/fragments commonly contain signed links or credentials.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class WebResearchActivityBase(DeclarativeBase):
    pass


class WebResearchActivityGate(WebResearchActivityBase):
    """Durable erasure fence shared by replicas; retains no raw identity/query."""

    __tablename__ = "runtime_web_research_activity_gate"
    subject_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    erased: Mapped[bool] = mapped_column(Boolean, default=False)


class WebResearchActivityRow(WebResearchActivityBase):
    __tablename__ = "runtime_web_research_activity"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(32))
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="started")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WebResearchActivity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    user_id: str
    session_id: str | None
    team_id: str | None
    agent_instance_id: str | None
    correlation_id: str
    operation: str
    query: str | None
    url: str | None
    final_url: str | None
    outcome: str
    error_code: str | None
    duration_ms: int | None
    result_count: int | None
    created_at: datetime
    expires_at: datetime


class WebResearchActivityStore:
    def __init__(self, engine: AsyncEngine, retention_days: int) -> None:
        self._dialect = engine.dialect.name
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.retention_days = retention_days

    async def check_ready(self) -> None:
        async with self._sessions() as session:
            await session.execute(select(WebResearchActivityRow.request_id).limit(1))
            await session.execute(select(WebResearchActivityGate.subject_hash).limit(1))

    async def _lock_subject(
        self, session: AsyncSession, user_id: str
    ) -> WebResearchActivityGate:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = pg_insert if self._dialect == "postgresql" else sqlite_insert
        subject_hash = sha256(user_id.encode()).hexdigest()
        await session.execute(
            insert(WebResearchActivityGate)
            .values(
                subject_hash=subject_hash,
                erased=False,
            )
            .on_conflict_do_nothing(index_elements=["subject_hash"])
        )
        return (
            await session.execute(
                select(WebResearchActivityGate)
                .where(
                    WebResearchActivityGate.subject_hash == subject_hash,
                )
                .with_for_update()
            )
        ).scalar_one()

    async def begin(self, **fields: object) -> None:
        now = utcnow()
        async with self._sessions.begin() as session:
            gate = await self._lock_subject(session, str(fields["user_id"]))
            if gate.erased:
                raise WebResearchError("rejected")
            session.add(
                WebResearchActivityRow(
                    **fields,
                    created_at=now,
                    expires_at=now + timedelta(days=self.retention_days),
                    outcome="started",
                )
            )

    async def finish(self, request_id: str, **fields: object) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(WebResearchActivityRow)
                .where(WebResearchActivityRow.request_id == request_id)
                .values(**fields)
            )

    async def list(
        self, *, user_id: str | None, limit: int
    ) -> list[WebResearchActivity]:
        statement = select(WebResearchActivityRow).where(
            WebResearchActivityRow.expires_at > utcnow()
        )
        if user_id is not None:
            statement = statement.where(WebResearchActivityRow.user_id == user_id)
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        statement.order_by(
                            WebResearchActivityRow.created_at.desc()
                        ).limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [WebResearchActivity.model_validate(row) for row in rows]

    async def erase_user(self, user_id: str) -> int:
        async with self._sessions.begin() as session:
            gate = await self._lock_subject(session, user_id)
            gate.erased = True
            result = await session.execute(
                delete(WebResearchActivityRow).where(
                    WebResearchActivityRow.user_id == user_id
                )
            )
            return cast(CursorResult[Any], result).rowcount

    async def purge(self) -> None:
        now = utcnow()
        async with self._sessions.begin() as session:
            # An interrupted process cannot retrospectively claim the remote request failed.
            await session.execute(
                update(WebResearchActivityRow)
                .where(
                    WebResearchActivityRow.outcome == "started",
                    WebResearchActivityRow.created_at < now - timedelta(minutes=5),
                )
                .values(outcome="unknown", error_code="process_interrupted")
            )
            await session.execute(
                delete(WebResearchActivityRow).where(
                    WebResearchActivityRow.expires_at <= now
                )
            )
