# Copyright Thales 2025
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

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from fred_core.common.structures import TemporalSchedulerConfig

logger = logging.getLogger(__name__)


class TemporalClientProvider:
    """
    Provides a singleton Temporal client connection based on the given config.
    The connection is established lazily upon the first request.
    Safe for concurrent use.
    """

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
                data_converter=pydantic_data_converter,
            )
            return self._client
