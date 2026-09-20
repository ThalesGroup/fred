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
Writing documents into the library a run was given, and saying who fills it.

Knowledge Flow is offered to a Knowledge Base, not imposed on it: a pod that
keeps its own store never uses the publisher here, and declaring its library
does nothing for it either — both are inert without a Knowledge Flow URL. For a
pod that does not want to build storage on day one, this is the shortcut: it
authenticates with the pod's own identity, so an author writes no auth code and
holds no store credential.
"""

from __future__ import annotations

import logging
import mimetypes

import httpx
from fred_pod.security.backend_to_backend_auth import M2MTokenProvider

from fred_sdk.knowledge_base.configuration import PodConfiguration

logger = logging.getLogger(__name__)

# Ingestion converts and indexes inline, so this is minutes, not the 30s a
# Control Plane call gets.
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

# Declaring who fills a library writes one field, so it gets a call's timeout
# rather than an ingestion's.
_DECLARE_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# What a Knowledge Base is, in the vocabulary Fred records machine writers under.
# Fred stores the qualified reference and tests it for presence; it never parses
# this half, so nothing downstream depends on the spelling.
_MACHINE_KIND = "knowledge_base"


class DocumentPublishError(RuntimeError):
    """One document could not be written. The run may continue without it."""


class DocumentRetractError(RuntimeError):
    """One document could not be taken out of the library."""


def _raise_for(
    response: httpx.Response, error: type[RuntimeError], subject: str
) -> None:
    """The surface answers with an outcome, so a status is the whole story."""
    if response.status_code >= 400:
        raise error(f"{subject}: {response.status_code} {response.text[:300]}")


async def declare_library_synchronized(
    configuration: PodConfiguration, *, library_id: str, instance_id: str
) -> None:
    """Tell Fred a machine fills this library, so people stop writing into it.

    Sent by the pod rather than by Fred because writing it needs the right to
    write in that library, and the pod's grant over its own library is the only
    one an instance produces. It can therefore never reach a library it was not
    given, which is the property that makes this safe to let a pod declare.

    Never raises: a base that stopped synchronizing because it could not write a
    marker would be a worse failure than a library that stays open one more run,
    and the run after this one sends it again.
    """
    if not configuration.knowledge_flow_url:
        # This pod keeps its own store, so Fred holds no documents of its own to
        # protect. Same condition that decides whether it writes any at all.
        return

    machine = f"{_MACHINE_KIND}:{instance_id}"
    try:
        tokens = M2MTokenProvider(configuration.m2m)
        async with httpx.AsyncClient(timeout=_DECLARE_TIMEOUT) as client:
            response = await client.put(
                f"{configuration.knowledge_flow_url}/libraries/{library_id}/synchronized-by",
                json={"synchronized_by": machine},
                headers={"Authorization": f"Bearer {await tokens.get_token()}"},
            )
    except Exception:  # noqa: BLE001 - reported, never fatal to the run
        logger.warning(
            "Could not declare library %s as filled by %s",
            library_id,
            machine,
            exc_info=True,
        )
        return

    if response.status_code >= 400:
        # A different machine already filling this library means two of them
        # share a folder, which nothing upstream should allow — loud on purpose.
        logger.warning(
            "Fred refused the declaration for library %s: %s %s",
            library_id,
            response.status_code,
            response.text[:300],
        )


class DocumentPublisher:
    """Writes into one library, as the pod's own workload identity."""

    def __init__(
        self,
        configuration: PodConfiguration,
        *,
        library_id: str,
        source_tag: str,
    ) -> None:
        if not configuration.knowledge_flow_url:
            raise ValueError(
                "This pod has no Knowledge Flow URL: set FRED_KNOWLEDGE_FLOW_URL, "
                "or keep your own store and do not use DocumentPublisher."
            )
        self._base_url = configuration.knowledge_flow_url
        self._library_id = library_id
        self._source_tag = source_tag
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._tokens = M2MTokenProvider(configuration.m2m)

    async def publish(
        self, *, relative_path: str, content: bytes, version: str | None = None
    ) -> None:
        """Write one document, replacing what the same path held before.

        The source key is the caller's own name for it — writing the same key
        again updates that document, so nothing about Fred's own identifiers
        ever has to be remembered here.
        """
        response = await self._client.post(
            f"{self._base_url}/libraries/{self._library_id}/documents",
            files={
                "file": (
                    relative_path,
                    content,
                    mimetypes.guess_type(relative_path)[0]
                    or "application/octet-stream",
                )
            },
            data={
                "path": relative_path,
                "source_key": relative_path,
                "source_tag": self._source_tag,
                **({"document_version": version} if version else {}),
            },
            headers=await self._headers(),
        )
        _raise_for(response, DocumentPublishError, relative_path)

    async def retract(self, *, relative_path: str) -> None:
        """Take one document out of the library, by the key it was written under.

        The document is not destroyed — it stops belonging to this library,
        which is the only retraction a source's disappearance justifies. A key
        the library does not hold is not an error.
        """
        response = await self._client.request(
            "DELETE",
            f"{self._base_url}/libraries/{self._library_id}/documents",
            params={"source_key": relative_path},
            headers=await self._headers(),
        )
        _raise_for(response, DocumentRetractError, relative_path)

    async def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._tokens.get_token()}"}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DocumentPublisher":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
