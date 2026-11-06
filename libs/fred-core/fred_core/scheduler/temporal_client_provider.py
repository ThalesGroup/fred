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
from functools import cache
from typing import Optional

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.runtime import (
    LogForwardingConfig,
    LoggingConfig,
    Runtime,
    TelemetryConfig,
)

from fred_core.common import TemporalSchedulerConfig

logger = logging.getLogger(__name__)


@cache
def route_temporal_core_logs() -> None:
    """Forward sdk-core's logs to Python: it writes stderr in its own format otherwise.

    Call before the process's first Temporal client, which fixes the default runtime.
    """
    logs = LoggingConfig(
        filter=LoggingConfig.default.filter,
        forwarding=LogForwardingConfig(
            logger=logging.getLogger("temporal_sdk_core"),
            prepend_target_on_message=False,
        ),
    )
    Runtime.set_default(
        Runtime(telemetry=TelemetryConfig(logging=logs)), error_if_already_set=False
    )


class TemporalClientProvider:
    """
    Provides a singleton Temporal client connection based on the given config.
    The connection is established lazily upon the first request.
    Safe for concurrent use.
    """

    def __init__(
        self, config: TemporalSchedulerConfig, *, log_connection_details: bool = True
    ) -> None:
        self._config = config
        self._log_connection_details = log_connection_details
        self._client: Optional[Client] = None
        self._lock = asyncio.Lock()

    @property
    def config(self) -> TemporalSchedulerConfig:
        return self._config

    async def get_client(self) -> Client:
        """
        Lazy singleton connection. Safe under concurrent calls.
        """
        if self._client is not None:
            return self._client

        async with self._lock:
            if self._client is not None:
                return self._client

            if self._log_connection_details:
                logger.info(
                    "Connecting: host=%s namespace=%s",
                    self._config.host,
                    self._config.namespace,
                )
            else:
                logger.info("event=scheduler_connection outcome=started")
            # temporalio Client.connect is async and exposes no per-call rpc_timeout of
            # its own — bound it ourselves so an unreachable/slow Temporal frontend
            # cannot hang every caller of get_client() indefinitely.
            route_temporal_core_logs()
            connect_call = Client.connect(
                self._config.host,
                namespace=self._config.namespace,
                data_converter=pydantic_data_converter,
            )
            timeout = self._config.connect_timeout_seconds
            try:
                self._client = (
                    await asyncio.wait_for(connect_call, timeout=timeout)
                    if timeout
                    else await connect_call
                )
            except TimeoutError:
                if self._log_connection_details:
                    logger.error(
                        "Connect to host=%s namespace=%s timed out after %ss",
                        self._config.host,
                        self._config.namespace,
                        timeout,
                    )
                else:
                    logger.error(
                        "event=scheduler_connection outcome=failed reason=timeout"
                    )
                raise
            return self._client
