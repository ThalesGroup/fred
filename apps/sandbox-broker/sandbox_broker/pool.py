# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Single-process capacity guard for on-demand sandbox workloads."""

from __future__ import annotations

import asyncio
import logging

from fred_sdk.contracts.sandbox import SandboxError

from .backend import SandboxBackend, SandboxLease, SandboxPrepareLeak
from .config import BrokerSettings
from .mounts import revoke_view

logger = logging.getLogger(__name__)
_CLEANUP_CHECK_SECONDS = 30


class OnDemandCapacity:
    def __init__(self, backend: SandboxBackend, settings: BrokerSettings) -> None:
        self.backend = backend
        self.settings = settings
        self._active: set[SandboxLease] = set()
        self._leaked: set[SandboxLease] = set()
        self._total = 0
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    async def start(self) -> None:
        await self.backend.preflight()
        recover = getattr(self.backend, "recover", None)
        if recover is not None:
            await recover()
        self._worker = asyncio.create_task(self._retry_cleanup())

    async def acquire(self, view_key: str | None = None) -> SandboxLease:
        if self._closed:
            raise SandboxError("unavailable")
        if self._total >= self.settings.max_sandboxes:
            raise SandboxError("busy")
        self._total += 1
        try:
            lease = await self.backend.prepare(view_key)
        except SandboxPrepareLeak as exc:
            self._leaked.add(exc.lease)
            self._wake.set()
            logger.exception("Sandbox preparation cleanup is uncertain")
            raise
        except BaseException:
            self._total -= 1
            raise
        self._active.add(lease)
        return lease

    async def release(self, lease: SandboxLease) -> None:
        try:
            await self._dispose(lease)
        except Exception:
            self._leaked.add(lease)
            self._wake.set()
            logger.exception("Failed to dispose sandbox workload")
        else:
            self._total -= 1
        finally:
            self._active.discard(lease)

    def schedule_release(self, lease: SandboxLease) -> None:
        task = asyncio.create_task(self.release(lease))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

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
        for lease in leases:
            try:
                await self._dispose(lease)
            except Exception:
                logger.exception("Failed to dispose sandbox workload at shutdown")

    async def _retry_cleanup(self) -> None:
        while not self._closed:
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=_CLEANUP_CHECK_SECONDS
                )
            except TimeoutError:
                pass
            self._wake.clear()
            await self._retry_leaked()

    async def _retry_leaked(self) -> None:
        for lease in list(self._leaked):
            try:
                await self._dispose(lease)
            except Exception:
                logger.exception("Failed to retry sandbox workload cleanup")
            else:
                self._leaked.discard(lease)
                self._total -= 1

    async def _dispose(self, lease: SandboxLease) -> None:
        revoke_error: Exception | None = None
        if lease.view_key is not None:
            try:
                await revoke_view(self.settings, lease.view_key)
            except Exception as exc:
                revoke_error = exc
        await self.backend.dispose(lease)
        if revoke_error is not None:
            raise revoke_error

    @property
    def allocated_count(self) -> int:
        return self._total
