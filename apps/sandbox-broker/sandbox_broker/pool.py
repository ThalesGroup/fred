# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Single-process pool of disposable, single-use sandbox workloads."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic

from fred_sdk.contracts.sandbox import SandboxError

from .backend import SandboxBackend, SandboxLease, SandboxPrepareLeak
from .config import BrokerSettings

logger = logging.getLogger(__name__)
_MAX_IDLE_SECONDS = 3000
_POOL_CHECK_SECONDS = 30


class WarmPool:
    def __init__(self, backend: SandboxBackend, settings: BrokerSettings) -> None:
        self.backend = backend
        self.settings = settings
        self.target_size = settings.warm_pool_size
        self._ready: asyncio.Queue[SandboxLease] = asyncio.Queue()
        self._active: set[SandboxLease] = set()
        self._leaked: set[SandboxLease] = set()
        self._total = 0
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    async def start(self) -> None:
        await self.backend.preflight()
        try:
            for _ in range(self.target_size):
                self._total += 1
                try:
                    lease = await self.backend.prepare()
                except SandboxPrepareLeak as exc:
                    self._leaked.add(exc.lease)
                    raise
                except BaseException:
                    self._total -= 1
                    raise
                self._ready.put_nowait(lease)
        except BaseException:
            await self.close()
            raise
        self._worker = asyncio.create_task(self._replenish())

    async def acquire(self) -> SandboxLease:
        if self._closed:
            raise SandboxError("unavailable")
        try:
            lease = self._ready.get_nowait()
        except asyncio.QueueEmpty:
            if self._total >= self.settings.max_sandboxes:
                raise SandboxError("busy") from None
            self._total += 1
            try:
                if not self.settings.cold_start_on_miss:
                    ready_state = getattr(self.backend, "warm_state", None)
                    if ready_state is None or (await ready_state())[0] < 1:
                        raise SandboxError("busy") from None
                lease = await self.backend.prepare()
            except SandboxPrepareLeak as exc:
                self._leaked.add(exc.lease)
                logger.exception("Sandbox preparation cleanup is uncertain")
                raise
            except BaseException:
                self._total -= 1
                raise
        self._active.add(lease)
        self._wake.set()
        return lease

    async def release(self, lease: SandboxLease) -> None:
        try:
            await self.backend.dispose(lease)
        except Exception:
            self._leaked.add(lease)
            logger.exception("Failed to dispose sandbox workload")
        else:
            self._total -= 1
        finally:
            self._active.discard(lease)
            self._wake.set()

    def schedule_release(self, lease: SandboxLease) -> None:
        task = asyncio.create_task(self.release(lease))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def configure_warm_capacity(self, target: int) -> None:
        if not 0 <= target <= self.settings.max_sandboxes:
            raise ValueError("Warm capacity exceeds the operator limit")
        if target == 0 and not self.settings.cold_start_on_miss:
            raise ValueError("Zero warm capacity requires on-demand provisioning")
        self.target_size = target
        while self._ready.qsize() > target:
            self.schedule_release(self._ready.get_nowait())
        self._wake.set()

    async def close(self) -> None:
        self._closed = True
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        if self._cleanup_tasks:
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
        leases = list(self._active | self._leaked)
        while not self._ready.empty():
            leases.append(self._ready.get_nowait())
        for lease in leases:
            try:
                await self.backend.dispose(lease)
            except Exception:
                logger.exception("Failed to dispose sandbox workload at shutdown")

    async def _replenish(self) -> None:
        while not self._closed:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=_POOL_CHECK_SECONDS)
            except TimeoutError:
                pass
            self._wake.clear()
            await self._retry_leaked()
            await self._retire_expired()
            while (
                not self._closed
                and self._ready.qsize() < self.target_size
                and self._total < self.settings.max_sandboxes
            ):
                self._total += 1
                try:
                    lease = await self.backend.prepare()
                except asyncio.CancelledError:
                    self._total -= 1
                    raise
                except SandboxPrepareLeak as exc:
                    self._leaked.add(exc.lease)
                    logger.exception("Sandbox preparation cleanup is uncertain")
                    await asyncio.sleep(2)
                    self._wake.set()
                    break
                except Exception:
                    self._total -= 1
                    logger.exception("Failed to replenish sandbox pool")
                    await asyncio.sleep(2)
                    self._wake.set()
                    break
                if self._ready.qsize() >= self.target_size:
                    await self.release(lease)
                else:
                    self._ready.put_nowait(lease)

    async def _retry_leaked(self) -> None:
        for lease in list(self._leaked):
            try:
                await self.backend.dispose(lease)
            except Exception:
                logger.exception("Failed to retry sandbox workload cleanup")
            else:
                self._leaked.discard(lease)
                self._total -= 1

    async def _retire_expired(self) -> None:
        for _ in range(self._ready.qsize()):
            lease = self._ready.get_nowait()
            if monotonic() - lease.prepared_at < _MAX_IDLE_SECONDS:
                self._ready.put_nowait(lease)
                continue
            try:
                await self.backend.dispose(lease)
            except Exception:
                self._leaked.add(lease)
                logger.exception("Failed to retire expired sandbox workload")
            else:
                self._total -= 1

    @property
    def ready_count(self) -> int:
        return self._ready.qsize()

    @property
    def allocated_count(self) -> int:
        return self._total
