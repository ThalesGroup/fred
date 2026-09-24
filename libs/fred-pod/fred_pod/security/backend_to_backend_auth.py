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
import math
import os
import time
import typing as t
from collections.abc import Callable

import httpx
from httpx import Request, Response
from pydantic import BaseModel

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


# Optional process-local observer: fred-pod stays independent of metrics libraries.
TokenObserver = Callable[[str, str, float], None]
_token_observer: TokenObserver | None = None


def set_token_observer(observer: TokenObserver | None) -> None:
    global _token_observer
    _token_observer = observer


def _observe_token(event: str, outcome: str, seconds: float = 0.0) -> None:
    if _token_observer is not None:
        try:
            _token_observer(event, outcome, seconds)
        except Exception:
            logging.getLogger(__name__).warning("Auth metrics observer failed")


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

    @property
    def token_url(self) -> str:
        # Mirrors how you compute JWKS: realm/protocol/openid-connect/token
        return f"{self.keycloak_realm_url}/protocol/openid-connect/token"


_REFRESH_FAILED = "Workload token refresh failed."


class M2MTokenProvider:
    """
    Caches and refreshes a Keycloak client-credentials token.
    Thread-safe (async) and cheap to reuse across calls.
    """

    def __init__(
        self,
        cfg: M2MAuthConfig,
        *,
        wall_clock: Callable[[], float] = time.time,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.cfg = cfg
        self._secret = os.getenv(cfg.secret_env, "")
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._exp: float = 0  # epoch seconds
        self._wall_clock = wall_clock
        self._transport = transport

    async def get_token(self) -> str:
        started = time.perf_counter()
        outcome = "error"
        try:
            token = await self._get_token()
            outcome = "success"
            return token
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            _observe_token("acquire", outcome, time.perf_counter() - started)

    async def _get_token(self) -> str:
        now = self._wall_clock()
        if self._token and now < self._exp - 30:
            _observe_token("cache", "hit")
            return self._token
        _observe_token("cache", "miss")
        async with self._lock:
            # double-check inside lock
            now = self._wall_clock()
            if self._token and now < self._exp - 30:
                _observe_token("cache", "shared_refresh")
                return self._token
            if not self._secret:
                raise RuntimeError(_REFRESH_FAILED)

            form = {
                "grant_type": "client_credentials",
                "client_id": self.cfg.client_id,
                "client_secret": self._secret,
            }
            if self.cfg.scope:
                form["scope"] = self.cfg.scope

            request_started = time.perf_counter()
            request_outcome = "error"
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
                request_outcome = "success"
            except asyncio.CancelledError:
                request_outcome = "cancelled"
                raise
            except httpx.TransportError as exc:
                # Same httpx class as the underlying failure, without its request or detail.
                raise type(exc)(_REFRESH_FAILED) from None
            except Exception:
                raise RuntimeError(_REFRESH_FAILED) from None
            finally:
                _observe_token(
                    "request_renewal" if self._token is not None else "request_initial",
                    request_outcome,
                    time.perf_counter() - request_started,
                )

            self._token = token
            self._exp = expires_at
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
