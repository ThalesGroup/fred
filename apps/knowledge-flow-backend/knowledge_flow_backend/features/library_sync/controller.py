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

"""The REST surface a system that synchronizes a source writes through.

Every route answers with something a pod on a schedule can act on: an outcome,
or a task to follow to one. The upload surface streams progress and leaves
success to be inferred from the absence of bad news, which is readable for a
person watching a browser and unusable for a machine.
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fred_core import AuthorizationError, KeycloakUser, get_current_user_without_gcu
from fred_core.security.structure import is_service_agent

from knowledge_flow_backend.common.source_utils import UnknownSourceTagError
from knowledge_flow_backend.core.stores.tags.base_tag_store import TagAlreadyExistsError, TagNotFoundError
from knowledge_flow_backend.features.library_sync.service import LibrarySyncService
from knowledge_flow_backend.features.library_sync.structures import (
    DocumentAccepted,
    DocumentRemoved,
    InvalidSourceRequest,
    LibraryDocuments,
    LibrarySourceVersion,
    LibrarySynchronizedBy,
    SynchronizationUnavailable,
)

logger = logging.getLogger(__name__)


async def require_sync_client(user: KeycloakUser = Depends(get_current_user_without_gcu)) -> KeycloakUser:
    """Admit a workload identity, and nothing else, to mirror a source.

    GCU admission is a person accepting terms; a service account has no such
    record and would be refused outright. Skipping that check is only safe
    because a human token is refused here too. A deployment that authenticates
    is therefore a precondition of synchronizing at all.
    """
    if not is_service_agent(user):
        raise HTTPException(status_code=403, detail="Library synchronization requires a service identity")
    return user


def _bounded_failure(exc: Exception, *, code: str = "document_write_failed") -> HTTPException:
    """What a caller is told about a failure it did not cause.

    The kind of failure and nothing else. An exception's message is written for
    whoever reads the log — it carries server paths, connection strings and
    driver text — and a caller that cannot act on it has no business seeing it.
    The kind is enough to decide: retry a timeout, give up on a value error,
    raise a ticket for anything else. The rest is logged.
    """
    return HTTPException(
        status_code=500,
        detail={"code": code, "failure": type(exc).__name__},
    )


class LibrarySyncController:
    """Routes for a caller that mirrors a source into one library it was granted."""

    def __init__(self, router: APIRouter):
        self.service = LibrarySyncService()

        @router.post(
            "/libraries/{library_id}/documents",
            status_code=202,
            tags=["Library synchronization"],
            summary="Write one document into a library, addressed by the caller's own source key",
            description=(
                "Accepts a document a system synchronizes from its own source and queues it on "
                "the pipeline every upload goes through: the reply carries the document's "
                "identifier and the task to follow to the outcome. The source key names the "
                "document inside the library and is the caller's alone: writing the same key "
                "again updates that document in place, for ever, so a source watched over "
                "months leaves one document per file rather than a version per run. "
                "The optional document version is whatever the source has — an etag, a content "
                "hash, a revision — stored and returned, never interpreted. "
                "Folders along the path are created as needed, authorized by the right to "
                "write in the library. A deployment with no scheduler refuses the write with "
                "503 before storing anything."
            ),
            responses={503: {"description": "A deployment with no scheduler refuses the write before storing anything."}},
        )
        async def write_document(
            library_id: str,
            background_tasks: BackgroundTasks,
            file: Annotated[UploadFile, File(description="The document's bytes.")],
            path: Annotated[str, Form(description="Where the document goes inside the library, e.g. 'specs/api/openapi.md'.")],
            source_key: Annotated[str, Form(description="The caller's own name for this document, unique within the library.")],
            document_version: Annotated[Optional[str], Form(description="The source's version of this document. Opaque to Fred.")] = None,
            source_tag: Annotated[str, Form(description="Which configured document source this caller is.")] = "fred",
            user: KeycloakUser = Depends(require_sync_client),
        ) -> DocumentAccepted:
            try:
                return await self.service.write_document(
                    user,
                    library_id=library_id,
                    path=path,
                    source_key=source_key,
                    document_version=document_version,
                    source_tag=source_tag,
                    upload=file,
                    background_tasks=background_tasks,
                )
            except InvalidSourceRequest as exc:
                raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
            except UnknownSourceTagError as exc:
                raise HTTPException(status_code=400, detail={"code": "unknown_source_tag", "message": str(exc)})
            except SynchronizationUnavailable as exc:
                raise HTTPException(status_code=503, detail={"code": "scheduling_unavailable", "message": str(exc)})
            except (AuthorizationError, HTTPException, TagAlreadyExistsError, TagNotFoundError):
                # Each already has an answer of its own registered on the app;
                # swallowing them into a 500 below would lose it.
                raise
            except Exception as exc:
                logger.exception("[LIBRARY SYNC] Write failed for library=%s", library_id)
                raise _bounded_failure(exc)

        @router.delete(
            "/libraries/{library_id}/documents",
            tags=["Library synchronization"],
            summary="Take one document out of a library, addressed by its source key",
            description=(
                "Removes the document written under this source key. The library's own name, "
                "description and other documents are untouched, and a key the library does not "
                "hold is not an error. Fred never removes a document because a caller stopped "
                "mentioning it: silence is not a removal."
            ),
        )
        async def remove_document(
            library_id: str,
            source_key: Annotated[str, Query(description="The key the document was written under.")],
            user: KeycloakUser = Depends(require_sync_client),
        ) -> DocumentRemoved:
            try:
                return await self.service.remove_document(user, library_id=library_id, source_key=source_key)
            except InvalidSourceRequest as exc:
                raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})

        @router.get(
            "/libraries/{library_id}/documents",
            tags=["Library synchronization"],
            response_model=LibraryDocuments,
            summary="List what a library holds under the caller's source keys, and where each write stands",
            description=(
                "Returns the documents written into this library by key, in key order, each with "
                "the identifier Fred gave it, the version the caller last sent, and where its "
                "ingestion stands. A run reconciles against 'succeeded' and 'in_progress' alike — "
                "a version match on a write still owed its outcome is not a second write; 'failed' "
                "is one the pipeline refused, which the next write of that key takes again. "
                "A person's upload into the same library "
                "carries no key and is not listed. The listing is bounded, and says so when it is "
                "short of the whole library."
            ),
        )
        async def list_documents(
            library_id: str,
            limit: Annotated[int, Query(ge=1, le=5000, description="At most this many documents, in key order.")] = 5000,
            user: KeycloakUser = Depends(require_sync_client),
        ) -> LibraryDocuments:
            try:
                return await self.service.list_documents(user, library_id=library_id, limit=limit)
            except (AuthorizationError, HTTPException):
                raise
            except Exception as exc:
                logger.exception("[LIBRARY SYNC] Read failed for library=%s", library_id)
                raise _bounded_failure(exc, code="library_read_failed")

        @router.get(
            "/libraries/{library_id}/source-version",
            tags=["Library synchronization"],
            summary="Read the version of its own source this library last accepted",
            description=(
                "Returns what a caller last recorded, exactly as given, or null if it never "
                "recorded one. This is what lets a pull-mode caller be driven by its own "
                "source — ask Fred where it got to, ask the source what changed since — "
                "instead of keeping a ledger of its own."
            ),
        )
        async def read_source_version(
            library_id: str,
            user: KeycloakUser = Depends(require_sync_client),
        ) -> LibrarySourceVersion:
            return LibrarySourceVersion(source_version=await self.service.read_source_version(user, library_id))

        @router.put(
            "/libraries/{library_id}/synchronized-by",
            tags=["Library synchronization"],
            summary="Record which machine fills this library",
            description=(
                "Marks the library as filled by a machine, which is what stops people from "
                "changing what it holds: no upload, no document added or removed, no folder "
                "created inside it, no rename. Deleting it stays available to whoever may "
                "delete a folder. The reference is qualified — 'knowledge_base:<id>' — and "
                "opaque: Fred acts on its presence, never on what it names. Recording the "
                "same machine again is not a change, so a retry is safe; recording a "
                "different one is refused rather than applied."
            ),
        )
        async def record_synchronized_by(
            library_id: str,
            body: LibrarySynchronizedBy,
            user: KeycloakUser = Depends(require_sync_client),
        ) -> LibrarySynchronizedBy:
            try:
                recorded = await self.service.record_synchronized_by(user, library_id, body.synchronized_by)
            except InvalidSourceRequest as exc:
                raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
            return LibrarySynchronizedBy(synchronized_by=recorded)

        @router.put(
            "/libraries/{library_id}/source-version",
            tags=["Library synchronization"],
            summary="Record the version of its own source this library has reached",
            description="Stores the value verbatim. Fred never parses, orders or dates it.",
        )
        async def record_source_version(
            library_id: str,
            body: LibrarySourceVersion,
            user: KeycloakUser = Depends(require_sync_client),
        ) -> LibrarySourceVersion:
            try:
                recorded = await self.service.record_source_version(user, library_id, body.source_version)
            except InvalidSourceRequest as exc:
                raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
            return LibrarySourceVersion(source_version=recorded)
