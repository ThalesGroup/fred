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

import asyncio
import logging
import mimetypes
from typing import Literal

import httpx
from fred_pod.security.backend_to_backend_auth import M2MBearerAuth
from pydantic import BaseModel

from fred_sdk.knowledge_base.configuration import PodConfiguration

logger = logging.getLogger(__name__)

# Fred extracts metadata, copies the file into its store and submits the task
# before answering a write, so the read side outlasts a plain call's.
_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=120.0, pool=10.0)

# Declaring who fills a library writes one field, so it gets a call's timeout
# rather than an ingestion's.
_DECLARE_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# What a Knowledge Base is, in the vocabulary Fred records machine writers under.
# Fred stores the qualified reference and tests it for presence; it never parses
# this half, so nothing downstream depends on the spelling.
_MACHINE_KIND = "knowledge_base"

# Mirrors `TaskState.is_terminal` in fred_core: spelled out here because a pod
# reads a task's state without installing the platform.
_SUCCEEDED = "succeeded"
_FAILED = "failed"
_TERMINAL_STATES = (_SUCCEEDED, _FAILED, "cancelled")

# A poll answered with one of these says nothing about the task: the request
# timed out at a proxy, or Fred asked to slow down. Polling on is the answer.
_TRANSIENT_STATUSES = (408, 429)


class _RefusedError(RuntimeError):
    """Fred answered with a status; kept on the error so 5xx and 4xx read apart."""

    status_code: int = 0


class DocumentPublishError(_RefusedError):
    """Fred refused a write, or a read of what it holds. Names what and why."""


class DocumentRetractError(_RefusedError):
    """One document could not be taken out of the library."""


class DocumentWaitTimeout(RuntimeError):
    """The wait ended before the ingestion did. The task itself keeps running."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"{task_id}: still not terminal when the wait ended")
        self.task_id = task_id


class DocumentHandle(BaseModel):
    """What Fred answered when it accepted a write: the ingestion to follow."""

    task_id: str
    document_uid: str
    source_key: str
    document_version: str | None = None
    created: bool


class DocumentOutcome(BaseModel):
    """Where an accepted write stands. Terminal once Fred has stopped working."""

    task_id: str
    state: str
    step: str | None = None
    progress: float | None = None
    error: str | None = None

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    @property
    def succeeded(self) -> bool:
        return self.state == _SUCCEEDED


def _raise_for(
    response: httpx.Response, error: type[_RefusedError], subject: str
) -> None:
    """The surface answers with an outcome, so a status is the whole story."""
    if response.status_code >= 400:
        refused = error(f"{subject}: {response.status_code} {response.text[:300]}")
        refused.status_code = response.status_code
        raise refused


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
        tokens = configuration.token_provider
        async with httpx.AsyncClient(
            timeout=_DECLARE_TIMEOUT, auth=M2MBearerAuth(tokens)
        ) as client:
            response = await client.put(
                f"{configuration.knowledge_flow_url}/libraries/{library_id}/synchronized-by",
                json={"synchronized_by": machine},
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
    """Writes into one library, and reads back what it holds, as the pod itself."""

    def __init__(
        self,
        configuration: PodConfiguration,
        *,
        library_id: str,
        source_tag: str,
    ) -> None:
        if not configuration.knowledge_flow_url:
            raise ValueError(
                "This pod has no Knowledge Flow URL: set "
                "knowledge_base.knowledge_flow_url in its configuration.yaml, "
                "or keep your own store and do not use DocumentPublisher."
            )
        self._base_url = configuration.knowledge_flow_url
        self._library_id = library_id
        self._source_tag = source_tag
        self._tokens = configuration.token_provider
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT, auth=M2MBearerAuth(self._tokens)
        )

    async def publish(
        self,
        *,
        relative_path: str,
        content: bytes,
        version: str | None = None,
        profile: Literal["fast", "medium", "rich"] = "medium",
    ) -> DocumentHandle:
        """Hand one document to Fred, replacing what the same path held before.

        The write is accepted here and processed by Fred's ingestion pipeline
        afterwards: the handle names the task to follow, and `wait` says whether
        it landed. The source key is the caller's own name for it — writing the
        same key again updates that document, so nothing about Fred's own
        identifiers ever has to be remembered here.
        `profile` selects ingestion processing and defaults to `medium`.
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
                "profile": profile,
                **({"document_version": version} if version else {}),
            },
        )
        _raise_for(response, DocumentPublishError, relative_path)
        return DocumentHandle.model_validate(response.json())

    async def outcome(self, task_id: str) -> DocumentOutcome:
        """Where the ingestion behind a handle stands right now."""
        response = await self._client.get(f"{self._base_url}/tasks/{task_id}")
        _raise_for(response, DocumentPublishError, f"task {task_id}")
        return DocumentOutcome.model_validate(response.json())

    async def wait(
        self,
        task_id: str,
        *,
        timeout: float = 600.0,
        poll_interval: float = 2.0,
        max_poll_interval: float = 15.0,
    ) -> DocumentOutcome:
        """Follow one ingestion to its end, and return that end whatever it is.

        A failed ingestion is an outcome, not a transport error, so it comes
        back as a value. Only the watching is bounded: past `timeout` this
        raises `DocumentWaitTimeout` and the task itself keeps running. A blip
        on the way to Fred is not an answer either, so it does not end the wait.
        Polls `poll_interval` apart at first, doubling up to `max_poll_interval`.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        interval = poll_interval
        while True:
            try:
                outcome = await self.outcome(task_id)
            except (httpx.TransportError, DocumentPublishError) as error:
                # A refusal (4xx) is Fred's answer about this task; anything
                # else says nothing about it, and it is still running.
                if (
                    isinstance(error, DocumentPublishError)
                    and error.status_code < 500
                    and error.status_code not in _TRANSIENT_STATUSES
                ):
                    raise
                logger.debug("Poll of task %s failed, polling on: %s", task_id, error)
            else:
                if outcome.terminal:
                    return outcome
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise DocumentWaitTimeout(task_id)
            await asyncio.sleep(min(interval, remaining))
            interval = min(interval * 2, max_poll_interval)

    async def documents(self) -> dict[str, str | None]:
        """What the library holds or is about to, by source key, with its version.

        A failed write is left out so the next run writes that key again; one
        still in flight is listed, so a version match on it is not a second write.
        """
        response = await self._client.get(
            f"{self._base_url}/libraries/{self._library_id}/documents",
        )
        _raise_for(response, DocumentPublishError, f"library {self._library_id}")
        listing = response.json()
        if listing.get("truncated"):
            logger.warning(
                "Fred listed only part of library %s; the inventory is incomplete",
                self._library_id,
            )
        # A document without a source key cannot be addressed by this pod at
        # all, so it is not part of what a run reconciles against.
        return {
            item["source_key"]: item.get("document_version")
            for item in listing.get("items", [])
            if item.get("state") != _FAILED and item.get("source_key")
        }

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
        )
        _raise_for(response, DocumentRetractError, relative_path)

    async def source_version(self) -> str | None:
        """What the last run recorded with `record_source_version`, or None.

        Lets a source that can say what changed since a version (a Git
        revision, a change token) resume from Fred rather than keep a ledger.
        """
        response = await self._client.get(
            f"{self._base_url}/libraries/{self._library_id}/source-version",
        )
        _raise_for(response, DocumentPublishError, f"library {self._library_id}")
        return response.json().get("source_version")

    async def record_source_version(self, value: str) -> None:
        """Store how far this library got in its source. Kept verbatim."""
        response = await self._client.put(
            f"{self._base_url}/libraries/{self._library_id}/source-version",
            json={"source_version": value},
        )
        _raise_for(response, DocumentPublishError, f"library {self._library_id}")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DocumentPublisher":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
