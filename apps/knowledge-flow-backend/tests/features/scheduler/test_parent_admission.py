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

"""The parent workflow's admission and failure containment.

These run `_wf_run_parent_pipeline` itself with `start_child_workflow`
intercepted, so what is asserted is the behaviour — which document starts when,
and what a failure does to its siblings — not the shape of the helper.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from temporalio.exceptions import CancelledError, ChildWorkflowError

from knowledge_flow_backend.features.scheduler import workflow as workflow_module
from knowledge_flow_backend.features.scheduler.workflow import _wf_run_parent_pipeline


def _file(profile: str, name: str) -> dict:
    return {"display_name": name, "document_uid": name, "profile": profile, "extraction_task_queue": f"ingestion-{profile}"}


class _Fixture:
    """Drives the children by hand: nothing finishes until the test says so."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.futures: dict[str, asyncio.Future] = {}

    def finish(self, name: str, *, exc: BaseException | None = None) -> None:
        future = self.futures[name]
        if exc is not None:
            future.set_exception(exc)
        else:
            future.set_result({"document_uid": name})

    def in_flight(self) -> set[str]:
        return {name for name, future in self.futures.items() if not future.done()}


@contextmanager
def _intercept(fixture: _Fixture):
    async def _start_child_workflow(_run, *, args, id, retry_policy):  # noqa: A002 - Temporal's own name
        name = args[1]["display_name"]
        fixture.started.append(name)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        fixture.futures[name] = future
        return future

    async def _wait(fs, *, timeout=None, return_when=asyncio.ALL_COMPLETED):
        """The SDK's `workflow.wait` differs from `asyncio.wait` on exactly one
        point that matters here: it returns lists, in the order it was given, not
        sets. Reproducing that keeps the admission loop's ordering under test."""
        done, pending = await asyncio.wait(fs, timeout=timeout, return_when=return_when)
        return [f for f in fs if f in done], [f for f in fs if f in pending]

    with (
        patch.object(workflow_module.workflow, "start_child_workflow", _start_child_workflow),
        patch.object(workflow_module.workflow, "wait", _wait),
        patch.object(workflow_module.workflow, "info", lambda: type("I", (), {"workflow_id": "wf-1"})()),
        patch.object(workflow_module.workflow, "logger", logging.getLogger("test-workflow")),
    ):
        yield


async def _run(files: list[dict], per_profile: int, fixture: _Fixture) -> asyncio.Task:
    definition = {"name": "p", "files": files, "max_parallelism": per_profile}
    task = asyncio.create_task(_wf_run_parent_pipeline(definition=definition, child_workflow_run=object(), child_prefix="ProcessPushFile"))
    await asyncio.sleep(0)  # let the first admission round run
    return task


async def _settle() -> None:
    for _ in range(6):
        await asyncio.sleep(0)


# ── admission ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fast_documents_start_while_the_rich_window_is_full() -> None:
    """The defect this replaces: three rich at the head of a submission held every
    fast document behind them, on workers that were not even busy."""
    files = [_file("rich", f"rich-{i}") for i in range(3)] + [_file("fast", f"fast-{i}") for i in range(5)]
    fixture = _Fixture()

    with _intercept(fixture):
        task = await _run(files, per_profile=2, fixture=fixture)
        await _settle()

        # Two rich (its window) and two fast — not the first four documents.
        assert set(fixture.started) == {"rich-0", "rich-1", "fast-0", "fast-1"}

        fixture.finish("fast-0")
        fixture.finish("fast-1")
        await _settle()
        # A freed fast slot goes to the next fast, without waiting for any rich.
        assert {"fast-2", "fast-3"} <= set(fixture.started)
        assert fixture.in_flight() >= {"rich-0", "rich-1"}

        for name in list(fixture.in_flight()):
            fixture.finish(name)
        await _settle()
        while not task.done():
            for name in list(fixture.in_flight()):
                fixture.finish(name)
            await _settle()
        assert task.result()["processed"] == len(files)


@pytest.mark.asyncio
async def test_no_profile_exceeds_its_window_and_the_total_is_the_sum() -> None:
    files = [_file("rich", f"rich-{i}") for i in range(4)] + [_file("fast", f"fast-{i}") for i in range(4)]
    fixture = _Fixture()

    with _intercept(fixture):
        task = await _run(files, per_profile=2, fixture=fixture)
        await _settle()

        in_flight = fixture.in_flight()
        assert len([n for n in in_flight if n.startswith("rich")]) == 2
        assert len([n for n in in_flight if n.startswith("fast")]) == 2
        # Two profiles present, two per profile.
        assert len(in_flight) == 4

        while not task.done():
            for name in list(fixture.in_flight()):
                fixture.finish(name)
            await _settle()
        assert task.result() == {"total": 8, "processed": 8, "failed": 0}


# ── failure containment ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_failed_document_does_not_stop_the_others() -> None:
    files = [_file("fast", f"fast-{i}") for i in range(4)]
    fixture = _Fixture()

    with _intercept(fixture):
        task = await _run(files, per_profile=2, fixture=fixture)
        await _settle()

        fixture.finish("fast-0", exc=RuntimeError("extractor exploded"))
        await _settle()

        # The submission carries on and admits the document behind the failure.
        assert "fast-2" in fixture.started
        while not task.done():
            for name in list(fixture.in_flight()):
                fixture.finish(name)
            await _settle()

        result = task.result()
        assert result == {"total": 4, "processed": 4, "failed": 1}


@pytest.mark.asyncio
async def test_a_submission_with_failures_is_not_reported_as_clean() -> None:
    files = [_file("fast", f"fast-{i}") for i in range(2)]
    fixture = _Fixture()

    with _intercept(fixture):
        task = await _run(files, per_profile=2, fixture=fixture)
        await _settle()
        fixture.finish("fast-0", exc=RuntimeError("boom"))
        fixture.finish("fast-1")
        await _settle()
        while not task.done():
            await _settle()

    assert task.result()["failed"] == 1


# ── cancellation stays distinct from failure ──────────────────────────────────


def _cancelled_child() -> ChildWorkflowError:
    error = ChildWorkflowError(
        "Child Workflow execution cancelled",
        namespace="default",
        workflow_id="ProcessPushFile-0-abc",
        run_id="run-1",
        workflow_type="ProcessPushFile",
        initiated_event_id=1,
        started_event_id=2,
        retry_state=None,
    )
    error.__cause__ = CancelledError("cancelled")
    return error


@pytest.mark.asyncio
async def test_cancellation_stops_admission_instead_of_counting_a_failure() -> None:
    """A failing document must not stop the submission; a cancelled one must. The
    two arrive at the same place, so the parent has to tell them apart."""
    files = [_file("fast", f"fast-{i}") for i in range(4)]
    fixture = _Fixture()

    with _intercept(fixture):
        task = await _run(files, per_profile=2, fixture=fixture)
        await _settle()
        admitted_before = set(fixture.started)

        fixture.finish("fast-0", exc=_cancelled_child())
        await _settle()
        for name in list(fixture.in_flight()):
            fixture.finish(name)
        await _settle()

        with pytest.raises(ChildWorkflowError):
            await task

    # No document was admitted after the cancellation surfaced.
    assert set(fixture.started) == admitted_before


@pytest.mark.asyncio
async def test_cancelling_the_parent_itself_stops_the_documents_it_started() -> None:
    """The other way a submission is cancelled: not a child reporting it, but the
    cancellation landing on this workflow while it waits. Admission has to stop,
    and the documents already running have to be cancelled with it — nothing else
    would ever tally them — with every outcome read, so none is later logged as
    an unhandled task error."""
    files = [_file("fast", f"fast-{i}") for i in range(4)]
    fixture = _Fixture()

    with _intercept(fixture):
        task = await _run(files, per_profile=2, fixture=fixture)
        await _settle()
        admitted = set(fixture.started)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert admitted, "nothing was running when the parent was cancelled"
    assert set(fixture.started) == admitted, "a document was admitted after the parent was cancelled"
    assert all(future.cancelled() for future in fixture.futures.values()), "a started document outlived the parent"
