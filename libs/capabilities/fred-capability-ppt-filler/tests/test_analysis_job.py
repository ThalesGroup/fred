# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""SQL preparation receipts, attempt fencing and bounded preflight.

Swift's save/list-triggered asyncio recovery tests are replaced by the durable
preparation contract. Cancellation/CPU capacity protections remain covered.
"""

import asyncio
import hashlib
import threading
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from builder_decks import build_showcase_template
from fred_capability_ppt_filler import concurrency
from fred_capability_ppt_filler.builder import analysis_job as jobs
from fred_capability_ppt_filler.builder import preparation
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.capability import (
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_sdk.contracts.capability import CapabilityIdentity, SaveContext, UploadedFile
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationWork,
)
from fred_sdk.contracts.runtime import RuntimeServices
from sqlalchemy import select

analysis_job = jobs
TEMPLATE = build_showcase_template()
SHA = hashlib.sha256(TEMPLATE).hexdigest()


def context(maker):
    return PreparationContext(
        work=PreparationWork(
            preparation_id=uuid4(),
            installation_id=uuid4(),
            runtime_id="pod-a",
            capability_id="ppt_builder",
            space_id=uuid4(),
            agent_instance_id=uuid4(),
            configuration_revision=1,
            file_id=uuid4(),
            sha256=SHA,
            filename="model.pptx",
            size=len(TEMPLATE),
            config={"use_vision": False},
            state="pending",
        ),
        database=maker.kw["bind"],
        content=TEMPLATE,
    )


@pytest.fixture
def calculate(monkeypatch):
    calls = []

    async def analyse(content, port, key):
        calls.append((content, port, key))
        return builtin_template()[1], b"%PDF-thumbnails"

    monkeypatch.setattr(jobs, "_analyse", analyse)
    return calls


@pytest.mark.asyncio
async def test_preflight_has_no_writes_and_does_not_trust_client_results(analysis_db):
    ctx = SaveContext(
        identity=CapabilityIdentity(user_id="editor", team_id="space"),
        services=RuntimeServices(),
    )
    capability = PptBuilderCapability()
    result = await capability.validate_config(
        PptBuilderConfig(template_sha256=SHA, analysis_id="forged"),
        {"template": [UploadedFile(filename="model.pptx", content=TEMPLATE)]},
        ctx,
    )
    assert result.template_sha256 is None and result.analysis_id is None
    async with analysis_db() as session:
        assert (await session.execute(select(jobs.AnalysisRow))).first() is None
    with pytest.raises(ValueError):
        await capability.validate_config(
            PptBuilderConfig(),
            {"template": [UploadedFile(filename="bad.pptx", content=b"not pptx")]},
            ctx,
        )
    with pytest.raises(ValueError, match="vision"):
        await capability.validate_config(PptBuilderConfig(use_vision=True), {}, ctx)


@pytest.mark.asyncio
async def test_written_result_is_reused_on_another_replica_before_reconfirmation(
    analysis_db, calculate
):
    ctx = context(analysis_db)
    first = await preparation.prepare(ctx)
    jobs.clear_caches()
    second = await preparation.prepare(replace(ctx))
    assert first == second and first.reference == preparation.analysis_identity(ctx)
    assert len(calculate) == 1 and calculate[0][1:] == (None, "rules")
    store = jobs.SqlAnalysisStore(analysis_db)
    assert first.reference is not None
    assert await store.patterns_pdf(first.reference) == b"%PDF-thumbnails"
    assert (
        await jobs.analysis_readiness(store, first.reference, SHA, "rules")
    ).state == "ready"


@pytest.mark.asyncio
async def test_readiness_does_not_restart_an_expired_attempt(analysis_db, calculate):
    ctx = context(analysis_db)
    store = await preparation._reserve(ctx)
    identity = preparation.analysis_identity(ctx)
    assert (
        await jobs.analysis_readiness(store, identity, SHA, "rules")
    ).state == "pending"
    assert not calculate
    result = await preparation.prepare(ctx)
    assert result.reference and len(calculate) == 1


@pytest.mark.asyncio
async def test_retirement_before_first_activity_prevents_recreation(
    analysis_db, calculate
):
    ctx = context(analysis_db)
    await preparation.retire(ctx)
    await preparation.retire(ctx)
    with pytest.raises(ValueError, match="retired"):
        await preparation.prepare(ctx)
    assert not calculate
    store = jobs.SqlAnalysisStore(analysis_db)
    assert await store.template(preparation.analysis_identity(ctx)) is None


@pytest.mark.asyncio
async def test_retirement_during_calculation_fences_final_write(
    analysis_db, monkeypatch
):
    ctx = context(analysis_db)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def analyse(*args):
        entered.set()
        await release.wait()
        return builtin_template()[1], b"pdf"

    monkeypatch.setattr(jobs, "_analyse", analyse)
    task = asyncio.create_task(preparation.prepare(ctx))
    await entered.wait()
    await preparation.retire(ctx)
    release.set()
    with pytest.raises(RuntimeError, match="lost ownership"):
        await task
    store = jobs.SqlAnalysisStore(analysis_db)
    record = await store.get(preparation.analysis_identity(ctx))
    assert record is not None
    assert record.status == "retired" and record.inventory_json is None
    assert await store.patterns_pdf(record.agent_instance_id) is None


@pytest.mark.asyncio
async def test_expired_writer_cannot_publish_after_takeover(analysis_db, calculate):
    ctx = context(analysis_db)
    store = await preparation._reserve(ctx)
    identity = preparation.analysis_identity(ctx)
    record = await store.get(identity)
    assert record is not None
    old_job = record.job_id
    await preparation.prepare(ctx)
    assert not await store.finish(
        identity, old_job, builtin_template()[1], "late", None
    )
    assert await store.patterns_pdf(identity) == b"%PDF-thumbnails"


@pytest.mark.asyncio
async def test_concurrent_attempt_waits_for_lease_and_expiry_allows_recovery(
    analysis_db, calculate
):
    ctx = context(analysis_db)
    store = await preparation._reserve(ctx)
    identity = preparation.analysis_identity(ctx)
    await store._update(identity, lease_until=jobs._utcnow() + timedelta(seconds=90))
    with pytest.raises(RuntimeError, match="Another attempt"):
        await preparation.prepare(ctx)
    await store._update(identity, lease_until=jobs._utcnow() - timedelta(seconds=1))
    assert (await preparation.prepare(ctx)).reference
    assert len(calculate) == 1


@pytest.mark.asyncio
async def test_analysis_failure_is_persisted_without_inference_or_list_retry(
    analysis_db, monkeypatch
):
    ctx = context(analysis_db)

    async def fail(*args):
        raise jobs.AnalysisFailed("No usable layouts")

    monkeypatch.setattr(jobs, "_analyse", fail)
    first = await preparation.prepare(ctx)
    assert first.reference is None and first.error == "No usable layouts"
    assert await preparation.prepare(ctx) == first


@pytest.mark.asyncio
async def test_a_cancelled_job_keeps_its_slot_until_its_thread_ends():
    """Cancelling (timeout, superseded job) cannot stop the worker thread: its
    heavy-job slot stays taken until the thread is really done."""
    started, release = threading.Event(), threading.Event()

    def _blocking() -> None:
        started.set()
        release.wait(5)

    assert concurrency._active_jobs == 0
    job = asyncio.ensure_future(analysis_job._cpu(_blocking))
    await asyncio.to_thread(started.wait, 5)
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert concurrency._active_jobs == 1
    release.set()
    for _ in range(500):
        if concurrency._active_jobs == 0:
            break
        await asyncio.sleep(0.01)
    assert concurrency._active_jobs == 0


@pytest.mark.asyncio
async def test_background_work_leaves_heavy_slots_to_the_turns(monkeypatch):
    """Many refreshes at once (a version bump) take at most two of the four
    heavy-job slots, so a turn's build is never answered busy because of them."""
    monkeypatch.setattr(analysis_job, "_SLOT_POLL_SECONDS", 0.01)
    release = threading.Event()
    jobs = [asyncio.ensure_future(analysis_job._cpu(release.wait, 5)) for _ in range(4)]
    for _ in range(20):
        await asyncio.sleep(0.01)
    assert concurrency._active_jobs == analysis_job.MAX_BACKGROUND_SLOTS == 2
    turns = [concurrency.acquire_heavy_job_slot() for _ in range(2)]
    assert turns == [True, True]
    for _ in turns:
        concurrency.release_heavy_job_slot()
    release.set()
    await asyncio.gather(*jobs)
    for _ in range(500):
        if concurrency._active_jobs == 0:
            break
        await asyncio.sleep(0.01)
    assert concurrency._active_jobs == 0 and analysis_job._background_slots == 0


@pytest.mark.asyncio
async def test_other_pod_cannot_reuse_or_retire_the_result(analysis_db, calculate):
    ctx = context(analysis_db)
    first = await preparation.prepare(ctx)
    wrong = replace(ctx, work=ctx.work.model_copy(update={"runtime_id": "another-pod"}))
    with pytest.raises(ValueError, match="identity mismatch"):
        await preparation.prepare(wrong)
    with pytest.raises(ValueError, match="identity mismatch"):
        await preparation.retire(wrong)
    assert await preparation.prepare(ctx) == first
    assert len(calculate) == 1
