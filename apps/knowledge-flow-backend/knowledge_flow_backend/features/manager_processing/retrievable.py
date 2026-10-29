# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One fenced writer, then repeatable projection verification and SQL confirmation."""

from contextlib import contextmanager
from uuid import UUID, uuid5

from temporalio import activity

from knowledge_flow_backend.features.manager_processing.client import ManagerClient, ManagerError, raise_permanent_failure
from knowledge_flow_backend.features.manager_processing.contracts import RetrievalConfirmation, RetrievalWork


@contextmanager
def retrieval_work(command):
    from knowledge_flow_backend.application_context import ApplicationContext

    try:
        context = ApplicationContext.get_instance()
        settings = context.configuration.manager_processing
        if settings is None or not settings.enabled:
            raise ManagerError("worker_failed", permanent=True)
        document_id = str(UUID(command["document_id"]))
        operation_id = UUID(command["operation_id"])
        path = f"/document-processing/retrievable/{document_id}"
        with ManagerClient(settings) as client:
            work = RetrievalWork.model_validate(client.get(f"{path}?operation_id={operation_id}"))
            if str(work.document_id) != document_id or work.operation_id != operation_id:
                raise ManagerError("integrity_failure", permanent=True)
            ids = [str(uuid5(work.manifest.generation, str(i))) for i in work.manifest.vector_ordinals]
            if len(ids) != work.manifest.vectors or len(set(ids)) != len(ids) or (work.retrievable and not ids):
                raise ManagerError("integrity_failure", permanent=True)
            yield context, client, path, work, ids
    except Exception as error:
        raise_permanent_failure(error)
        raise


def callback(client, path, work, step):
    client.post(path, RetrievalConfirmation(operation_id=work.operation_id, retrievable=work.retrievable, step=step))


@activity.defn(name="set_document_retrievable")
def set_document_retrievable(command: dict) -> bool:
    with retrieval_work(command) as (context, client, path, work, ids):
        if work.confirmed or work.phase == "applied":
            return False
        if work.phase != "ready":
            raise ManagerError("retrieval_projection_uncertain", permanent=True)
        # Claim is deliberately not replayable: a lost claim response cannot admit a writer.
        callback(client, path, work, "claim")
        if not ids:
            raise ManagerError("indexing_failed", permanent=True)
        context.get_manager_vector_store().set_chunks_retrievable(document_uid=str(work.document_id), chunk_ids=ids, value=work.retrievable)
        return True


@activity.defn(name="record_retrievable_applied")
def record_retrievable_applied(command: dict) -> None:
    # Only scheduled after the writer activity successfully returns in Temporal history.
    with retrieval_work(command) as (_, client, path, work, _ids):
        if not work.confirmed:
            callback(client, path, work, "applied")


@activity.defn(name="confirm_document_retrievable")
def confirm_document_retrievable(command: dict) -> None:
    with retrieval_work(command) as (context, client, path, work, ids):
        if work.confirmed:
            return
        if work.phase != "applied":
            raise ManagerError("retrieval_projection_uncertain", permanent=True)
        if ids:
            context.get_manager_vector_store().verify_chunks_retrievable(document_uid=str(work.document_id), chunk_ids=ids, value=work.retrievable)
        callback(client, path, work, "confirm")
