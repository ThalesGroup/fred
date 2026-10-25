# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Conversation-bound workload leases with idle expiry."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from secrets import token_hex
from time import monotonic

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .backend import SandboxLease
from .pool import OnDemandCapacity

logger = logging.getLogger(__name__)
_SWEEP_SECONDS = 10


@dataclass(slots=True)
class _Session:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    view_key: str = field(default_factory=lambda: token_hex(32))
    lease: SandboxLease | None = None
    last_used: float = field(default_factory=monotonic)
    retire: bool = False


class ConversationPool:
    def __init__(
        self, pool: OnDemandCapacity, *, idle_seconds: int = 1200, max_sessions: int = 8
    ) -> None:
        self.pool = pool
        self.idle_seconds = idle_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, _Session] = {}
        self._lock = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._worker = asyncio.create_task(self._sweep_loop())

    async def view_key(self, key: str) -> str:
        while True:
            async with self._lock:
                entry = self._sessions.get(key)
                if entry is None:
                    if len(self._sessions) >= self.max_sessions:
                        raise SandboxError("busy")
                    entry = _Session()
                    self._sessions[key] = entry
            async with entry.lock:
                async with self._lock:
                    if self._sessions.get(key) is not entry:
                        continue
                if entry.retire or self._expired(entry):
                    await self._release(entry)
                    entry.view_key = token_hex(32)
                    entry.retire = False
                    entry.last_used = monotonic()
                return entry.view_key

    async def execute(self, key: str, request: SandboxRequest) -> SandboxResult:
        while True:
            async with self._lock:
                entry = self._sessions.get(key)
                if entry is None:
                    if len(self._sessions) >= self.max_sessions:
                        raise SandboxError("busy")
                    entry = _Session()
                    self._sessions[key] = entry
            async with entry.lock:
                async with self._lock:
                    if self._sessions.get(key) is not entry:
                        continue
                if entry.retire:
                    await self._release(entry)
                    async with self._lock:
                        if self._sessions.get(key) is entry:
                            del self._sessions[key]
                    continue
                if entry.lease is not None and self._expired(entry):
                    await self._release(entry)
                    entry.view_key = token_hex(32)
                elif entry.lease is None and self._expired(entry):
                    entry.view_key = token_hex(32)
                    entry.last_used = monotonic()
                try:
                    if entry.lease is None:
                        entry.lease = await self.pool.acquire(entry.view_key)
                    renew = getattr(self.pool.backend, "renew", None)
                    if renew is not None:
                        await renew(
                            entry.lease,
                            self.idle_seconds
                            + self.pool.settings.execution_timeout_seconds
                            + 3,
                        )
                    result = await asyncio.wait_for(
                        self.pool.backend.execute(entry.lease, request),
                        timeout=self.pool.settings.execution_timeout_seconds + 3,
                    )
                    if result.timed_out:
                        await self._release(entry)
                        async with self._lock:
                            if self._sessions.get(key) is entry:
                                del self._sessions[key]
                        return result
                    if renew is not None:
                        await renew(entry.lease, self.idle_seconds)
                    entry.last_used = monotonic()
                    if entry.retire:
                        await self._release(entry)
                        async with self._lock:
                            if self._sessions.get(key) is entry:
                                del self._sessions[key]
                    return result
                except BaseException:
                    await self._release(entry)
                    async with self._lock:
                        if self._sessions.get(key) is entry:
                            del self._sessions[key]
                    raise

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        for key, entry in list(self._sessions.items()):
            async with entry.lock:
                await self._release(entry)
                self._sessions.pop(key, None)

    async def configure(self, *, idle_seconds: int, max_sessions: int) -> None:
        changed = idle_seconds != self.idle_seconds
        self.idle_seconds = idle_seconds
        self.max_sessions = max_sessions
        await self._evict_excess()
        if not changed:
            return
        renew = getattr(self.pool.backend, "renew", None)
        for key, entry in list(self._sessions.items()):
            if entry.lock.locked():
                continue
            async with entry.lock:
                if self._expired(entry):
                    await self._release(entry)
                    async with self._lock:
                        if self._sessions.get(key) is entry:
                            del self._sessions[key]
                elif entry.lease is not None and renew is not None:
                    remaining = max(
                        1, int(self.idle_seconds - (monotonic() - entry.last_used))
                    )
                    try:
                        await renew(entry.lease, remaining)
                    except Exception:
                        logger.exception("Unable to renew conversation sandbox expiry")
                        await self._release(entry)
                        async with self._lock:
                            if self._sessions.get(key) is entry:
                                del self._sessions[key]

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(_SWEEP_SECONDS)
            await self.sweep()

    async def sweep(self) -> None:
        for key, entry in list(self._sessions.items()):
            if entry.lock.locked() or not self._expired(entry):
                continue
            async with entry.lock:
                if not self._expired(entry):
                    continue
                await self._release(entry)
                async with self._lock:
                    if self._sessions.get(key) is entry:
                        del self._sessions[key]
        await self._evict_excess()

    async def _evict_excess(self) -> None:
        excess = len(self._sessions) - self.max_sessions
        for key, entry in sorted(
            self._sessions.items(), key=lambda item: item[1].last_used
        ):
            if excess <= 0:
                return
            if entry.lock.locked():
                entry.retire = True
                excess -= 1
                continue
            async with entry.lock:
                async with self._lock:
                    if self._sessions.get(key) is not entry:
                        continue
                    del self._sessions[key]
                await self._release(entry)
                excess -= 1

    async def _release(self, entry: _Session) -> None:
        lease = entry.lease
        entry.lease = None
        if lease is not None:
            self.pool.schedule_release(lease)

    def _expired(self, entry: _Session) -> bool:
        return monotonic() - entry.last_used >= self.idle_seconds

    @property
    def active_count(self) -> int:
        return sum(entry.lease is not None for entry in self._sessions.values())
