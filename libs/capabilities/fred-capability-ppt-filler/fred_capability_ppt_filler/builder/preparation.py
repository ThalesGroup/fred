# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Temporal owns retries; SQL leases fence attempts and retirement fences late writers."""

import asyncio
import uuid
from datetime import timedelta

from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationResult,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from fred_capability_ppt_filler.pptx_archive import sanitize_template

from . import analysis_job as jobs


def analysis_identity(ctx: PreparationContext) -> str:
    return f"prep:{ctx.work.preparation_id}"


async def _reserve(
    ctx: PreparationContext, *, retire: bool = False
) -> jobs.SqlAnalysisStore:
    factory = async_sessionmaker(ctx.database, expire_on_commit=False)
    store = jobs.SqlAnalysisStore(factory)
    identity = analysis_identity(ctx)
    now = jobs._utcnow()
    # A receipt, including a retired receipt, is never deleted/re-created. This
    # also fences a delayed first activity that had not inserted its row yet.
    try:
        async with factory() as session, session.begin():
            session.add(
                jobs.AnalysisRow(
                    agent_instance_id=identity,
                    team_id=str(ctx.work.space_id),
                    saved_by=f"runtime:{ctx.work.runtime_id}",
                    template_sha256=ctx.work.sha256,
                    labelling_key=jobs.RULES_KEY,
                    analysis_version=jobs.ANALYSIS_VERSION,
                    status="retired" if retire else "pending",
                    job_id=str(uuid.uuid4()),
                    attempts=0,
                    lease_until=now,
                    template_pptx=b"",
                    template_filename=ctx.work.filename,
                    created_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError:
        pass
    return store


async def retire(ctx: PreparationContext) -> None:
    store = await _reserve(ctx, retire=True)
    updated = await store._update(
        analysis_identity(ctx),
        jobs.AnalysisRow.saved_by == f"runtime:{ctx.work.runtime_id}",
        jobs.AnalysisRow.team_id == str(ctx.work.space_id),
        jobs.AnalysisRow.template_sha256 == ctx.work.sha256,
        status="retired",
        job_id=str(uuid.uuid4()),
        template_pptx=b"",
        inventory_json=None,
        patterns_pdf=None,
        overrides_json=None,
        error=None,
        lease_until=jobs._utcnow(),
    )
    if not updated:
        raise ValueError("Preparation identity mismatch")
    jobs.forget_inventories(analysis_identity(ctx))


async def prepare(ctx: PreparationContext) -> PreparationResult:
    store = await _reserve(ctx)
    identity = analysis_identity(ctx)
    async with store._sessionmaker() as session, session.begin():
        row = (
            await session.execute(
                select(jobs.AnalysisRow)
                .where(jobs.AnalysisRow.agent_instance_id == identity)
                .with_for_update()
            )
        ).scalar_one()
        if (
            row.saved_by != f"runtime:{ctx.work.runtime_id}"
            or row.team_id != str(ctx.work.space_id)
            or row.template_sha256 != ctx.work.sha256
        ):
            raise ValueError("Preparation identity mismatch")
        if row.status == "retired":
            raise ValueError("Preparation retired")
        if row.status == "succeeded":
            return PreparationResult(reference=identity)
        if row.status == "failed":
            return PreparationResult(error=row.error or "Template analysis failed")
        if jobs._aware(row.lease_until) > jobs._utcnow():
            raise RuntimeError("Another attempt still owns this preparation")
        job_id = str(uuid.uuid4())
        row.job_id = job_id
        row.attempts += 1
        row.status = "pending"
        row.lease_until = jobs._utcnow() + timedelta(seconds=jobs.LEASE_SECONDS)
    # No SQL transaction is retained over parsing, Office conversion or callbacks.
    template = await asyncio.to_thread(sanitize_template, ctx.content)
    if not await store._update(
        identity, jobs.AnalysisRow.job_id == job_id, template_pptx=template
    ):
        raise ValueError("Preparation superseded")
    await jobs.run_analysis(store, identity, job_id, template, None, jobs.RULES_KEY)
    record = await store.get(identity, with_inventory=False)
    if (
        record is None
        or record.job_id != job_id
        or record.status not in ("succeeded", "failed")
    ):
        raise RuntimeError("Preparation attempt lost ownership")
    return PreparationResult(
        reference=identity if record.status == "succeeded" else None,
        error=record.error if record.status == "failed" else None,
    )
