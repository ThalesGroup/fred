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
Writing documents into the library a run was given.

Knowledge Flow is offered to a Knowledge Base, not imposed on it: a pod that
keeps its own store never imports this. For one that does not want to build
storage on day one, this is the shortcut — it authenticates with the pod's own
identity, so an author writes no auth code and holds no store credential.
"""

from __future__ import annotations

import json
import logging
import mimetypes

import httpx
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider

from fred_sdk.knowledge_base.environment import CLIENT_SECRET_ENV, PodEnvironment

logger = logging.getLogger(__name__)

# Ingestion converts and indexes inline, so this is minutes, not the 30s a
# Control Plane call gets.
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

_FAILED_STATUSES = frozenset({"failed", "error"})


class DocumentPublishError(RuntimeError):
    """One document could not be written. The run may continue without it."""


class DocumentRetractError(RuntimeError):
    """One document could not be taken out of the library."""


class DocumentPublisher:
    """Writes into one library, as the pod's own workload identity."""

    def __init__(
        self,
        environment: PodEnvironment,
        *,
        library_id: str,
        source_tag: str,
    ) -> None:
        if not environment.knowledge_flow_url:
            raise ValueError(
                "This pod has no Knowledge Flow URL: set FRED_KNOWLEDGE_FLOW_URL, "
                "or keep your own store and do not use DocumentPublisher."
            )
        self._base_url = environment.knowledge_flow_url
        self._library_id = library_id
        self._source_tag = source_tag
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
                "No client secret set: ingesting unauthenticated. Only a local "
                "stack with authentication disabled will accept this."
            )

    async def publish(self, *, relative_path: str, content: bytes) -> str | None:
        """Write one document, replacing what the same path held before.

        Returns the identifier Fred assigned it, when the response carries one.
        """
        metadata = {"tags": [self._library_id], "source_tag": self._source_tag}
        files = {
            "files": (
                relative_path,
                content,
                mimetypes.guess_type(relative_path)[0] or "application/octet-stream",
            )
        }
        response = await self._client.post(
            f"{self._base_url}/upload-process-documents",
            files=files,
            data={"metadata_json": json.dumps(metadata)},
            headers=await self._headers(),
        )
        if response.status_code >= 400:
            raise DocumentPublishError(
                f"{relative_path}: {response.status_code} {response.text[:300]}"
            )
        return self._outcome(relative_path, response.text)

    async def retract(self, *, document_uid: str) -> None:
        """Take one document out of the library, as the UI's delete does.

        The document itself is not destroyed — it stops belonging to this
        library, which is the only retraction a source's disappearance
        justifies. A library this pod owns has one writer, so the
        read-modify-write below races with nobody.
        """
        headers = await self._headers()
        current = await self._client.get(
            f"{self._base_url}/tags/{self._library_id}", headers=headers
        )
        if current.status_code >= 400:
            raise DocumentRetractError(
                f"cannot read library {self._library_id}: "
                f"{current.status_code} {current.text[:200]}"
            )
        tag = current.json()
        remaining = [uid for uid in tag.get("item_ids") or [] if uid != document_uid]
        if len(remaining) == len(tag.get("item_ids") or []):
            return  # already out of the library: nothing to write

        updated = await self._client.put(
            f"{self._base_url}/tags/{self._library_id}",
            json={
                "name": tag["name"],
                "path": tag.get("path"),
                "description": tag.get("description"),
                "type": tag.get("type"),
                "item_ids": remaining,
            },
            headers=headers,
        )
        if updated.status_code >= 400:
            raise DocumentRetractError(
                f"{document_uid}: {updated.status_code} {updated.text[:200]}"
            )

    @staticmethod
    def _outcome(relative_path: str, body: str) -> str | None:
        """Read the progress stream: a 200 still carries per-file failures."""
        document_uid: str | None = None
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("status") in _FAILED_STATUSES:
                raise DocumentPublishError(
                    f"{relative_path}: {event.get('step', 'ingestion')} reported "
                    f"{event.get('status')}"
                )
            document_uid = event.get("document_uid") or document_uid
        return document_uid

    async def _headers(self) -> dict[str, str]:
        if self._tokens is None:
            return {}
        return {"Authorization": f"Bearer {await self._tokens.get_token()}"}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DocumentPublisher":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
