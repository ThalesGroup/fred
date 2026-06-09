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

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

import pytest

import fred_core.model.http_clients as http_clients
from fred_core.common import ModelConfiguration


def _model_config(
    settings: dict[str, object] | None = None,
    *,
    provider: str = "openai",
) -> ModelConfiguration:
    """Build one minimal model configuration for shared HTTP client tests."""

    return ModelConfiguration(provider=provider, name="demo-model", settings=settings)


@pytest.fixture(autouse=True)
def isolate_shared_httpx_state() -> Iterator[None]:
    """Reset the module-level shared stack so each test stays independent."""

    original_tuning = http_clients._SHARED_TUNING
    original_sync = http_clients._SYNC_CLIENT
    original_async = http_clients._ASYNC_CLIENT
    http_clients._SHARED_TUNING = None
    http_clients._SYNC_CLIENT = None
    http_clients._ASYNC_CLIENT = None
    try:
        yield
    finally:
        http_clients._SHARED_TUNING = original_tuning
        http_clients._SYNC_CLIENT = original_sync
        http_clients._ASYNC_CLIENT = original_async


def test_silence_asyncio_debug_logs_restores_logger_state() -> None:
    """Temporarily disable asyncio logger output only within the context."""

    asyncio_logger = logging.getLogger("asyncio")
    original_disabled = asyncio_logger.disabled
    asyncio_logger.disabled = False
    try:
        with http_clients._silence_asyncio_debug_logs():
            assert asyncio_logger.disabled is True
        assert asyncio_logger.disabled is False
    finally:
        asyncio_logger.disabled = original_disabled


def test_compute_transport_tuning_uses_defaults_when_settings_missing() -> None:
    """Return the documented default limits and timeout values."""

    tuning = http_clients.compute_transport_tuning({})

    assert tuning.limits.max_connections == 500
    assert tuning.limits.max_keepalive_connections == 50
    assert tuning.limits.keepalive_expiry == 10.0
    assert tuning.timeout.connect == 10.0
    assert tuning.timeout.read == 120.0
    assert tuning.timeout.write == 30.0
    assert tuning.timeout.pool == 5.0


def test_compute_transport_tuning_warns_for_invalid_limit_shape_and_request_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ignore non-dict limits and reuse request_timeout for transport fallback."""

    settings: dict[str, object] = {
        "http_client_limits": ["bad-shape"],
        "request_timeout": 42,
    }

    with caplog.at_level(logging.WARNING):
        tuning = http_clients.compute_transport_tuning(settings)

    assert "[NET] http_client_limits ignored" in caplog.text
    assert "[NET] timeout not set; using request_timeout=42" in caplog.text
    assert tuning.limits.max_connections == 500
    assert tuning.timeout.connect == 42.0
    assert tuning.timeout.read == 42.0
    assert tuning.timeout.write == 42.0
    assert tuning.timeout.pool == 42.0


def test_compute_transport_tuning_raises_for_invalid_numeric_values() -> None:
    """Reject negative limits and malformed timeout fields."""

    with pytest.raises(ValueError, match="max_connections must be >= 0"):
        http_clients.compute_transport_tuning(
            {"http_client_limits": {"max_connections": -1}}
        )

    with pytest.raises(ValueError, match="timeout.connect must be a float"):
        http_clients.compute_transport_tuning(
            {"timeout": {"connect": "oops", "read": 1, "write": 1, "pool": 1}}
        )


def test_strip_transport_settings_removes_only_transport_keys() -> None:
    """Remove transport-only keys while preserving request-level timeout."""

    settings: dict[str, object] = {
        "http_client_limits": {"max_connections": 99},
        "timeout": {"connect": 1},
        "request_timeout": 12,
        "temperature": 0.5,
    }

    http_clients.strip_transport_settings(settings)

    assert settings == {
        "request_timeout": 12,
        "temperature": 0.5,
    }


def test_get_shared_stack_initializes_once_and_reuses_matching_tuning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Create one shared HTTPX stack and reuse it for identical settings."""

    registered: list[object] = []

    def fake_register(
        callback: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        registered.append(callback)
        return callback

    monkeypatch.setattr(http_clients.atexit, "register", fake_register)

    cfg = _model_config(
        {
            "http_client_limits": {
                "max_connections": 10,
                "max_keepalive_connections": 4,
                "keepalive_expiry_seconds": 2.5,
            },
            "timeout": {
                "connect": 1,
                "read": 2,
                "write": 3,
                "pool": 4,
            },
        }
    )

    with caplog.at_level(logging.INFO):
        tuning_1, sync_1, async_1 = http_clients.get_shared_stack(cfg)
        tuning_2, sync_2, async_2 = http_clients.get_shared_stack(cfg)

    assert tuning_1 == tuning_2
    assert sync_1 is sync_2
    assert async_1 is async_2
    assert registered == [http_clients.shutdown_shared_clients]
    assert "[NET] Shared HTTPX stack init provider=openai" in caplog.text

    http_clients.shutdown_shared_clients()
    assert sync_1.is_closed is True
    assert async_1.is_closed is True
    assert http_clients._SYNC_CLIENT is None
    assert http_clients._ASYNC_CLIENT is None


def test_get_shared_stack_warns_and_ignores_new_tuning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep the first initialized tuning when later callers request a different one."""

    monkeypatch.setattr(
        http_clients.atexit,
        "register",
        lambda callback, *args, **kwargs: callback,
    )

    base_cfg = _model_config({"timeout": 5}, provider="openai")
    different_cfg = _model_config(
        {
            "http_client_limits": {"max_connections": 999},
            "timeout": {"connect": 9, "read": 9, "write": 9, "pool": 9},
        },
        provider="azure",
    )

    tuning_1, sync_1, async_1 = http_clients.get_shared_stack(base_cfg)

    with caplog.at_level(logging.WARNING):
        tuning_2, sync_2, async_2 = http_clients.get_shared_stack(different_cfg)

    assert tuning_2 == tuning_1
    assert sync_2 is sync_1
    assert async_2 is async_1
    assert "ignoring new tuning" in caplog.text

    http_clients.shutdown_shared_clients()


@pytest.mark.asyncio
async def test_shutdown_shared_clients_closes_async_client_when_loop_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schedule async client shutdown on the current loop when one is already running."""

    monkeypatch.setattr(
        http_clients.atexit,
        "register",
        lambda callback, *args, **kwargs: callback,
    )
    cfg = _model_config({"timeout": 5})

    _, sync_client, async_client = http_clients.get_shared_stack(cfg)

    http_clients.shutdown_shared_clients()
    await asyncio.sleep(0)

    assert sync_client.is_closed is True
    assert async_client.is_closed is True
    assert http_clients._SYNC_CLIENT is None
    assert http_clients._ASYNC_CLIENT is None


@pytest.mark.asyncio
async def test_async_shutdown_shared_clients_closes_both_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Await shared client shutdown directly from async teardown paths."""

    monkeypatch.setattr(
        http_clients.atexit,
        "register",
        lambda callback, *args, **kwargs: callback,
    )
    cfg = _model_config({"timeout": 5})

    _, sync_client, async_client = http_clients.get_shared_stack(cfg)

    await http_clients.async_shutdown_shared_clients()

    assert sync_client.is_closed is True
    assert async_client.is_closed is True
    assert http_clients._SYNC_CLIENT is None
    assert http_clients._ASYNC_CLIENT is None
