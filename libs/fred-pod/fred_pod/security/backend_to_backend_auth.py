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
import math
import os
import time
import typing as t
from collections.abc import Callable

import httpx
from httpx import Request, Response
from pydantic import BaseModel, Field

# The shape httpx.ASGITransport accepts. Any ASGI application qualifies —
# FastAPI is one — and naming it this way keeps FastAPI out of the pod floor.
_ASGIMessage = t.MutableMapping[str, t.Any]
ASGIApp = t.Callable[
    [
        _ASGIMessage,
        t.Callable[[], t.Awaitable[_ASGIMessage]],
        t.Callable[[_ASGIMessage], t.Awaitable[None]],
    ],
    t.Awaitable[None],
]

# A tool or pod calling a Fred API has no user bearer, so it needs a service
# token (client_credentials) or the call 401s. It lives in fred-pod because every
# pod needs it and none should install the agents platform to get it.


class M2MAuthConfig(BaseModel):
    """
    Minimal config for client-credentials flow.
    keycloak_realm_url: the *realm* URL, same one you already use for JWKS
                        (e.g., https://kc.example/realms/myrealm)
    client_id:          confidential client ID (e.g., "knowledge")
    secret_env:         env var name that stores the client secret (e.g., "KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET")
    scope:              optional Keycloak scopes (rarely needed)
    """

    keycloak_realm_url: str
    client_id: str
    secret_env: str
    scope: str | None = None
    refresh_failure_cooldown_seconds: float = Field(
        default=5.0, gt=0, le=60, allow_inf_nan=False
    )

    @property
    def token_url(self) -> str:
        # Mirrors how you compute JWKS: realm/protocol/openid-connect/token
        return f"{self.keycloak_realm_url}/protocol/openid-connect/token"


class M2MTokenProvider:
    """
    Caches and refreshes a Keycloak client-credentials token.
    Thread-safe (async) and cheap to reuse across calls.
    """

    def __init__(
        self,
        cfg: M2MAuthConfig,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.cfg = cfg
        self._secret = os.getenv(cfg.secret_env, "")
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._exp: float = 0  # epoch seconds
        self._failure_deadline = 0.0
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock
        self._transport = transport

    @staticmethod
    def _refresh_error() -> RuntimeError:
        return RuntimeError("Workload token refresh failed.")

    def _raise_during_cooldown(self) -> None:
        if self._monotonic_clock() < self._failure_deadline:
            raise self._refresh_error()

    async def get_token(self) -> str:
        now = self._wall_clock()
        if self._token and now < self._exp - 30:
            return self._token
        self._raise_during_cooldown()

        async with self._lock:
            # double-check inside lock
            now = self._wall_clock()
            if self._token and now < self._exp - 30:
                return self._token
            self._raise_during_cooldown()

            if not self._secret:
                self._failure_deadline = (
                    self._monotonic_clock() + self.cfg.refresh_failure_cooldown_seconds
                )
                raise self._refresh_error()

            form = {
                "grant_type": "client_credentials",
                "client_id": self.cfg.client_id,
                "client_secret": self._secret,
            }
            if self.cfg.scope:
                form["scope"] = self.cfg.scope

            try:
                async with httpx.AsyncClient(
                    timeout=10.0, transport=self._transport
                ) as c:
                    r = await c.post(self.cfg.token_url, data=form)
                    r.raise_for_status()
                    payload = r.json()

                token = payload.get("access_token")
                raw_expires_in = payload.get("expires_in", 60)
                if not isinstance(token, str) or not token:
                    raise ValueError
                if isinstance(raw_expires_in, bool):
                    raise ValueError
                expires_in = float(raw_expires_in)
                if not math.isfinite(expires_in) or expires_in <= 0:
                    raise ValueError
                expires_at = now + expires_in
                if self._wall_clock() >= expires_at:
                    raise ValueError
            except Exception:
                self._failure_deadline = (
                    self._monotonic_clock() + self.cfg.refresh_failure_cooldown_seconds
                )
                raise self._refresh_error() from None

            self._token = token
            self._exp = expires_at
            self._failure_deadline = 0.0

            # Guarantee to the outside world that we return str
            assert self._token is not None
            return self._token


class M2MBearerAuth(httpx.Auth):
    """
    httpx.Auth that injects 'Authorization: Bearer <service_token>'.

    Important: httpx expects an *async generator* here. We yield the request
    after mutating headers, which avoids the common type errors.
    """

    requires_request_body = True
    requires_response_body = False

    def __init__(self, provider: M2MTokenProvider):
        self._provider = provider

    async def async_auth_flow(
        self, request: Request
    ) -> t.AsyncGenerator[Request, Response]:
        token = await self._provider.get_token()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request  # httpx performs the request; we don't need the response hook here.


def make_m2m_asgi_client(app: ASGIApp, auth: httpx.Auth) -> httpx.AsyncClient:
    """
    In-process client for self-calls via ASGITransport (no network).
    """
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://apiserver",
        timeout=15.0,
        auth=auth,
    )
