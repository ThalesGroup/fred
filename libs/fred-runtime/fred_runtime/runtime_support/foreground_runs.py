"""Pod-local execution ownership, stream attachment and bounded replay."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from fred_runtime.common.outbound_credentials import RunRecord
from fred_runtime.runtime_support.authority import RunStopError
from fred_runtime.runtime_support.run_budget import terminal_stop_event

Outcome = Literal["succeeded", "failed", "cancelled"]
logger = logging.getLogger(__name__)


class AttachmentError(Exception):
    def __init__(self, status_code: int, reason: str) -> None:
        self.status_code = status_code
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ReplayLimits:
    grace_seconds: float = 60.0
    max_events: int = 512
    max_bytes: int = 2 * 1024 * 1024
    max_runs: int = 128

    def __post_init__(self) -> None:
        if self.grace_seconds < 0:
            raise ValueError("Replay grace must not be negative.")
        if self.max_events < 1 or self.max_bytes < 1 or self.max_runs < 1:
            raise ValueError("Replay bounds must be positive.")


class ForegroundRun:
    def __init__(
        self,
        record: RunRecord,
        stream: AsyncIterator[str],
        *,
        limits: ReplayLimits,
        on_end: Callable[[Outcome, str | None], Awaitable[None]],
        on_cancel: Callable[[str], None],
    ) -> None:
        self.record = record
        self._stream = stream
        self._limits = limits
        self._on_end = on_end
        self._on_cancel = on_cancel
        self._events: deque[tuple[int, str, int]] = deque()
        self._bytes = 0
        self._next_sequence = 0
        self._condition = asyncio.Condition()
        self._finish_lock = asyncio.Lock()
        self._attachment: object | None = None
        self._grace: asyncio.Task[None] | None = None
        self._producer: asyncio.Task[None] | None = None
        self._deadline: asyncio.Task[None] | None = None
        self._retention: asyncio.Task[None] | None = None
        self._cancel_reason: str | None = None
        self._producer_entered = False
        self._finalized = False
        self._done = False
        self._expired = False

    def start(self) -> None:
        if self._producer is not None or self._done:
            raise RuntimeError("Foreground run already started.")
        self._producer = asyncio.create_task(self._produce())
        self._producer.add_done_callback(self._producer_done)
        self._deadline = asyncio.create_task(self._expire_ceiling())

    @property
    def removable(self) -> bool:
        return self._expired and self._attachment is None

    async def attach(self, after_sequence: int | None) -> AsyncIterator[str]:
        async with self._condition:
            if self._expired:
                raise AttachmentError(410, "run_expired")
            if self._attachment is not None:
                raise AttachmentError(409, "run_already_attached")
            cursor = -1 if after_sequence is None else after_sequence
            self._validate_cursor(cursor)
            lease = object()
            self._attachment = lease
            self._cancel_timer(self._grace)
            self._grace = asyncio.create_task(self._expire_grace(lease))
        return self._read(lease, cursor)

    def _validate_cursor(self, cursor: int) -> None:
        first = self._events[0][0] if self._events else self._next_sequence
        if cursor >= self._next_sequence or cursor < first - 1:
            raise AttachmentError(409, "replay_unavailable")

    async def _read(self, lease: object, cursor: int) -> AsyncIterator[str]:
        async with self._condition:
            if self._attachment is not lease:
                raise AttachmentError(410, "run_expired")
            self._cancel_timer(self._grace)
            self._grace = None
        try:
            while True:
                async with self._condition:
                    self._validate_cursor(cursor)
                    available = [
                        (sequence, frame)
                        for sequence, frame, _ in self._events
                        if sequence > cursor
                    ]
                    if not available:
                        if self._done:
                            return
                        await self._condition.wait()
                        continue
                for sequence, frame in available:
                    cursor = sequence
                    yield frame
        finally:
            async with self._condition:
                if self._attachment is lease:
                    self._attachment = None
                    if not self._done:
                        self._grace = asyncio.create_task(self._expire_grace(None))

    async def cancel(self, reason: str = "cancelled", *, grace: bool = False) -> None:
        async with self._condition:
            if self._finalized:
                return
            if self._cancel_reason is None:
                self._cancel_reason = reason
                self._expired = self._expired or grace
                try:
                    self._on_cancel(reason)
                except Exception:
                    logger.warning(
                        "event=foreground_cancel outcome=failed reason=state_update_failed"
                    )
            producer = self._producer
        if producer is None:
            await self._finish(*self._cancel_outcome(), append_stop=True)
        elif producer is not asyncio.current_task():
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
            if not self._finalized:
                await self._finish(*self._cancel_outcome(), append_stop=True)

    async def _expire_grace(self, lease: object | None) -> None:
        await asyncio.sleep(self._limits.grace_seconds)
        async with self._condition:
            if self._grace is not asyncio.current_task():
                return
            if lease is not None and self._attachment is lease:
                self._attachment = None
            elif lease is not self._attachment:
                return
        await self.cancel(grace=True)

    async def _expire_ceiling(self) -> None:
        seconds = self.record.run_ceiling_seconds or 900.0
        remaining = self.record.started_monotonic + seconds - time.monotonic()
        await asyncio.sleep(max(0, remaining))
        await self.cancel("run_ceiling_reached")

    async def _expire_retention(self) -> None:
        await asyncio.sleep(self._limits.grace_seconds)
        async with self._condition:
            self._expired = True
            self._condition.notify_all()

    async def _append(self, payload: dict[str, Any]) -> None:
        sequence = self._next_sequence
        sequenced = dict(payload)
        sequenced["sequence"] = sequence
        frame = f"id: {sequence}\ndata: {json.dumps(sequenced, ensure_ascii=False)}\n\n"
        size = len(frame.encode("utf-8"))
        if size > self._limits.max_bytes:
            raise AttachmentError(409, "event_exceeds_replay_bound")
        async with self._condition:
            self._next_sequence += 1
            self._events.append((sequence, frame, size))
            self._bytes += size
            while (
                len(self._events) > self._limits.max_events
                or self._bytes > self._limits.max_bytes
            ):
                self._bytes -= self._events.popleft()[2]
            self._condition.notify_all()
        await asyncio.sleep(0)

    def _producer_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled() and not self._producer_entered and not self._finalized:
            asyncio.create_task(self._finish(*self._cancel_outcome(), append_stop=True))

    def _cancel_outcome(self) -> tuple[Outcome, str | None]:
        reason = self._cancel_reason or "cancelled"
        outcome: Outcome = "cancelled" if reason == "cancelled" else "failed"
        return outcome, reason

    async def _produce(self) -> None:
        self._producer_entered = True
        outcome: Outcome = "failed"
        reason: str | None = None
        awaiting_human = False
        terminal_seen = False
        try:
            async for frame in self._stream:
                data = "\n".join(
                    line[5:].lstrip()
                    for line in frame.splitlines()
                    if line.startswith("data:")
                )
                if not data:
                    continue
                payload = json.loads(data)
                kind = payload.get("kind")
                if kind == "awaiting_human":
                    awaiting_human = True
                elif kind == "execution_error":
                    awaiting_human = False
                    reason = payload.get("reason")
                    outcome = "cancelled" if reason == "cancelled" else "failed"
                    terminal_seen = True
                elif kind == "final":
                    outcome = "succeeded"
                    terminal_seen = True
                await self._append(payload)
            if awaiting_human:
                await asyncio.Event().wait()
            elif not terminal_seen:
                reason = "execution_failed"
                await self._append(
                    {
                        "kind": "execution_error",
                        "message": "The stream ended.",
                        "reason": None,
                    }
                )
        except asyncio.CancelledError:
            if not terminal_seen:
                outcome, reason = self._cancel_outcome()
                await self._append_stop(reason)
        except Exception:
            if not terminal_seen:
                outcome, reason = "failed", "execution_failed"
                try:
                    await self._append(
                        {
                            "kind": "execution_error",
                            "message": "The stream ended.",
                            "reason": None,
                        }
                    )
                except Exception:
                    logger.warning(
                        "event=foreground_replay outcome=failed reason=terminal_buffer_unavailable"
                    )
        finally:
            await self._finish(outcome, reason)

    async def _append_stop(self, reason: str | None) -> None:
        stop = RunStopError()
        stop.reason = reason or "cancelled"
        try:
            await self._append(terminal_stop_event(stop).model_dump(mode="json"))
        except Exception:
            logger.warning(
                "event=foreground_replay outcome=failed reason=stop_buffer_unavailable"
            )

    async def _finish(
        self,
        outcome: Outcome,
        reason: str | None,
        *,
        append_stop: bool = False,
    ) -> None:
        async with self._finish_lock:
            if self._finalized:
                return
            self._finalized = True
            if append_stop:
                await self._append_stop(reason)
            close = getattr(self._stream, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    logger.warning(
                        "event=foreground_close outcome=failed reason=stream_close_failed"
                    )
            try:
                await self._on_end(outcome, reason)
            except Exception:
                # Terminal reporting is best-effort and must not strand the
                # local state machine or surface an unhandled task exception.
                logger.warning(
                    "event=foreground_close outcome=failed reason=report_unavailable"
                )
            finally:
                async with self._condition:
                    self._done = True
                    self._condition.notify_all()
                for timer in (self._grace, self._deadline):
                    self._cancel_timer(timer)
                if not self._expired:
                    self._retention = asyncio.create_task(self._expire_retention())

    @staticmethod
    def _cancel_timer(task: asyncio.Task[None] | None) -> None:
        if task is not None and task is not asyncio.current_task():
            task.cancel()


class ForegroundRunRegistry:
    def __init__(self, limits: ReplayLimits) -> None:
        self.limits = limits
        self._runs: dict[str, ForegroundRun] = {}
        self._expired: deque[str] = deque(maxlen=limits.max_runs)

    def get(self, run_id: str) -> ForegroundRun:
        run = self._runs.get(run_id)
        if run is not None and run.removable:
            del self._runs[run_id]
            self._expired.append(run_id)
            run = None
        if run is not None:
            return run
        if run_id in self._expired:
            raise AttachmentError(410, "run_expired")
        raise AttachmentError(404, "run_not_found")

    def add(self, run: ForegroundRun) -> None:
        for run_id, existing in tuple(self._runs.items()):
            if existing.removable:
                del self._runs[run_id]
                self._expired.append(run_id)
        if len(self._runs) >= self.limits.max_runs:
            asyncio.create_task(run.cancel("foreground_capacity_exceeded"))
            raise AttachmentError(503, "foreground_capacity_exceeded")
        if run.record.run_id in self._runs:
            asyncio.create_task(run.cancel("run_already_admitted"))
            raise AttachmentError(409, "run_already_admitted")
        self._runs[run.record.run_id] = run

    async def close(self) -> None:
        await asyncio.gather(*(run.cancel() for run in self._runs.values()))
        for run in self._runs.values():
            run._cancel_timer(run._retention)
        self._runs.clear()
        self._expired.clear()
