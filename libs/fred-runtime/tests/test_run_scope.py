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
The scope of one run: nested runs share it, a recorded stop ends all of it, and
its children are cancelled with it. It sets no limit of its own.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fred_runtime.runtime_support.authority import AuthorityLostError, RunStopError
from fred_runtime.runtime_support.run_scope import (
    _STOP_MESSAGES,
    RunScope,
    complete_cleanup,
    register_run_child,
    terminal_stop_event,
)
from fred_sdk.contracts.runtime import RuntimeStopReason


@pytest.mark.asyncio
async def test_cleanup_finishes_after_repeated_cancellation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    async def close() -> None:
        started.set()
        await release.wait()
        completed.set()

    task = asyncio.create_task(complete_cleanup(close()))
    await started.wait()
    task.cancel()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert completed.is_set()


@pytest.mark.asyncio
async def test_a_nested_run_joins_the_parents_scope() -> None:
    with RunScope.open() as parent:
        with RunScope.open() as child:
            # A child with a scope of its own would outlive the run that
            # started it, and a stop recorded there would not reach it.
            assert child is parent


def test_a_recorded_stop_is_raised_as_a_fresh_error_each_time() -> None:
    """One shared instance re-raised from several sites accumulates a traceback
    that belongs to none of them."""

    scope = RunScope()
    recorded = AuthorityLostError()
    scope.record_stop(recorded)

    raised = []
    for _ in range(2):
        with pytest.raises(AuthorityLostError) as caught:
            scope.raise_if_stopped()
        raised.append(caught.value)

    assert raised[0] is not recorded
    assert raised[1] is not recorded
    assert raised[0] is not raised[1]
    assert raised[0].reason == "authority_lost"


@pytest.mark.parametrize("reason", list(RuntimeStopReason))
def test_every_reason_has_its_own_platform_sentence(reason: RuntimeStopReason) -> None:
    """A reason added to the contract without a sentence beside it fails here,
    where it is cheap, rather than reading as a cancelled run in production."""

    class _Stop(RunStopError):
        pass

    _Stop.reason = reason.value
    event = terminal_stop_event(_Stop())

    assert event.reason is reason
    assert event.message == _STOP_MESSAGES[reason]


def test_a_reason_with_no_sentence_still_ends_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler that ends runs must not be the one that raises: looking the
    sentence up directly would `KeyError` exactly there."""

    monkeypatch.delitem(_STOP_MESSAGES, RuntimeStopReason.AUTHORITY_LOST)

    event = terminal_stop_event(AuthorityLostError())

    assert event.reason is RuntimeStopReason.AUTHORITY_LOST
    assert event.message == _STOP_MESSAGES[RuntimeStopReason.CANCELLED]


@pytest.mark.asyncio
async def test_a_child_is_registered_on_the_run_that_is_open() -> None:
    """The registration point a spawn path calls: work started in a task of its
    own goes with the run, and a caller outside any run is told so."""

    async def _forever() -> None:
        await asyncio.sleep(3600)

    orphan = asyncio.ensure_future(_forever())
    try:
        assert register_run_child(cast(Any, orphan)) is False
    finally:
        orphan.cancel()

    with RunScope.open() as scope:
        child = asyncio.ensure_future(_forever())
        assert register_run_child(cast(Any, child)) is True
        scope.cancel_children()

    await asyncio.sleep(0)
    assert child.cancelled()
