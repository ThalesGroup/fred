from __future__ import annotations

import asyncio
import logging
from typing import Optional

from temporalio.client import Client

from fred_core.common.structures import TemporalSchedulerConfig

logger = logging.getLogger(__name__)


class TemporalClientProvider:
    def __init__(self, config: TemporalSchedulerConfig) -> None:
        self._config = config
        self._client: Optional[Client] = None
        self._lock = asyncio.Lock()

    async def get_client(self) -> Client:
        """
        Lazy singleton connection. Safe under concurrent calls.
        """
        if self._client is not None:
            return self._client

        async with self._lock:
            if self._client is not None:
                return self._client

            logger.info(
                "[TEMPORAL] Connecting: host=%s namespace=%s",
                self._config.host,
                self._config.namespace,
            )
            # temporalio Client.connect is async
            self._client = await Client.connect(
                self._config.host,
                namespace=self._config.namespace,
            )
            return self._client
