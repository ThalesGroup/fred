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

Weaver claims admitted runs and reports bounded results to Control Plane.
Swift retains its workflow-owned execution contract.
"""

from __future__ import annotations

import os

import httpx
from fred_pod.security.backend_to_backend_auth import M2MBearerAuth

from fred_sdk.knowledge_base import telemetry
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.declaration import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseRunContext,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
)

_TIMEOUT = httpx.Timeout(30.0)


class ControlPlaneClient:
    """Authenticated Control Plane calls a Knowledge Base pod makes."""

    def __init__(self, configuration: PodConfiguration) -> None:
        self._configuration = configuration
        self._base_url = configuration.control_plane_url
        self._prefix = configuration.prefix
        self._tokens = configuration.token_provider
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT, auth=M2MBearerAuth(self._tokens)
        )

    async def publish(self, declaration: KnowledgeBaseDeclaration) -> None:
        """Upsert this definition's declaration. Idempotent, so a redeploy replays."""
        if self._configuration.knowledge_base.protocol == "weaver":
            payload = declaration.to_payload()
            fields = payload.pop("configuration_fields", [])
            await self._request(
                None,
                "POST",
                "/knowledge-base-definitions/publish",
                json={
                    "runtime_id": self._configuration.runtime_id,
                    "definitions": [{**payload, "config_schema": {"fields": fields}}],
                },
            )
            return
        # Not measured: `publish` runs as a one-shot deployment hook that no
        # scraper ever reaches. Its exit status and logs are its outcome.
        await self._request(
            None,
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
            "run_context",
            "GET",
            f"/knowledge-bases/definitions/{definition_id}"
            f"/instances/{instance_id}/runs/{run_id}/context",
        )
        return KnowledgeBaseRunContext.model_validate(payload)

    async def worker_configuration(self, definition_id: str) -> dict:
        return await self._request(
            "worker_configuration",
            "GET",
            "/knowledge-bases/worker",
            params={
                "runtime_id": self._configuration.runtime_id,
                "definition_id": definition_id,
            },
        )

    async def claim_run(
        self, run_id: str
    ) -> KnowledgeBaseRunContext | KnowledgeBaseRunOutcome:
        payload = await self._request(
            "claim", "POST", f"/knowledge-base-runs/{run_id}/claim"
        )
        if payload.get("state") in ("succeeded", "failed", "cancelled"):
            return KnowledgeBaseRunOutcome(payload["state"])
        configuration = {**payload["config"], "profile": payload["profile"]}
        for field, reference in payload.get("credential_refs", {}).items():
            variable = self._configuration.knowledge_base.secret_bindings.get(reference)
            if variable is None or variable not in os.environ:
                # Neither references nor environment values belong in activity failures.
                raise ValueError("Knowledge Base credential binding is unavailable")
            configuration[field] = os.environ[variable]
        return KnowledgeBaseRunContext(
            definition_id=payload["definition_id"],
            instance_id=payload["instance_id"],
            team_id=payload["space_id"],
            run_id=payload["id"],
            library_id=payload["folder_id"],
            configuration=configuration,
        )

    async def complete_run(self, run_id: str, result: KnowledgeBaseSyncResult) -> None:
        # Free-form source messages may contain credentials; only bounded counters
        # and stable codes cross the worker boundary.
        safe = result.model_dump(
            mode="json", exclude={"summary", "warnings", "errors", "metrics"}
        )
        await self._request(
            "complete",
            "POST",
            f"/knowledge-base-runs/{run_id}/complete",
            json={
                "error_code": None
                if result.outcome.value == "succeeded"
                else "synchronization_failed",
                "result": safe,
            },
        )

    async def _request(
        self,
        operation: str | None,
        method: str,
        path: str,
        json: object | None = None,
        params: dict[str, str] | None = None,
    ) -> dict:
        url = f"{self._base_url}{path}"
        if operation is None:
            response = await self._client.request(method, url, json=json, params=params)
        else:
            with telemetry.observing_request("control_plane", operation) as answered:
                response = await self._client.request(
                    method, url, json=json, params=params
                )
                answered(response.status_code)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
