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

"""
Application-scoped runtime state (FastAPI-bound).
- Owns the in-process httpx client used for backend↔backend/self calls.
- Keeps FastAPI imports out of ApplicationContext (safe for Temporal/sandbox code).
- Propagates user bearer when present; falls back to B2B service token.
"""

from __future__ import annotations
from typing import Optional, Mapping, Any
import httpx
from fastapi import FastAPI

from fred_core import (
    B2BAuthConfig,
    B2BTokenProvider,
    B2BBearerAuth,
    make_b2b_asgi_client,
)

from app.application_context import get_configuration


class _AppState:
    def __init__(self) -> None:
        self._app: Optional[FastAPI] = None
        self._b2b_client: Optional[httpx.AsyncClient] = None
        self._b2b_provider: Optional[B2BTokenProvider] = None

    def attach_app(self, app: FastAPI) -> None:
        """
        Fred rationale:
        - Bind the running FastAPI instance so we can build an in-process ASGI client.
        - Keeps internal calls fast (no network) and always authenticated (service bearer).
        """
        self._app = app
        self._init_b2b_client()

    def _init_b2b_client(self) -> None:
        if self._app is None:
            return  # not attach_app'ed yet

        # Read the same Keycloak values you use in initialize_keycloak()
        get_configuration().app.security.client_id
        realm_url = get_configuration().app.security.keycloak_url
        client_id = get_configuration().app.security.client_id
        token_env_var_name = "KEYCLOAK_KNOWLEDGE_CLIENT_SECRET"  # nosec B105

        if not realm_url or not client_id:
            # Soft-fail: allows tests/dev without B2B; errors only when accessed.
            return

        cfg = B2BAuthConfig(
            keycloak_realm_url=realm_url,
            client_id=client_id,
            secret_env=token_env_var_name,
        )
        self._b2b_provider = B2BTokenProvider(cfg)
        auth = B2BBearerAuth(self._b2b_provider)
        self._b2b_client = make_b2b_asgi_client(self._app, auth)

    def get_b2b_client(self) -> httpx.AsyncClient:
        if self._b2b_client is None:
            raise RuntimeError("B2B client not initialized. Call application_state.attach_app(app) at startup and set KEYCLOAK_REALM_URL / KEYCLOAK_CLIENT_ID / KEYCLOAK_CLIENT_SECRET.")
        return self._b2b_client

    async def internal_request(
        self,
        method: str,
        path: str,
        *,
        user_authorization: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Preferred self-call:
        - If user bearer exists → propagate it (keeps user context/audit).
        - Else → use service bearer via shared B2B client.
        """
        client = self.get_b2b_client()
        hdrs = dict(headers or {})
        if user_authorization:
            hdrs["Authorization"] = user_authorization
        return await client.request(method.upper(), path, headers=hdrs, **kwargs)

    async def shutdown(self) -> None:
        """Close the shared httpx client cleanly on app shutdown."""
        if self._b2b_client is not None:
            await self._b2b_client.aclose()
            self._b2b_client = None


# Module-level singleton (simple and explicit)
_STATE = _AppState()


# Public helpers (nice import ergonomics)
def attach_app(app: FastAPI) -> None:
    _STATE.attach_app(app)


def get_b2b_client() -> httpx.AsyncClient:
    return _STATE.get_b2b_client()


async def internal_get(path: str, *, user_authorization: Optional[str] = None, **kw) -> httpx.Response:
    return await _STATE.internal_request("GET", path, user_authorization=user_authorization, **kw)


async def internal_post(path: str, *, user_authorization: Optional[str] = None, **kw) -> httpx.Response:
    return await _STATE.internal_request("POST", path, user_authorization=user_authorization, **kw)


async def shutdown() -> None:
    await _STATE.shutdown()
