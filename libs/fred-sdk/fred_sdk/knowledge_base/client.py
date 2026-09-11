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

"""
The pod's outbound calls to Control Plane.

Every call is outbound and authenticated with the pod's own confidential M2M
client — never a user token, because a dispatched run has no user present.
One instance holds one connection pool and one cached token, so a long-lived
worker does not re-handshake per run.
Fred binds a definition to the client that first publishes it, so the same
identity authorizes publication, run context and result reporting.
"""

from __future__ import annotations

import logging

import httpx
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider

from fred_sdk.knowledge_base.declaration import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.environment import CLIENT_SECRET_ENV, PodEnvironment
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseRunContext,
    KnowledgeBaseSyncResult,
)

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0)


class ControlPlaneClient:
    """Authenticated Control Plane calls a Knowledge Base pod makes."""

    def __init__(self, environment: PodEnvironment) -> None:
        self._base_url = environment.control_plane_url
        self._provider_id = environment.provider_id
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._tokens: M2MTokenProvider | None = None
        if environment.authenticated:
            self._tokens = M2MTokenProvider(
                M2MAuthConfig(
                    keycloak_realm_url=environment.keycloak_realm_url,
                    client_id=environment.client_id,
                    secret_env=CLIENT_SECRET_ENV,
                )
            )
        else:
            logger.warning(
                "No client secret set: calling Fred unauthenticated. Only a "
                "local stack with authentication disabled will accept this."
            )

    async def publish(self, declaration: KnowledgeBaseDeclaration) -> None:
        """Upsert this definition's declaration. Idempotent, so a redeploy replays."""
        await self._request(
            "PUT",
            f"/knowledge-bases/providers/{self._provider_id}"
            f"/definitions/{declaration.id}",
            json=declaration.to_payload(),
        )

    async def fetch_run_context(
        self, definition_id: str, run_id: str
    ) -> KnowledgeBaseRunContext:
        """Fetch one run's configuration, scoped to that active run."""
        payload = await self._request(
            "GET",
            f"/knowledge-bases/providers/{self._provider_id}"
            f"/definitions/{definition_id}/runs/{run_id}/context",
        )
        return KnowledgeBaseRunContext.model_validate(payload)

    async def report_result(
        self, definition_id: str, run_id: str, result: KnowledgeBaseSyncResult
    ) -> None:
        """Report the terminal state and bounded result of one run."""
        await self._request(
            "POST",
            f"/knowledge-bases/providers/{self._provider_id}"
            f"/definitions/{definition_id}/runs/{run_id}/result",
            json=result.model_dump(mode="json"),
        )

    async def _request(
        self, method: str, path: str, json: object | None = None
    ) -> dict:
        headers = {}
        if self._tokens is not None:
            headers["Authorization"] = f"Bearer {await self._tokens.get_token()}"
        response = await self._client.request(
            method, f"{self._base_url}{path}", json=json, headers=headers
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
