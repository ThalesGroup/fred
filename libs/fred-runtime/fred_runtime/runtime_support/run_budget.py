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
Run-level limits shared by both engines, and the terminal event a stopped run
ends with.

A run ceiling is not a per-call timeout: a per-call timeout bounds one outbound
call, this bounds the whole run, children included. Both engines open one
`RunScope` per run and end the run through `terminal_stop_event`, so the
message a stopped run shows is written once, here, and never assembled from an
upstream error.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, TypeVar, cast

from fred_sdk.contracts.runtime import RuntimeErrorEvent, RuntimeStopReason

from .authority import ChildLimitReachedError, RunCeilingReachedError, RunStopError

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Wall-clock budget for one attended run, in seconds. Attended means a person
#: is waiting: past a quarter of an hour the answer has no reader left, and the
#: run is only holding a slot and a credential open.
DEFAULT_RUN_CEILING_SECONDS: Final[float] = 900.0

#: How many children (child agents, team members, parallel members) one run may
#: have in flight at once.
DEFAULT_MAX_CONCURRENT_CHILDREN: Final[int] = 8

# One bounded, platform-owned sentence per reason. The upstream error text is
# never folded in — copying a receiver's body into this message is exactly the
# leak the redaction rule exists to prevent.
_STOP_MESSAGES: Final[dict[RuntimeStopReason, str]] = {
    RuntimeStopReason.AUTHORITY_LOST: (
        "This run was stopped because it is no longer authorized to act for you."
    ),
    RuntimeStopReason.RUN_CEILING_REACHED: (
        "This run was stopped because it reached its maximum duration."
    ),
    RuntimeStopReason.CANCELLED: "This run was stopped.",
    RuntimeStopReason.DELEGATION_UNAVAILABLE: (
        "This run was stopped because delegated access is unavailable."
    ),
    RuntimeStopReason.CHILD_LIMIT_REACHED: (
        "This run was stopped because it reached its concurrent child limit."
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


@dataclass(frozen=True)
class RunLimits:
    """Per-run budget. Per-call timeouts are configured separately and are not
    affected by these values."""

    wall_clock_seconds: float = DEFAULT_RUN_CEILING_SECONDS
    max_concurrent_children: int = DEFAULT_MAX_CONCURRENT_CHILDREN

    def __post_init__(self) -> None:
        if not math.isfinite(self.wall_clock_seconds) or self.wall_clock_seconds <= 0:
            raise ValueError("The run ceiling must be finite and positive.")
        if self.max_concurrent_children < 1:
            raise ValueError("The concurrent child limit must be positive.")


_default_limits: RunLimits = RunLimits()
_agent_limits_resolver: Callable[[str | None], RunLimits | None] | None = None


def configure_run_limits(
    *,
    wall_clock_seconds: float = DEFAULT_RUN_CEILING_SECONDS,
    max_concurrent_children: int = DEFAULT_MAX_CONCURRENT_CHILDREN,
) -> None:
    """Set the deployment-wide run limits. Called once at pod startup from the
    pod configuration; the defaults above apply until it is."""

    global _default_limits
    _default_limits = RunLimits(
        wall_clock_seconds=wall_clock_seconds,
        max_concurrent_children=max_concurrent_children,
    )


def set_agent_run_limits_resolver(
    resolver: Callable[[str | None], RunLimits | None] | None,
) -> None:
    """Install the per-agent override hook: it receives the agent id and returns
    limits for that agent, or None to keep the deployment-wide ones."""

    global _agent_limits_resolver
    _agent_limits_resolver = resolver


def resolve_run_limits(agent_id: str | None) -> RunLimits:
    """Return the limits in force for one agent."""

    resolver = _agent_limits_resolver
    if resolver is not None:
        override = resolver(agent_id)
        if override is not None:
            return override
    return _default_limits


_CURRENT_RUN_SCOPE: ContextVar[RunScope | None] = ContextVar(
    "fred_current_run_scope", default=None
)
_CHILD_SLOT_DEPTH: ContextVar[int] = ContextVar("fred_child_slot_depth", default=0)


class RunScope:
    """
    The wall-clock budget and the children of one run.

    A nested engine run (a child agent, a team member) joins the scope already
    open instead of opening its own: a child must not outlive the run that
    started it, nor be given a second budget of its own.
    """

    def __init__(
        self,
        limits: RunLimits,
        *,
        clock: Callable[[], float] = time.monotonic,
        started_at: float | None = None,
    ) -> None:
        self._limits = limits
        self._clock = clock
        self._deadline = (
            clock() if started_at is None else started_at
        ) + limits.wall_clock_seconds
        self._children: set[asyncio.Task[object]] = set()
        self._child_parents: dict[
            asyncio.Task[object], asyncio.Task[object] | None
        ] = {}
        self._slots = asyncio.Semaphore(max(1, limits.max_concurrent_children))
        self._stop_error: RunStopError | None = None
        self._closed = False

    @classmethod
    def current(cls) -> RunScope | None:
        """Return the scope of the run executing on this context, if any."""

        return _CURRENT_RUN_SCOPE.get()

    @classmethod
    @contextmanager
    def open(
        cls,
        *,
        agent_id: str | None,
        limits: RunLimits | None = None,
        started_at: float | None = None,
    ) -> Iterator[RunScope]:
        """
        Open the scope for one run, or join the one already running.

        A scope that has been closed is never joined: an abandoned stream can
        leave its scope visible on the consumer's context long after its run
        ended, and a later run must not inherit that run's spent deadline or
        its recorded stop.
        """

        parent = _CURRENT_RUN_SCOPE.get()
        if parent is not None and not parent.closed:
            yield parent
            return
        scope = cls(limits or resolve_run_limits(agent_id), started_at=started_at)
        token = _CURRENT_RUN_SCOPE.set(scope)
        try:
            yield scope
        finally:
            # Close before resetting: an async generator finalized from another
            # context makes the reset fail, and nothing after it would run.
            scope.close()
            try:
                _CURRENT_RUN_SCOPE.reset(token)
            except ValueError:
                # Finalized on a different context than the one that set it.
                # `closed` is what keeps a later run from joining this scope.
                logger.debug("[RUN] run scope reset skipped: foreign context")

    def close(self) -> None:
        """End the scope and cancel whatever it still has running."""

        self._closed = True
        self.cancel_children()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def limits(self) -> RunLimits:
        return self._limits

    def remaining_seconds(self) -> float:
        """Seconds left in the budget; zero or less once it is exhausted."""

        return self._deadline - self._clock()

    def raise_if_exhausted(self) -> None:
        if self.remaining_seconds() <= 0:
            raise RunCeilingReachedError()

    def record_stop(self, error: RunStopError) -> None:
        """Remember that this run was stopped. A child ends on its own terminal
        event, so without this the parent would read the child's stop as an
        ordinary result and carry on calling out for a run that is over."""

        if self._stop_error is None:
            self._stop_error = error

    @property
    def stopped(self) -> bool:
        return self._stop_error is not None

    def raise_if_stopped(self) -> None:
        """
        End this run if it has already been stopped.

        A fresh instance per site: re-raising one shared object accumulates a
        traceback that belongs to none of the places it was raised from.
        """

        error = self._stop_error
        if error is None:
            return
        try:
            raise type(error)()
        except TypeError:
            # A subclass with a different constructor: the reason still travels
            # on the original, and ending the run matters more than the copy.
            raise error from None

    def _ceiling_or_reraise(self) -> None:
        """
        Decide who a timeout belongs to.

        A timeout raised while the run still has budget came from inside the
        step — a per-call timeout — and is not this run's to claim: reporting it
        as the ceiling would hide a slow receiver behind a wrong reason.
        """

        self.raise_if_exhausted()

    async def next_event(self, iterator: AsyncIterator[T]) -> T:
        """
        Pull the next item of an engine stream under the run's remaining budget.

        `asyncio.wait_for` is `asyncio.timeout` around the await: the step runs
        on this task, and the deadline cancels this task where it is suspended —
        inside the step — then turns that cancellation into `TimeoutError` here.
        A step that swallows the cancellation instead returns its value, since
        only a `CancelledError` reaching the timeout is converted. That overrun
        is accepted rather than run the step in a task of its own, which would
        detach it from the run's context and leave it working past the ceiling:
        the run ends on the exhaustion check at the top of the next call, one
        step later at most, and no further step is started.
        """

        self.raise_if_stopped()
        self.raise_if_exhausted()
        try:
            return await asyncio.wait_for(
                iterator.__anext__(), timeout=self.remaining_seconds()
            )
        except TimeoutError:
            self._ceiling_or_reraise()
            raise

    async def next_queued(self, queue: asyncio.Queue[T]) -> T:
        """
        Take the next queued event under the run's remaining budget.

        No stop check here: this waits on work that is already running and has
        its own stop handling, so raising here would end the run a second time.
        The check belongs where the run is about to do more work.
        """

        self.raise_if_exhausted()
        try:
            return await asyncio.wait_for(queue.get(), timeout=self.remaining_seconds())
        except TimeoutError:
            self._ceiling_or_reraise()
            raise

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

        for task in tuple(self._children):
            if not task.done():
                task.cancel()

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
            if not task.done():
                task.cancel()

    @asynccontextmanager
    async def child_slot(self) -> AsyncIterator[None]:
        """Hold one of the run's concurrent-child slots for the block."""

        if _CHILD_SLOT_DEPTH.get() > 0 and self._slots.locked():
            raise ChildLimitReachedError()
        await self._slots.acquire()
        depth_token = _CHILD_SLOT_DEPTH.set(_CHILD_SLOT_DEPTH.get() + 1)
        try:
            self.raise_if_exhausted()
            yield
        finally:
            _CHILD_SLOT_DEPTH.reset(depth_token)
            self._slots.release()

    async def run_children(
        self, factories: Sequence[Callable[[], Awaitable[T]]]
    ) -> list[T]:
        """
        Run children concurrently, never more than the configured bound at once,
        and leave none behind: `asyncio.gather` reports the first failure while
        its siblings keep running, which for a stopped run means work still
        calling out under an authority the platform has just given up.
        """

        async def _in_slot(factory: Callable[[], Awaitable[T]]) -> T:
            async with self.child_slot():
                return await factory()

        tasks: list[asyncio.Task[T]] = [
            asyncio.ensure_future(_in_slot(factory)) for factory in factories
        ]
        for task in tasks:
            self.register_child(task)  # type: ignore[arg-type]
        try:
            return await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise


def register_run_child(task: asyncio.Task[object]) -> bool:
    """
    Register a task as a child of the run executing on this context.

    Call this wherever a run starts work in a task of its own — a spawned child
    agent, a team member — so that ending the run ends that work too. Work a run
    simply awaits inline needs no registration: cancelling the run's own step
    already unwinds it. Returns False when no run scope is open.
    """

    scope = RunScope.current()
    if scope is None:
        return False
    scope.register_child(task)
    return True


__all__ = [
    "DEFAULT_MAX_CONCURRENT_CHILDREN",
    "DEFAULT_RUN_CEILING_SECONDS",
    "RunLimits",
    "RunScope",
    "configure_run_limits",
    "register_run_child",
    "resolve_run_limits",
    "set_agent_run_limits_resolver",
    "stop_reason_of",
    "terminal_stop_event",
]
