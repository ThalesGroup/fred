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

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fred_core.common import TemporalSchedulerConfig
from fred_core.scheduler.temporal_client_provider import TemporalClientProvider


@pytest.mark.asyncio
async def test_get_client_times_out_instead_of_hanging_forever() -> None:
    # An unreachable/slow Temporal frontend must fail this call, not hang the
    # caller (and, transitively, an upload HTTP stream) forever.
    config = TemporalSchedulerConfig(connect_timeout_seconds=1)
    provider = TemporalClientProvider(config)

    async def hang_forever(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(10)

    with patch(
        "fred_core.scheduler.temporal_client_provider.Client.connect",
        side_effect=hang_forever,
    ):
        with pytest.raises(TimeoutError):
            await provider.get_client()


@pytest.mark.asyncio
async def test_get_client_returns_the_connected_client_when_fast() -> None:
    config = TemporalSchedulerConfig(connect_timeout_seconds=5)
    provider = TemporalClientProvider(config)
    sentinel = object()

    with patch(
        "fred_core.scheduler.temporal_client_provider.Client.connect",
        new=AsyncMock(return_value=sentinel),
    ):
        client = await provider.get_client()

    assert client is sentinel


@pytest.mark.asyncio
async def test_get_client_never_times_out_when_disabled() -> None:
    config = TemporalSchedulerConfig(connect_timeout_seconds=None)
    provider = TemporalClientProvider(config)
    sentinel = object()

    with patch(
        "fred_core.scheduler.temporal_client_provider.Client.connect",
        new=AsyncMock(return_value=sentinel),
    ):
        client = await provider.get_client()

    assert client is sentinel


@pytest.mark.asyncio
async def test_get_client_caches_the_connection_across_calls() -> None:
    config = TemporalSchedulerConfig(connect_timeout_seconds=5)
    provider = TemporalClientProvider(config)
    connect_mock = AsyncMock(return_value=object())

    with patch(
        "fred_core.scheduler.temporal_client_provider.Client.connect", new=connect_mock
    ):
        first = await provider.get_client()
        second = await provider.get_client()

    assert first is second
    connect_mock.assert_called_once()
