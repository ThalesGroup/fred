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

"""CTRLP-12 C2: control-plane service-token minter.

The server-initiated erase path (lifecycle erase-at-expiry) has no user bearer,
so it authenticates as the platform service principal using the existing
`control-plane` Keycloak service account. These tests pin the wiring:
- the minter is built from `security.m2m` (the control-plane SA), reusing the
  shared `M2MTokenProvider`;
- `get_service_bearer()` returns an `Authorization` value;
- it fails closed (raises) when the client secret is absent, so the lifecycle
  can treat it as a retryable error rather than silently skipping the erase.
"""

from __future__ import annotations

import pytest

from control_plane_backend.app.context import ApplicationContext
from control_plane_backend.config.loader import load_configuration

_SECRET_ENV = "KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET"


def _context(monkeypatch: pytest.MonkeyPatch) -> ApplicationContext:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    return ApplicationContext(load_configuration())


def test_service_token_provider_is_built_from_control_plane_sa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context(monkeypatch)
    provider = ctx.get_service_token_provider()

    # Reuses the existing control-plane service account (security.m2m).
    assert provider.cfg.client_id == "control-plane"
    assert provider.cfg.secret_env == _SECRET_ENV
    assert provider.cfg.token_url.endswith("/protocol/openid-connect/token")
    # Cached: the provider (and its token cache) is reused across calls.
    assert ctx.get_service_token_provider() is provider


@pytest.mark.asyncio
async def test_get_service_bearer_formats_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context(monkeypatch)

    async def _fake_get_token() -> str:
        return "minted-token"

    # Avoid a real Keycloak round-trip; the fred_core provider is tested upstream.
    monkeypatch.setattr(ctx.get_service_token_provider(), "get_token", _fake_get_token)
    assert await ctx.get_service_bearer() == "Bearer minted-token"


@pytest.mark.asyncio
async def test_get_service_bearer_fails_closed_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    config = load_configuration()
    # Remove the secret AFTER loading config (loading the .env may have set it),
    # and BEFORE the provider is built lazily below so it reads an empty secret.
    monkeypatch.delenv(_SECRET_ENV, raising=False)
    ctx = ApplicationContext(config)

    # The provider reads the secret from the env at construction; absent → the
    # mint raises (never a network call) so the lifecycle leaves the queue entry
    # un-done (retryable) rather than silently skipping the erase.
    with pytest.raises(RuntimeError):
        await ctx.get_service_bearer()
