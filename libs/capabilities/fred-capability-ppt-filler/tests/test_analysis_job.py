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

"""Background template analysis: the save returns at once, the result lives in
the shared table every replica reads, interrupted jobs are recovered, and a
superseded job never writes."""

from __future__ import annotations

import asyncio
import hashlib
import threading

import pytest
from analysis_db import age_row, drain
from builder_decks import build_showcase_template
from fred_capability_ppt_filler import concurrency
from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder.analysis import ANALYSIS_VERSION
from fred_capability_ppt_filler.builder.analysis_job import (
    MAX_ATTEMPTS,
    SqlAnalysisStore,
    analysis_readiness,
    get_analysis_store,
    labelling_key,
    parse_labelling_key,
    ready_inventory,
    status_response,
)
from fred_capability_ppt_filler.builder.capability import (
    PPT_BUILDER_TEMPLATE_KEY,
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.models import AnalysisError, AnalyzeResult
from fred_capability_ppt_filler.capability import TEMPLATE_SLOT
from fred_sdk.contracts.capability import (
    CapabilityIdentity,
    SaveContext,
    UploadedFile,
)
from fred_sdk.contracts.runtime import CapabilityModelPort, RuntimeServices
from port_fakes import FakeAssets

TEMPLATE = build_showcase_template()
SHA = hashlib.sha256(TEMPLATE).hexdigest()
INSTANCE = "inst-7"
IDENTITY = CapabilityIdentity(
    user_id="u-1", team_id="team-42", agent_instance_id=INSTANCE
)


class _Port(CapabilityModelPort):
    """A save's model port; labelling itself is replaced in these tests."""

    async def ainvoke(self, messages, *, profile_id=None, require_vision=False):
        raise AssertionError("label_inventory is faked here")


PORT = _Port()


def _save_ctx(assets: FakeAssets | None = None, port=PORT) -> SaveContext:
    return SaveContext(
        identity=IDENTITY,
        services=RuntimeServices(
            agent_assets=assets or FakeAssets(), capability_model=port
        ),
    )


def _uploads(content: bytes = TEMPLATE):
    return {TEMPLATE_SLOT: [UploadedFile(filename="template.pptx", content=content)]}


@pytest.fixture(autouse=True)
def offline_conversion(monkeypatch):
    async def _pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
        return b"%PDF-thumbs"

    async def _labels(inventory, template, pdf, port, *, profile_id, use_vision):
        return inventory

    monkeypatch.setattr(analysis_job, "convert_office_bytes_to_pdf", _pdf)
    monkeypatch.setattr(analysis_job, "label_inventory", _labels)


async def _save(config: PptBuilderConfig, uploads=None, assets=None, port=PORT):
    return await PptBuilderCapability().validate_config(
        config, uploads or {}, _save_ctx(assets, port)
    )


def test_labelling_key_round_trips():
    assert labelling_key(False, "gpt") == "rules"
    assert labelling_key(True, None) == "vision:agent-default"
    assert parse_labelling_key("vision:agent-default") == (True, None)
    assert parse_labelling_key("vision:chat.gpt4o") == (True, "chat.gpt4o")
    assert parse_labelling_key("rules") == (False, None)


@pytest.mark.asyncio
async def test_save_returns_before_the_job_ends(analysis_db, monkeypatch):
    release = asyncio.Event()
    seen: dict = {}

    async def _slow_label(inventory, template, pdf, port, *, profile_id, use_vision):
        seen.update(pdf=pdf, use_vision=use_vision, profile_id=profile_id)
        await release.wait()
        return inventory

    monkeypatch.setattr(analysis_job, "label_inventory", _slow_label)
    assets = FakeAssets()
    stored = await _save(
        PptBuilderConfig(labelling_model="chat.vision"), _uploads(), assets
    )

    assert stored.template_sha256 == SHA
    assert assets.blobs == {stored.template_key: TEMPLATE}
    store = get_analysis_store()
    record = await store.get(INSTANCE)
    assert record is not None and record.status in ("pending", "running")
    readiness = await PptBuilderCapability().readiness(stored, IDENTITY)
    assert readiness.state == "pending"

    release.set()
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.status == "succeeded"
    assert record.analysis_version == ANALYSIS_VERSION and record.has_thumbnails
    assert await store.patterns_pdf(INSTANCE) == b"%PDF-thumbs"
    assert seen == {
        "pdf": b"%PDF-thumbs",
        "use_vision": True,
        "profile_id": "chat.vision",
    }
    assert (await PptBuilderCapability().readiness(stored, IDENTITY)).state == "ready"
    assert status_response(record).summary is not None


@pytest.mark.asyncio
async def test_any_replica_reads_the_stored_result(analysis_db):
    stored = await _save(PptBuilderConfig(), _uploads())
    await drain()
    key = stored.labelling_key()
    first = await ready_inventory(get_analysis_store(), INSTANCE, SHA, key)
    assert first is not None

    analysis_job.clear_caches()  # another pod: nothing in memory
    other_replica = SqlAnalysisStore(analysis_db)
    second = await ready_inventory(other_replica, INSTANCE, SHA, key)
    assert second == first
    assert await ready_inventory(other_replica, INSTANCE, SHA, "rules") is None


@pytest.mark.asyncio
async def test_interrupted_analysis_is_reported_and_recovered(analysis_db):
    stored = await _save(PptBuilderConfig(use_vision=False), _uploads())
    await drain()
    await age_row(analysis_db, INSTANCE, status="running", inventory_json=None)
    store = get_analysis_store()
    record = await store.get(INSTANCE)
    assert record is not None
    response = status_response(record)
    assert response.status == "interrupted" and "Re-run" in (response.error or "")

    readiness = await analysis_readiness(store, INSTANCE, SHA, "rules")
    assert readiness.state == "pending"
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.status == "succeeded"
    assert record.attempts == 2
    assert (await PptBuilderCapability().readiness(stored, IDENTITY)).state == "ready"


@pytest.mark.asyncio
async def test_an_analysis_that_keeps_dying_fails_instead_of_looping(analysis_db):
    await _save(PptBuilderConfig(use_vision=False), _uploads())
    await drain()
    await age_row(analysis_db, INSTANCE, status="running", attempts=MAX_ATTEMPTS)
    readiness = await analysis_readiness(get_analysis_store(), INSTANCE, SHA, "rules")
    assert readiness.state == "failed" and "interrupted" in (readiness.detail or "")


@pytest.mark.asyncio
async def test_a_superseded_job_never_writes(analysis_db):
    store = get_analysis_store()
    common = dict(
        instance_id=INSTANCE,
        team_id="team-42",
        saved_by="u-1",
        template_sha256=SHA,
        labelling_key="rules",
    )
    first = await store.start(template=TEMPLATE, **common)
    second = await store.start(template=None, **common)
    inventory = (
        await asyncio.to_thread(analysis_job.analyze_template, TEMPLATE)
    ).inventory
    assert inventory is not None
    assert not await store.finish(INSTANCE, first, inventory, None)
    assert not await store.heartbeat(INSTANCE, first)
    assert await store.finish(INSTANCE, second, inventory, None)


@pytest.mark.asyncio
async def test_a_failed_analysis_reports_its_error(analysis_db, monkeypatch):
    def _broken(_content):
        return AnalyzeResult(
            errors=[AnalysisError(code="invalid_upload", message="No slide master.")]
        )

    monkeypatch.setattr(analysis_job, "analyze_template", _broken)
    stored = await _save(PptBuilderConfig(), _uploads())
    await drain()
    readiness = await PptBuilderCapability().readiness(stored, IDENTITY)
    assert readiness.state == "failed" and readiness.detail == "No slide master."


@pytest.mark.asyncio
async def test_changing_the_toggle_or_the_rules_re_runs_the_analysis(
    analysis_db, monkeypatch
):
    keys: list = []
    original = analysis_job.run_analysis

    async def _recording(store, instance_id, job_id, template, port, key):
        keys.append(key)
        await original(store, instance_id, job_id, template, port, key)

    monkeypatch.setattr(analysis_job, "run_analysis", _recording)
    stored = await _save(PptBuilderConfig(), _uploads())
    await drain()

    # An ordinary save of a current analysis starts nothing.
    await _save(stored)
    await drain()
    assert keys == ["vision:agent-default"]

    rules = await _save(stored.model_copy(update={"use_vision": False}))
    await drain()
    assert keys[-1] == "rules"
    record = await get_analysis_store().get(INSTANCE)
    assert record is not None and record.matches(SHA, "rules")
    assert record.status == "succeeded"

    await age_row(analysis_db, INSTANCE, status="succeeded", analysis_version=0)
    await _save(rules)
    await drain()
    record = await get_analysis_store().get(INSTANCE)
    assert record is not None and record.analysis_version == ANALYSIS_VERSION
    assert len(keys) == 3


@pytest.mark.asyncio
async def test_a_lost_row_is_rebuilt_from_the_stored_template(analysis_db):
    stored = PptBuilderConfig(template_sha256=SHA, use_vision=False)
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})
    assert (await PptBuilderCapability().readiness(stored, IDENTITY)).state == "failed"
    await _save(stored, assets=assets)
    await drain()
    assert (await PptBuilderCapability().readiness(stored, IDENTITY)).state == "ready"


async def _outdated(analysis_db, monkeypatch) -> tuple[PptBuilderConfig, list]:
    """A succeeded analysis made by older rules; records each job started."""
    stored = await _save(PptBuilderConfig(use_vision=False), _uploads())
    await drain()
    await age_row(analysis_db, INSTANCE, analysis_version=ANALYSIS_VERSION - 1)
    analysis_job.clear_caches()
    jobs: list = []
    original = analysis_job.run_analysis

    async def _recording(store, instance_id, job_id, template, port, key):
        jobs.append(job_id)
        await original(store, instance_id, job_id, template, port, key)

    monkeypatch.setattr(analysis_job, "run_analysis", _recording)
    return stored, jobs


@pytest.mark.asyncio
async def test_an_outdated_analysis_stays_ready_and_is_refreshed_once(
    analysis_db, monkeypatch
):
    stored, jobs = await _outdated(analysis_db, monkeypatch)
    release = asyncio.Event()

    async def _slow_label(inventory, template, pdf, port, *, profile_id, use_vision):
        await release.wait()
        return inventory

    monkeypatch.setattr(analysis_job, "label_inventory", _slow_label)
    store = get_analysis_store()
    capability = PptBuilderCapability()
    # Readiness checks and a turn notice it together: one refresh starts.
    states = await asyncio.gather(
        capability.readiness(stored, IDENTITY),
        capability.readiness(stored, IDENTITY),
        ready_inventory(store, INSTANCE, SHA, "rules"),
    )
    assert [s.state for s in states[:2]] == ["ready", "ready"]
    assert states[2] is not None  # the old inventory still serves the turn
    await asyncio.sleep(0)
    assert len(jobs) == 1
    record = await store.get(INSTANCE)
    assert record is not None and record.status == "succeeded"
    assert status_response(record).current  # being refreshed: no re-run offered
    assert (await capability.readiness(stored, IDENTITY)).state == "ready"
    assert len(jobs) == 1

    release.set()
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.analysis_version == ANALYSIS_VERSION
    assert await ready_inventory(store, INSTANCE, SHA, "rules") is not None
    assert analysis_job.cached_inventory(INSTANCE, SHA, "rules") is not None


@pytest.mark.asyncio
async def test_a_failed_refresh_keeps_the_old_analysis_and_is_not_retried(
    analysis_db, monkeypatch
):
    stored, jobs = await _outdated(analysis_db, monkeypatch)

    def _broken(_content):
        return AnalyzeResult(
            errors=[AnalysisError(code="invalid_upload", message="No slide master.")]
        )

    monkeypatch.setattr(analysis_job, "analyze_template", _broken)
    capability = PptBuilderCapability()
    assert (await capability.readiness(stored, IDENTITY)).state == "ready"
    await drain()
    store = get_analysis_store()
    record = await store.get(INSTANCE)
    assert record is not None and record.status == "succeeded"
    assert record.analysis_version == ANALYSIS_VERSION - 1
    assert record.inventory() is not None and record.attempts == MAX_ATTEMPTS
    assert not status_response(record).current  # the author may re-run it

    assert (await capability.readiness(stored, IDENTITY)).state == "ready"
    assert await ready_inventory(store, INSTANCE, SHA, "rules") is not None
    await drain()
    assert len(jobs) == 1
    # The author's re-run still starts one, and the agent stays ready meanwhile.
    assert await analysis_job.refresh_outdated(store, record, force=True)
    assert (await capability.readiness(stored, IDENTITY)).state == "ready"
    await drain()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_a_vision_analysis_is_refreshed_only_where_its_model_port_is(
    analysis_db, monkeypatch
):
    async def _labels(inventory, template, pdf, port, *, profile_id, use_vision):
        return inventory

    monkeypatch.setattr(analysis_job, "label_inventory", _labels)
    stored = await _save(PptBuilderConfig(), _uploads())
    await drain()
    await age_row(analysis_db, INSTANCE, analysis_version=ANALYSIS_VERSION - 1)
    analysis_job.clear_caches()  # a pod that did not take the save: no port
    jobs: list = []
    original = analysis_job.run_analysis

    async def _recording(store, instance_id, job_id, template, port, key):
        jobs.append(port)
        await original(store, instance_id, job_id, template, port, key)

    monkeypatch.setattr(analysis_job, "run_analysis", _recording)
    capability = PptBuilderCapability()
    store = get_analysis_store()
    key = stored.labelling_key()
    assert (await capability.readiness(stored, IDENTITY)).state == "ready"
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    await drain()
    assert jobs == []
    record = await store.get(INSTANCE)
    assert record is not None and not status_response(record).current

    port = object()
    analysis_job.remember_port(INSTANCE, port)  # type: ignore[arg-type]
    assert (await capability.readiness(stored, IDENTITY)).state == "ready"
    await drain()
    assert jobs == [port]
    record = await store.get(INSTANCE)
    assert record is not None and record.analysis_version == ANALYSIS_VERSION


class _CountingStore(SqlAnalysisStore):
    def __init__(self, maker) -> None:
        super().__init__(maker)
        self.reads = 0

    async def get(self, instance_id, *, with_inventory=True):
        self.reads += 1
        return await super().get(instance_id, with_inventory=with_inventory)


@pytest.mark.asyncio
async def test_an_outdated_inventory_whose_refresh_never_lands_is_served_from_memory(
    analysis_db, monkeypatch
):
    """A failed refresh (attempts spent) never lands: turns must not each pay a
    row read and a JSON parse, yet the row is re-read now and then."""
    stored, jobs = await _outdated(analysis_db, monkeypatch)
    await age_row(analysis_db, INSTANCE, attempts=MAX_ATTEMPTS)
    store = _CountingStore(analysis_db)
    key = stored.labelling_key()
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    assert analysis_job.cached_inventory(INSTANCE, SHA, key) is not None
    assert store.reads == 1 and jobs == []

    monkeypatch.setattr(analysis_job, "OUTDATED_RECHECK_SECONDS", 0.0)
    analysis_job.clear_caches()
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    assert store.reads == 3  # due for a re-read on every call now


@pytest.mark.asyncio
async def test_a_refresh_that_lands_here_replaces_the_cached_outdated_inventory(
    analysis_db, monkeypatch
):
    stored, jobs = await _outdated(analysis_db, monkeypatch)
    store = get_analysis_store()
    key = stored.labelling_key()
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    await drain()
    assert len(jobs) == 1
    assert analysis_job.cached_inventory(INSTANCE, SHA, key) is None
    assert await ready_inventory(store, INSTANCE, SHA, key) is not None
    record = await store.get(INSTANCE)
    assert record is not None and not record.outdated()


@pytest.mark.asyncio
async def test_a_recovery_without_the_port_stores_rules_and_a_save_relabels(
    analysis_db,
):
    """An interrupted vision analysis recovered on a pod without the model port
    labels by rules: the row says so, the agent stays ready, and the next save
    that brings the port re-runs it with vision."""
    stored = await _save(PptBuilderConfig(), _uploads())
    await drain()
    await age_row(analysis_db, INSTANCE, status="running", inventory_json=None)
    analysis_job.clear_caches()  # another pod: no port
    store = get_analysis_store()
    assert (
        await analysis_readiness(store, INSTANCE, SHA, "vision:agent-default")
    ).state == "pending"
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.status == "succeeded"
    assert record.labelling_key == "rules"
    assert (await PptBuilderCapability().readiness(stored, IDENTITY)).state == "ready"
    assert await ready_inventory(store, INSTANCE, SHA, stored.labelling_key())

    await _save(stored, port=None)  # still no port: nothing to gain, no job
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.labelling_key == "rules"
    await _save(stored)
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.labelling_key == "vision:agent-default"


@pytest.mark.asyncio
async def test_a_forced_refresh_without_the_port_is_not_mistaken_for_vision(
    analysis_db,
):
    stored = await _save(PptBuilderConfig(), _uploads())
    await drain()
    await age_row(analysis_db, INSTANCE, analysis_version=ANALYSIS_VERSION - 1)
    analysis_job.clear_caches()
    store = get_analysis_store()
    record = await store.get(INSTANCE)
    assert record is not None
    assert await analysis_job.refresh_outdated(store, record, force=True)
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.analysis_version == ANALYSIS_VERSION
    assert record.labelling_key == "rules"
    await _save(stored)
    await drain()
    record = await store.get(INSTANCE)
    assert record is not None and record.labelling_key == "vision:agent-default"


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
