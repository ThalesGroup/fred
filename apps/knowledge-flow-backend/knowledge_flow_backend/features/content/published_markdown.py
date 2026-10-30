# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The published markdown source shared by the three document capabilities."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fred_core.documents.access import SpaceNotFoundError, SpacePendingDeletionError, published_artifact, resolve_scope
from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser
from minio.error import S3Error
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.document_scope import document_access_context
from knowledge_flow_backend.features.manager_processing.contracts import Artifact
from knowledge_flow_backend.security.weaver_admission import _space_error, delegated_person, require_space_read


async def published_markdown(person: AssertedUser, document_uid: str, access: DocumentAccessContext) -> str:
    await require_space_read(person, access.space_id)
    context = ApplicationContext.get_instance()
    try:
        async with context.get_pg_async_engine().connect() as conn:
            scope = await resolve_scope(conn, access, user_id=person.uid)
            try:
                document_id = UUID(document_uid)
            except ValueError:
                raise HTTPException(status_code=404, detail="document_not_found") from None
            artifact = await published_artifact(conn, scope, document_id, "output.md")
    except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
        raise _space_error(exc) from None
    if artifact is None:
        raise HTTPException(status_code=404, detail="document_not_found")
    try:
        content = await asyncio.to_thread(
            context.get_published_artifact_reader().read_bytes,
            artifact.prefix,
            Artifact(path="output.md", size=artifact.size, sha256=artifact.sha256),
        )
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchObject"):
            raise HTTPException(status_code=404, detail="document_not_found") from None
        raise
    return content.decode("utf-8")


class MarkdownResponse(BaseModel):
    content: str = Field(description="Full UTF-8 text of the authorized published output.md artifact; no pagination or response-size limit is imposed here.")


class MarkdownController:
    def __init__(self, router: APIRouter):
        @router.get(
            "/documents/{document_uid}/markdown",
            tags=["Documents"],
            response_model=MarkdownResponse,
            operation_id="get_document_markdown",
            summary="Read a document's full published markdown",
            description="Returns the published output.md text after shared space, corpus selection or explicit conversation attachment, ownership and lifecycle checks. Not an original binary download. Missing or non-visible documents return 404. No pagination; clients must budget for the whole response.",
        )
        async def markdown(
            document_uid: str,
            context: DocumentAccessContext = Depends(document_access_context),
            person: AssertedUser = Depends(delegated_person),
        ) -> MarkdownResponse:
            return MarkdownResponse(content=await published_markdown(person, document_uid, context))
