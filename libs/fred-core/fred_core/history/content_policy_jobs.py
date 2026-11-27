# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Durable, short-lived explanation work attached to a terminal history row."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .history_models import SessionHistoryRow
from .history_schema import Channel, ContentCategory, ContentNotice, Role

JOB_LIFETIME = timedelta(seconds=90)
_LEASE = timedelta(seconds=14)


@dataclass(frozen=True)
class ContentPolicyJob:
    rank: int
    runtime_id: str
    binding: dict | None
    pod_profile_id: str | None


@dataclass(frozen=True)
class ClaimedContentPolicyJob:
    row_key: tuple[str, str, int]
    reference: str
    lease: str
    categories: tuple[ContentCategory, ...]
    binding: dict | None
    pod_profile_id: str | None


def _stored_notice(row: SessionHistoryRow) -> ContentNotice | None:
    try:
        return ContentNotice.model_validate(
            (row.metadata_json or {}).get("content_notice")
        )
    except ValidationError:
        return None


def _settle(row: SessionHistoryRow, explanation: ContentCategory | None) -> None:
    notice = _stored_notice(row)
    if notice is not None and notice.analysis_state == "pending":
        updated = notice.model_copy(
            update={
                "analysis_state": "complete" if explanation else "unavailable",
                "explanation": explanation,
            }
        )
        row.metadata_json = {
            **(row.metadata_json or {}),
            "content_notice": updated.model_dump(mode="json"),
        }
    row.content_policy_job = None
    row.content_policy_runtime = None
    row.content_policy_due = None


class ContentPolicyJobs:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def claim(self, runtime_id: str) -> ClaimedContentPolicyJob | None:
        row = SessionHistoryRow
        async with self._sessions.begin() as session:
            # Only one live lease per runtime ID across replicas. The advisory
            # lock covers selection and commit; the model call holds no DB slot.
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                locked = await session.scalar(
                    text(
                        "select pg_try_advisory_xact_lock(915248, hashtext(:runtime_id))"
                    ),
                    {"runtime_id": runtime_id},
                )
                if not locked:
                    return None
            now = await self._now(session)
            scope = row.content_policy_runtime == runtime_id
            future = await session.scalar(
                select(row.rank).where(scope, row.content_policy_due > now).limit(1)
            )
            if future is not None:
                return None
            due = await session.scalars(
                select(row)
                .where(scope, row.content_policy_due <= now)
                .order_by(row.content_policy_due)
                .limit(16)
                .with_for_update(skip_locked=True)
            )
            for current in due:
                job = current.content_policy_job or {}
                notice = _stored_notice(current)
                reference = (current.metadata_json or {}).get("support_error_ref")
                if (
                    notice is None
                    or notice.analysis_state != "pending"
                    or not isinstance(reference, str)
                    or reference != job.get("reference")
                    or current.timestamp.replace(tzinfo=timezone.utc) + JOB_LIFETIME
                    <= now
                ):
                    _settle(current, None)
                    continue
                lease = uuid4().hex
                current.content_policy_job = {**job, "lease": lease}
                current.content_policy_due = now + _LEASE
                return ClaimedContentPolicyJob(
                    (current.session_id, current.user_id, current.rank),
                    reference,
                    lease,
                    notice.categories,
                    job.get("binding"),
                    job.get("pod_profile_id"),
                )
        return None

    @staticmethod
    async def _now(session: AsyncSession) -> datetime:
        value = await session.scalar(select(func.now()))
        if value is None:
            raise RuntimeError("Database clock is unavailable.")
        return value.replace(tzinfo=timezone.utc)

    async def finish(
        self, claim: ClaimedContentPolicyJob, explanation: ContentCategory | None
    ) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(
                SessionHistoryRow, claim.row_key, with_for_update=True
            )
            if row is None or row.content_policy_job is None:
                return
            if (
                row.content_policy_job.get("lease") == claim.lease
                and (row.metadata_json or {}).get("support_error_ref")
                == claim.reference
            ):
                now = await self._now(session)
                if row.timestamp.replace(tzinfo=timezone.utc) + JOB_LIFETIME <= now:
                    explanation = None
                _settle(row, explanation if explanation in claim.categories else None)

    async def read_notice(
        self, session_id: str, rank: int, support_error_ref: str, user_id: str | None
    ) -> tuple[ContentNotice, bool] | None:
        row = SessionHistoryRow
        query = select(row.metadata_json, row.agent_instance_id).where(
            row.session_id == session_id,
            row.rank == rank,
            row.metadata_json["support_error_ref"].as_string() == support_error_ref,
            row.channel == Channel.error.value,
            row.role == Role.system.value,
        )
        if user_id is not None:
            query = query.where(row.user_id == user_id)
        async with self._sessions() as session:
            result = (await session.execute(query.limit(1))).first()
        if result is None:
            return None
        metadata, agent_instance_id = result
        try:
            notice = ContentNotice.model_validate(
                (metadata or {}).get("content_notice")
            )
        except ValidationError:
            return None
        return notice, agent_instance_id is not None
