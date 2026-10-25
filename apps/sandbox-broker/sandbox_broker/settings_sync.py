# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Apply admin policy without changing operator isolation controls."""

from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import BrokerSettings
from .sessions import ConversationPool
from .shared_sessions import SharedConversationPool

_REFRESH_SECONDS = 30
logger = logging.getLogger(__name__)


class _AdminPolicy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    idle_minutes: int = Field(ge=1, le=120)
    max_active_sessions: int = Field(ge=1, le=1000)


class SettingsSync:
    def __init__(
        self,
        settings: BrokerSettings,
        sessions: ConversationPool | SharedConversationPool,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.sessions = sessions
        self._client = httpx.AsyncClient(transport=transport, timeout=5)
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self.settings.settings_url:
            self._worker = asyncio.create_task(self._loop())

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    async def refresh(self) -> None:
        if not self.settings.settings_url or not self.settings.settings_token:
            return
        response = await self._client.get(
            self.settings.settings_url,
            headers={"Authorization": f"Bearer {self.settings.settings_token}"},
        )
        response.raise_for_status()
        policy = _AdminPolicy.model_validate(response.json())
        await self.sessions.configure(
            idle_seconds=policy.idle_minutes * 60,
            max_sessions=min(policy.max_active_sessions, self.settings.max_sandboxes),
        )

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unable to refresh sandbox admin settings")
            await asyncio.sleep(_REFRESH_SECONDS)
