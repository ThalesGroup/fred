# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared files in the object store: SQL publishes them and governs their erasure.

The store cannot join a SQL transaction. Each test stops at a point where the two
disagree and asserts what a reader and the cleanup observe at that point.
"""

import asyncio
import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest
from builder_decks import build_showcase_template
from fred_capability_ppt_filler.builder import analysis_job as jobs
from fred_capability_ppt_filler.builder import preparation
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationWork,
)

TEMPLATE = build_showcase_template()
SHA = hashlib.sha256(TEMPLATE).hexdigest()


def context(maker) -> PreparationContext:
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
            config={},
            state="pending",
        ),
        database=maker.kw["bind"],
        content=TEMPLATE,
    )


@pytest.fixture(autouse=True)
def analyse(monkeypatch):
    async def run(content, port, key):
        return builtin_template()[1], b"%PDF-thumbnails"

    monkeypatch.setattr(jobs, "_analyse", run)


def directory(ctx: PreparationContext) -> str:
    return str(ctx.work.preparation_id)


async def pending_writes(maker, ctx: PreparationContext) -> int:
    return await jobs.SqlAnalysisStore(maker)._scalar(
        jobs.AnalysisRow.pending_writes, preparation.analysis_identity(ctx)
    )


async def expire_lease(maker, ctx: PreparationContext) -> None:
    await jobs.SqlAnalysisStore(maker)._update(
        preparation.analysis_identity(ctx),
        lease_until=jobs._utcnow().replace(year=2000),
    )


class HeldWrite:
    """Holds the next object write open, as a slow PUT does."""

    def __init__(self, objects) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        objects.before_write = self._hold

    async def _hold(self, path: str) -> None:
        self.entered.set()
        await self.release.wait()


def test_the_table_holds_no_file_bytes():
    columns = jobs.AnalysisRow.__table__.columns.keys()
    assert "template_pptx" not in columns and "patterns_pdf" not in columns


@pytest.mark.asyncio
async def test_template_and_preview_are_read_back_from_the_attempts_directory(
    analysis_db, objects
):
    ctx = context(analysis_db)
    await preparation.prepare(ctx)
    identity = preparation.analysis_identity(ctx)
    store = jobs.SqlAnalysisStore(analysis_db)
    record = await store.get(identity)
    assert record is not None and record.has_thumbnails
    assert set(objects.files) == {
        f"{directory(ctx)}/{record.job_id}/template.pptx",
        f"{directory(ctx)}/{record.job_id}/patterns.pdf",
    }
    assert await store.patterns_pdf(identity) == b"%PDF-thumbnails"
    assert await store.template(identity, sha=SHA) is not None
    assert await store.template(identity, sha="another-template") is None
    assert await pending_writes(analysis_db, ctx) == 0


@pytest.mark.asyncio
async def test_a_template_without_preview_publishes_no_thumbnails(
    analysis_db, objects, monkeypatch
):
    async def without_pdf(content, port, key):
        return builtin_template()[1], None

    monkeypatch.setattr(jobs, "_analyse", without_pdf)
    ctx = context(analysis_db)
    await preparation.prepare(ctx)
    identity = preparation.analysis_identity(ctx)
    store = jobs.SqlAnalysisStore(analysis_db)
    record = await store.get(identity)
    assert record is not None and not record.has_thumbnails
    assert await store.patterns_pdf(identity) is None
    assert len(objects.files) == 1


@pytest.mark.asyncio
async def test_a_changed_object_is_refused_and_a_missing_one_is_absent(
    analysis_db, objects
):
    ctx = context(analysis_db)
    await preparation.prepare(ctx)
    identity = preparation.analysis_identity(ctx)
    store = jobs.SqlAnalysisStore(analysis_db)
    key = next(k for k in objects.files if k.endswith("template.pptx"))
    original = objects.files[key]
    objects.files[key] = b"not the analysed template"
    with pytest.raises(RuntimeError, match="does not match"):
        await store.template(identity)
    objects.files[key] = original
    del objects.files[key]
    assert await store.template(identity) is None


@pytest.mark.asyncio
async def test_nothing_is_usable_before_the_files_are_stored(analysis_db, objects):
    ctx = context(analysis_db)
    held = HeldWrite(objects)
    task = asyncio.create_task(preparation.prepare(ctx))
    await held.entered.wait()
    identity = preparation.analysis_identity(ctx)
    store = jobs.SqlAnalysisStore(analysis_db)
    assert (await jobs.analysis_readiness(store, identity, SHA, "rules")).state == (
        "pending"
    )
    assert await store.template(identity) is None
    assert await pending_writes(analysis_db, ctx) == 1
    held.release.set()
    await task
    assert (await jobs.analysis_readiness(store, identity, SHA, "rules")).state == (
        "ready"
    )


@pytest.mark.asyncio
async def test_stopping_between_upload_and_publication_reuses_nothing_and_blocks_nothing(
    analysis_db, objects, monkeypatch
):
    ctx = context(analysis_db)
    finish = jobs.SqlAnalysisStore.finish

    async def stopped(*args, **kwargs):
        raise ConnectionError("process stopped before the SQL publication")

    monkeypatch.setattr(jobs.SqlAnalysisStore, "finish", stopped)
    with pytest.raises(ConnectionError):
        await preparation.prepare(ctx)
    identity = preparation.analysis_identity(ctx)
    store = jobs.SqlAnalysisStore(analysis_db)
    assert await store.template(identity) is None
    # Every PUT really returned: nothing is uncertain, only tracked by its prefix.
    assert await pending_writes(analysis_db, ctx) == 0
    abandoned = set(objects.files)

    monkeypatch.setattr(jobs.SqlAnalysisStore, "finish", finish)
    await expire_lease(analysis_db, ctx)
    result = await preparation.prepare(replace(ctx))
    assert result.reference == identity
    assert await store.template(identity) is not None
    assert abandoned < set(objects.files)

    await preparation.retire(ctx)
    assert objects.files == {}


@pytest.mark.asyncio
async def test_an_unknown_write_outcome_is_retried_and_durably_blocks_erasure(
    analysis_db, objects
):
    ctx = context(analysis_db)

    async def fails(path: str) -> None:
        raise TimeoutError("the PUT may still take effect")

    objects.before_write = fails
    with pytest.raises(jobs.ObjectStorageUnavailable):
        await preparation.prepare(ctx)
    identity = preparation.analysis_identity(ctx)
    store = jobs.SqlAnalysisStore(analysis_db)
    record = await store.get(identity)
    assert record is not None and record.status == "running"  # a retry, not a verdict
    assert await pending_writes(analysis_db, ctx) == 1

    objects.before_write = None
    await expire_lease(analysis_db, ctx)
    assert (await preparation.prepare(ctx)).reference == identity
    survivors = dict(objects.files)
    assert survivors
    assert await pending_writes(analysis_db, ctx) == 1  # that attempt's PUT never ended

    for _ in range(2):  # a replay finds the same block, and never expires it
        with pytest.raises(jobs.PreparationWritesPending):
            await preparation.retire(ctx)
    assert objects.files == survivors
    record = await store.get(identity)
    assert record is not None and record.status == "retired"
    assert await store.template(identity) is None

    # The documented release, once an operator has established the writer ended.
    await store._update(identity, pending_writes=0)
    await preparation.retire(ctx)
    assert objects.files == {}


@pytest.mark.asyncio
async def test_an_unreachable_store_leaves_no_unknown_write(analysis_db, objects):
    ctx = context(analysis_db)
    objects.unreachable = True
    with pytest.raises(jobs.ObjectStorageUnavailable):
        await preparation.prepare(ctx)
    assert await pending_writes(analysis_db, ctx) == 0 and not objects.written
    objects.unreachable = False
    await preparation.retire(ctx)


@pytest.mark.asyncio
async def test_retirement_during_upload_waits_for_the_write_then_erases_for_good(
    analysis_db, objects
):
    ctx = context(analysis_db)
    held = HeldWrite(objects)
    task = asyncio.create_task(preparation.prepare(ctx))
    await held.entered.wait()

    with pytest.raises(jobs.PreparationWritesPending):
        await preparation.retire(ctx)

    held.release.set()
    with pytest.raises(RuntimeError, match="lost ownership"):
        await task  # the late files are present, and publication was refused
    objects.before_write = None
    assert objects.files
    assert await pending_writes(analysis_db, ctx) == 0

    await preparation.retire(ctx)
    assert objects.files == {}

    # A delayed retry after confirmed cleanup can neither calculate nor write.
    written = list(objects.written)
    with pytest.raises(ValueError, match="retired"):
        await preparation.prepare(ctx)
    assert objects.files == {} and objects.written == written


@pytest.mark.asyncio
async def test_a_cancelled_caller_cannot_acknowledge_a_write_still_running(
    analysis_db, objects
):
    ctx = context(analysis_db)
    held = HeldWrite(objects)
    task = asyncio.create_task(preparation.prepare(ctx))
    await held.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await pending_writes(analysis_db, ctx) == 1
    held.release.set()
    for _ in range(500):
        if not jobs._uploads:
            break
        await asyncio.sleep(0.01)
    assert await pending_writes(analysis_db, ctx) == 0


@pytest.mark.asyncio
async def test_a_superseded_attempt_writes_nothing_and_cannot_touch_the_published_files(
    analysis_db, objects
):
    ctx = context(analysis_db)
    store = await preparation._reserve(ctx)
    identity = preparation.analysis_identity(ctx)
    old = await store.get(identity)
    assert old is not None
    await preparation.prepare(ctx)
    published = dict(objects.files)
    assert await store.upload(identity, old.job_id, b"late", b"late") is None
    assert objects.files == published and await pending_writes(analysis_db, ctx) == 0


@pytest.mark.asyncio
async def test_retiring_one_preparation_leaves_another_identical_one_intact(
    analysis_db, objects
):
    kept, retired = context(analysis_db), context(analysis_db)
    await preparation.prepare(kept)
    await preparation.prepare(retired)
    await preparation.retire(retired)
    assert objects.files
    assert all(key.startswith(f"{directory(kept)}/") for key in objects.files)
    store = jobs.SqlAnalysisStore(analysis_db)
    assert await store.template(preparation.analysis_identity(kept)) is not None
