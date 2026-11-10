# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Backend-neutral lease contract; each prepared workload is single-use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult


@dataclass(frozen=True, slots=True)
class SandboxLease:
    id: str
    target: str
    view_key: str | None = None


class SandboxPrepareLeak(SandboxError):
    def __init__(self, lease: SandboxLease) -> None:
        super().__init__("backend_failed")
        self.lease = lease


class SandboxBackend(Protocol):
    async def preflight(self) -> None: ...

    async def prepare(self, view_key: str | None = None) -> SandboxLease: ...

    async def execute(
        self, lease: SandboxLease, request: SandboxRequest
    ) -> SandboxResult: ...

    async def dispose(self, lease: SandboxLease) -> None: ...
