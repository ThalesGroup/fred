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

import pytest

from fred_knowledge.vector.cancellation import WorkCancelled, cancellation_requested, cancellation_scope, raise_if_cancelled


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
