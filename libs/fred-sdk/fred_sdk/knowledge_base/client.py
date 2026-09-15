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
Fred binds a prefix to the client that first publishes under it, so the same
identity authorizes publishing a declaration and reading a run's configuration.

Nothing here reports what a run did. Fred runs the workflow engine and reads a
run's state from it, so a pod that is killed never leaves a run looking
unfinished — and there is no second version of that fact to disagree with.
"""

from __future__ import annotations

import httpx
from fred_core.security.backend_to_backend_auth import M2MTokenProvider

from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.declaration import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseRunContext,
)

_TIMEOUT = httpx.Timeout(30.0)


class ControlPlaneClient:
    """Authenticated Control Plane calls a Knowledge Base pod makes."""

    def __init__(self, configuration: PodConfiguration) -> None:
        self._base_url = configuration.control_plane_url
        self._prefix = configuration.prefix
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._tokens = M2MTokenProvider(configuration.m2m)

    async def publish(self, declaration: KnowledgeBaseDeclaration) -> None:
        """Upsert this definition's declaration. Idempotent, so a redeploy replays."""
        await self._request(
            "PUT",
            f"/knowledge-bases/definitions/{declaration.id}",
            json={"prefix": self._prefix, **declaration.to_payload()},
        )

    async def fetch_run_context(
        self,
        definition_id: str,
        instance_id: str,
        run_id: str,
    ) -> KnowledgeBaseRunContext:
        """Fetch one run's configuration, scoped to that run's own instance.

        The instance is named because Fred resolves the run through it: a run
        identifier alone says nothing about which folder is being filled.
        """
        payload = await self._request(
            "GET",
            f"/knowledge-bases/definitions/{definition_id}"
            f"/instances/{instance_id}/runs/{run_id}/context",
        )
        return KnowledgeBaseRunContext.model_validate(payload)

    async def _request(
        self,
        method: str,
        path: str,
        json: object | None = None,
        params: dict[str, str] | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {await self._tokens.get_token()}"}
        response = await self._client.request(
            method, f"{self._base_url}{path}", json=json, params=params, headers=headers
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
