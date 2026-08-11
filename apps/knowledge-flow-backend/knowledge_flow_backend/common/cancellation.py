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

"""Cooperative cancellation for blocking work running off the event loop.

Why this exists (GitHub #2315):
    Ingestion runs its heavy work in a thread (`asyncio.to_thread`), and Python
    cannot kill a thread. Cancelling an ingestion therefore stops the workflow
    and deletes the document immediately, while the thread keeps going to the
    end -- observed embedding and indexing 4038 chunks for ~3 minutes after the
    user pressed stop, every batch a paid embedding call for a document that no
    longer exists.

    The results were already discarded (`IngestionService.persist_progress`),
    so nothing was corrupted; the work itself was the waste. What was missing is
    a way to *tell* the thread. This module is that channel: the async side sets
    a flag when its activity is cancelled, and long-running loops check it at a
    natural boundary and stop.

Why a ContextVar holding an Event:
    `asyncio.to_thread` copies the caller's context into the worker thread, so
    the thread and the event loop end up holding the *same* `threading.Event`
    object -- a later `set()` from the loop is visible in the thread. A plain
    ContextVar value would not work: the thread got a snapshot, not a live view.

Where to check:
    At a boundary where stopping is cheap and leaves no half-written state --
    between batches, pages or files, never mid-write. A loop that does not check
    keeps today's behavior exactly.
"""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Generator
from contextlib import contextmanager

_cancellation_signal: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "fred_cancellation_signal",
    default=None,
)


class WorkCancelled(Exception):
    """Raised by `raise_if_cancelled` when the work has been cancelled.

    Ingestion activities let this propagate: the compensation path treats it
    like any other failure, and the document it was building is already gone.
    """


@contextmanager
def cancellation_scope() -> Generator[threading.Event, None, None]:
    """Scope one unit of cancellable work.

    Enter *before* handing the work to a thread, so the context copied into that
    thread carries this Event. On exit the signal is raised — the work either
    finished (nobody is left to read it) or was abandoned, and an abandoned
    thread must be told to stop at its next checkpoint.

    A scope, not a bare setter: the signal must not outlive its work. Leaving a
    raised signal installed would make the *next* piece of work in this context
    stop immediately, believing it had been cancelled.
    """
    signal = threading.Event()
    token = _cancellation_signal.set(signal)
    try:
        yield signal
    finally:
        signal.set()
        _cancellation_signal.reset(token)


def cancellation_requested() -> bool:
    """True once the work running in this context has been cancelled."""
    signal = _cancellation_signal.get()
    return signal is not None and signal.is_set()


def raise_if_cancelled(what: str) -> None:
    """Stop the current work if it has been cancelled.

    `what` names the loop being abandoned, so the log says which stage stopped
    early rather than only that something did.
    """
    if cancellation_requested():
        raise WorkCancelled(f"{what} cancelled; abandoning the remaining work")
