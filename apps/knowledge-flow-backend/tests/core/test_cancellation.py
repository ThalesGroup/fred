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

"""Cooperative cancellation of blocking ingestion work (#2315).

Cancelling an ingestion cannot kill the thread doing the work, so the thread has
to be told. Observed before this existed: ~3 minutes of embedding and indexing
4038 chunks after the user pressed stop, for a document already deleted.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from knowledge_flow_backend.common.cancellation import (
    WorkCancelled,
    cancellation_requested,
    cancellation_scope,
    raise_if_cancelled,
)
from knowledge_flow_backend.features.scheduler import activity_utils


def test_no_signal_means_never_cancelled():
    # Code that runs outside an activity (CLI, tests, in-memory scheduler) must
    # not be told to stop.
    assert cancellation_requested() is False
    raise_if_cancelled("some loop")


def test_raise_if_cancelled_names_the_loop_it_abandons():
    with cancellation_scope() as signal:
        raise_if_cancelled("vector indexing")  # not raised yet

        signal.set()

        with pytest.raises(WorkCancelled, match="vector indexing"):
            raise_if_cancelled("vector indexing")


def test_a_raised_signal_does_not_leak_into_the_next_work():
    """The scope must not leave the next unit of work believing it was cancelled."""
    with cancellation_scope():
        pass  # exiting raises the signal, for any thread still running

    assert cancellation_requested() is False
    raise_if_cancelled("the next document")


def test_the_worker_thread_sees_a_cancellation_raised_after_it_started(monkeypatch):
    """The whole point: the flag is set *while* the thread is already running.

    A plain ContextVar value would fail here — the thread copied the context at
    start. The Event is shared, so a later set() reaches it.
    """
    monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: False)

    started = threading.Event()
    slices_done = 0

    def blocking_work() -> str:
        nonlocal slices_done
        started.set()
        for _ in range(100):  # stands in for the 4038-chunk batch loop
            raise_if_cancelled("test loop")
            slices_done += 1
            threading.Event().wait(0.01)
        return "ran to completion"

    async def scenario() -> None:
        task = asyncio.ensure_future(activity_utils.to_thread_with_heartbeat(blocking_work))
        await asyncio.to_thread(started.wait, 5)
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # The thread is unkillable, so it keeps running until its next check —
        # then stops, instead of grinding through all 100 slices.
        await asyncio.to_thread(threading.Event().wait, 0.2)

    asyncio.run(scenario())

    assert 0 < slices_done < 100


def test_work_that_completes_is_untouched(monkeypatch):
    monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: False)

    def blocking_work() -> str:
        for _ in range(5):
            raise_if_cancelled("test loop")
        return "done"

    assert asyncio.run(activity_utils.to_thread_with_heartbeat(blocking_work)) == "done"
