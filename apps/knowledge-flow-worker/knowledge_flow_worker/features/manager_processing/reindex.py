# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Resume a leased document using published, integrity-checked chunk artifacts.

The manager owns progress and the physical namespace. Replayed writes retain the
published chunk IDs. An expired writer can only touch its old corpus namespace.
"""

from __future__ import annotations

import copy
import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fred_knowledge.artifacts.contracts import Artifact, Contract
from fred_knowledge.artifacts.errors import ManagerError
from fred_knowledge.vector.cancellation import WorkCancelled, raise_if_cancelled
from fred_sdk.contracts.weaver import InferenceAdmission
from langchain_core.documents import Document
from pydantic import Field
from temporalio import activity
from temporalio.exceptions import ApplicationError

from knowledge_flow_worker.features.manager_processing.artifacts import Artifacts
from knowledge_flow_worker.features.manager_processing.client import ManagerClient, raise_permanent_failure
from knowledge_flow_worker.features.manager_processing.contracts import StageModels
from knowledge_flow_worker.features.scheduler.activity_utils import to_thread_with_heartbeat

if TYPE_CHECKING:
    from knowledge_flow_worker.application_context import ApplicationContext


class ReindexDocument(Contract):
    document_id: UUID
    generation: UUID
    prefix: str
    artifact: Artifact
    space_id: UUID
    session_id: UUID | None
    retrievable: bool
    folder_path: str | None


class VectorReindexWork(Contract):
    id: UUID
    execution_id: UUID
    organization_id: UUID
    lease: UUID
    admission: InferenceAdmission
    document: ReindexDocument
    offset: int = Field(ge=0)


class ReindexProgress(Contract):
    execution_id: UUID
    lease: UUID
    document_id: UUID
    succeeded: bool
    offset: int = Field(ge=0)
    finished: bool


class ClaimVectorReindex(Contract):
    execution_id: UUID


class RetiredCorpus(Contract):
    organization_id: UUID
    corpus_generation: UUID | None


class RetiredCorpusProgress(RetiredCorpus):
    complete: bool


class PublishedChunk(Contract):
    id: UUID
    text: str = Field(max_length=4_194_304)
    # Published chunk metadata is processor-specific, as in ScopedVectors.
    metadata: dict[str, Any]


def step(context: ApplicationContext, client: ManagerClient, id: UUID, claim: ClaimVectorReindex) -> bool:
    payload = client.post(f"/document-processing/vector-reindex/{id}/claim", claim)
    if payload is None:
        return False
    work = VectorReindexWork.model_validate(payload)
    if work.id != id or work.execution_id != claim.execution_id or work.admission.corpus_generation != id:
        raise ManagerError("integrity_failure", permanent=True)
    try:
        rebuild(context, client, work)
    except (WorkCancelled, ApplicationError):
        raise
    except Exception as error:
        logging.getLogger(__name__).warning("Corpus reconstruction failed", extra={"operation_id": str(id), "reason": type(error).__name__})
        progress(client, work, succeeded=False, offset=work.offset, finished=False)
    return True


def cleanup_retired(context: ApplicationContext, client: ManagerClient) -> None:
    for payload in client.get("/document-processing/vector-reindex/retired"):
        retired = RetiredCorpus.model_validate(payload)
        store = context.get_corpus_store(retired.organization_id, corpus_generation=retired.corpus_generation)
        try:
            complete = not store.index_exists() or store.drop_corpus()
        except Exception as error:
            logging.getLogger(__name__).warning("Retired corpus cleanup will retry", extra={"reason": type(error).__name__})
            complete = False
        client.post("/document-processing/vector-reindex/retired", RetiredCorpusProgress(**retired.model_dump(), complete=complete))


def progress(client: ManagerClient, work: VectorReindexWork, *, succeeded: bool, offset: int, finished: bool) -> None:
    raise_if_cancelled("vector reindex checkpoint")
    try:
        accepted = client.post(
            f"/document-processing/vector-reindex/{work.id}",
            ReindexProgress(execution_id=work.execution_id, lease=work.lease, document_id=work.document.document_id, succeeded=succeeded, offset=offset, finished=finished),
        )
    except ManagerError as error:
        # An unacknowledged checkpoint is not proof that a vector write failed.
        raise ApplicationError("Corpus checkpoint unavailable", non_retryable=error.permanent) from None
    if not accepted:
        raise ApplicationError("Corpus reconstruction failed", non_retryable=True)


def rebuild(context: ApplicationContext, client: ManagerClient, work: VectorReindexWork) -> None:
    settings = context.configuration.manager_processing
    if settings is None or work.document.artifact.size > min(settings.temporary_bytes, 536_870_912):
        raise ManagerError("capacity_exceeded", permanent=True)
    scoped = copy.copy(context)
    scoped.admit_models(StageModels(embedding=work.admission, vision=None))
    store = scoped.get_corpus_store(work.organization_id)
    source = work.document
    with tempfile.TemporaryDirectory(prefix="fred-reindex-") as directory:
        path = Path(directory) / "chunks.jsonl"
        Artifacts(settings).read(source.prefix, source.artifact, path)
        documents: list[Document] = []
        identifiers: list[str] = []
        count = 0
        with path.open(encoding="utf-8") as chunks:
            for count, line in enumerate(chunks, 1):
                raise_if_cancelled("vector reindex chunk")
                if count <= work.offset:
                    continue
                chunk = PublishedChunk.model_validate(json.loads(line))
                if chunk.metadata.get("document_uid") != str(source.document_id) or chunk.metadata.get("chunk_uid") != str(chunk.id):
                    raise ManagerError("integrity_failure", permanent=True)
                metadata = dict(chunk.metadata)
                metadata.pop("embedding_model", None)
                metadata.pop("vector_index", None)
                metadata.update(
                    organization_id=str(work.organization_id),
                    space_id=str(source.space_id),
                    session_id=str(source.session_id) if source.session_id else "",
                    retrievable=source.retrievable,
                    folder_path=source.folder_path or "",
                )
                documents.append(Document(page_content=chunk.text, metadata=metadata))
                identifiers.append(str(chunk.id))
                if len(documents) == 64:
                    if set(store.add_documents(documents, ids=identifiers)) != set(identifiers):
                        raise ManagerError("indexing_failed")
                    progress(client, work, succeeded=True, offset=count, finished=False)
                    documents.clear()
                    identifiers.clear()
        if documents:
            raise_if_cancelled("vector reindex batch")
            if set(store.add_documents(documents, ids=identifiers)) != set(identifiers):
                raise ManagerError("indexing_failed")
        if count < work.offset:
            raise ManagerError("integrity_failure", permanent=True)
        progress(client, work, succeeded=True, offset=count, finished=True)


@activity.defn(name="reindex_next_document")
async def reindex_next_document(execution: dict[str, str]) -> bool:
    from knowledge_flow_worker.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    settings = context.configuration.manager_processing
    if settings is None:
        raise ApplicationError("Missing document processing configuration", non_retryable=True)
    identifier = UUID(execution["id"])
    claim = ClaimVectorReindex(execution_id=UUID(execution["execution_id"]))

    def process() -> bool:
        with ManagerClient(settings) as client:
            return step(context, client, identifier, claim)

    try:
        return await to_thread_with_heartbeat(process, heartbeat_details={"operation_id": str(identifier)}, drain_on_cancel=True)
    except Exception as error:
        raise_permanent_failure(error)
        raise
