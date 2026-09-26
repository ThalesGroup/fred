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

"""Run lifetime, descendant cancellation and terminal stop events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Final, TypeVar, cast

import anyio
from fred_sdk.contracts.runtime import RuntimeErrorEvent, RuntimeStopReason

from .authority import RunStopError

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Fixed messages keep upstream response content out of terminal events.
_STOP_MESSAGES: Final[dict[RuntimeStopReason, str]] = {
    RuntimeStopReason.AUTHORITY_LOST: (
        "This run was stopped because it is no longer authorized to act for you."
    ),
    RuntimeStopReason.CANCELLED: "This run was stopped.",
    RuntimeStopReason.DELEGATION_UNAVAILABLE: (
        "This run was stopped because delegated access is unavailable."
    ),
}


def stop_reason_of(error: RunStopError) -> RuntimeStopReason:
    """Map a stop error onto the event enum, defaulting to `cancelled`."""

    try:
        return RuntimeStopReason(error.reason)
    except ValueError:
        return RuntimeStopReason.CANCELLED


def terminal_stop_event(error: RunStopError, *, sequence: int = 0) -> RuntimeErrorEvent:
    """Build the terminal event for a stopped run from its reason alone."""

    reason = stop_reason_of(error)
    return RuntimeErrorEvent(
        sequence=sequence,
        # A reason added later must not make the handler that ends runs raise.
        message=_STOP_MESSAGES.get(reason, _STOP_MESSAGES[RuntimeStopReason.CANCELLED]),
        reason=reason,
    )


_CURRENT_RUN_SCOPE: ContextVar[RunScope | None] = ContextVar(
    "fred_current_run_scope", default=None
)
_OWNER_EXECUTION: ContextVar[bool] = ContextVar("fred_owner_execution", default=False)


def set_owner_execution(owner: bool) -> Token[bool]:
    return _OWNER_EXECUTION.set(owner)


def reset_owner_execution(token: Token[bool]) -> None:
    _OWNER_EXECUTION.reset(token)


async def complete_cleanup(work: Awaitable[T]) -> T:
    """Await teardown to completion across task and cancel-scope cancellation."""
    with anyio.CancelScope(shield=True):
        cleanup = asyncio.ensure_future(work)
        interrupted = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                interrupted = True
                current = asyncio.current_task()
                if current is not None:
                    current.uncancel()
        result = cleanup.result()
        if interrupted:
            raise asyncio.CancelledError()
        return result
    raise asyncio.CancelledError()


class RunScope:
    """Share lifetime and stop state across a run and its descendants."""

    def __init__(self) -> None:
        self._children: set[asyncio.Task[object]] = set()
        self._child_parents: dict[
            asyncio.Task[object], asyncio.Task[object] | None
        ] = {}
        self._stop_error: RunStopError | None = None
        self._closed = False
        self._end_owner_authority: Callable[[], None] | None = None
        self._delegated_credentials = False

    @property
    def delegated_credentials(self) -> bool:
        return self._delegated_credentials

    def set_delegated_credentials(self, delegated: bool) -> None:
        self._delegated_credentials = delegated

    def set_owner_authority_end(self, callback: Callable[[], None]) -> None:
        self._end_owner_authority = callback

    def end_owner_authority(self) -> None:
        if _OWNER_EXECUTION.get() and self._end_owner_authority is not None:
            self._end_owner_authority()

    @classmethod
    def current(cls) -> RunScope | None:
        """Return the scope of the run executing on this context, if any."""

        return _CURRENT_RUN_SCOPE.get()

    @classmethod
    @contextmanager
    def open(cls) -> Iterator[RunScope]:
        """Join an active scope; never inherit a closed scope from an abandoned stream."""

        parent = _CURRENT_RUN_SCOPE.get()
        if parent is not None and not parent.closed:
            yield parent
            return
        scope = cls()
        token = _CURRENT_RUN_SCOPE.set(scope)
        try:
            yield scope
        finally:
            # Finalization in another context can make reset fail; close first.
            scope.close()
            try:
                _CURRENT_RUN_SCOPE.reset(token)
            except ValueError:
                # A closed scope cannot be joined even if its context survives.
                logger.debug("[RUN] run scope reset skipped: foreign context")

    def close(self) -> None:
        """End the scope and cancel whatever it still has running."""

        self._closed = True
        self.cancel_children()

    @property
    def closed(self) -> bool:
        return self._closed

    def record_stop(self, error: RunStopError) -> None:
        """Preserve the first stop so parent and sibling execution cannot continue."""

        if self._stop_error is None:
            self._stop_error = error

    def raise_if_stopped(self) -> None:
        """Raise a fresh stop error to avoid accumulating shared tracebacks."""

        error = self._stop_error
        if error is None:
            return
        try:
            raise type(error)()
        except TypeError:
            # Preserve stops from subclasses with required constructor arguments.
            raise error from None

    async def next_event(self, iterator: AsyncIterator[T]) -> T:
        """Check authority before advancing the engine stream."""

        self.raise_if_stopped()
        return await iterator.__anext__()

    def register_child(self, task: asyncio.Task[object]) -> None:
        """Track a child task so the run can cancel it when it ends."""

        self._children.add(task)
        self._child_parents[task] = cast(
            asyncio.Task[object] | None, asyncio.current_task()
        )

        def _discard(done: asyncio.Task[object]) -> None:
            self._children.discard(done)
            self._child_parents.pop(done, None)

        task.add_done_callback(_discard)

    def cancel_children(self) -> None:
        """Cancel every child still in flight. Safe to call more than once."""

        current = asyncio.current_task()
        for task in tuple(self._children):
            if task is current:
                continue
            if not task.done() and not task.cancelling():
                task.cancel()

    async def cancel_and_wait(self) -> None:
        """Finish registered work before the owner releases the run."""
        current = asyncio.current_task()
        while pending := tuple(
            task for task in self._children if task is not current and not task.done()
        ):
            for task in pending:
                if not task.cancelling():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    def cancel_descendants(self) -> None:
        """Cancel work started beneath the current task, never its ancestors."""
        current = cast(asyncio.Task[object] | None, asyncio.current_task())
        if current is None:
            return
        descendants = {current}
        changed = True
        while changed:
            changed = False
            for task, parent in tuple(self._child_parents.items()):
                if task not in descendants and parent in descendants:
                    descendants.add(task)
                    changed = True
        descendants.discard(current)
        for task in descendants:
            if not task.done() and not task.cancelling():
                task.cancel()


def register_run_child(task: asyncio.Task[object]) -> bool:
    """Track spawned work for cancellation; return False outside a run scope."""

    scope = RunScope.current()
    if scope is None:
        return False
    scope.register_child(task)
    return True


__all__ = [
    "RunScope",
    "register_run_child",
    "stop_reason_of",
    "terminal_stop_event",
]
