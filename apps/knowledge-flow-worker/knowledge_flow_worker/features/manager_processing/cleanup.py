# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded repeated sweeps of manager-authorized obsolete generations."""

import asyncio
import itertools
import logging
from uuid import UUID, uuid5

from fred_core.logs.log_setup import dependency_wait_level
from fred_knowledge.artifacts.errors import ManagerError

from knowledge_flow_worker.features.manager_processing.artifacts import Artifacts
from knowledge_flow_worker.features.manager_processing.client import ManagerClient
from knowledge_flow_worker.features.manager_processing.contracts import Cleaned, Work


def sweep(context):
    settings = context.configuration.manager_processing
    artifacts = Artifacts(settings)
    with ManagerClient(settings) as client:
        candidates = client.get("/document-processing/cleanup")
        for candidate in candidates:
            # The manager leases each candidate; a failing one returns later, behind the others.
            try:
                work = Work.model_validate(candidate["work"])
                clean(lambda: context.get_corpus_store(work.organization_id), client, artifacts, candidate)
            except Exception as error:
                # One line per sweep and candidate: the cause, not a repeated traceback.
                logging.getLogger(__name__).warning("Manager cleanup candidate will retry: %s cause=%s", candidate.get("generation"), _cause(error))


def clean(store, client, artifacts, candidate):
    work = Work.model_validate(candidate["work"])
    generation = UUID(candidate["generation"])
    # An organization that never indexed a document has no corpus index, hence no vectors.
    indexed = store().index_exists()
    if candidate.get("purge_document"):
        if indexed:
            store().delete_vectors_for_document(document_uid=str(work.document_id))
        if indexed and store().get_document_chunk_count(document_uid=str(work.document_id)) > 0:
            logging.getLogger(__name__).info("Document vector cleanup will retry: %s", work.document_id)
            return
        objects = list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 201))
        for item in objects[:200]:
            if item.object_name is None:
                raise RuntimeError("Invalid object cleanup response")
            artifacts.client.remove_object(artifacts.bucket, item.object_name)
        client.post(
            "/document-processing/cleanup",
            Cleaned(
                work=work,
                generation=generation,
                cursor=0,
                next_cursor=0,
                objects_empty=not list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 1)),
                purge_document=True,
            ),
        )
        return
    start = candidate["cursor"]
    end = min(candidate["chunks"], start + candidate["batch"])
    for ordinal in range(start if indexed else end, end):
        if ordinal in candidate["protected_ordinals"]:
            continue
        identifier = str(uuid5(generation, str(ordinal)))
        store().delete_chunk(str(work.document_id), identifier)
        if "text" in store().get_chunk(str(work.document_id), identifier):
            raise RuntimeError("Vector cleanup is incomplete")
    # The manager only releases candidates after every admitted write acknowledged.
    # An uncertain request never becomes safe merely because its lease expired.
    objects = [] if candidate["preserve_objects"] else list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 201))
    for item in objects[:200]:
        if item.object_name is None:
            raise RuntimeError("Invalid object cleanup response")
        artifacts.client.remove_object(artifacts.bucket, item.object_name)
    client.post(
        "/document-processing/cleanup",
        Cleaned(
            work=work,
            generation=generation,
            cursor=start,
            next_cursor=end,
            objects_empty=not candidate["preserve_objects"] and not list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 1)),
        ),
    )


async def run():
    from knowledge_flow_worker.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    settings = context.configuration.manager_processing
    if settings is None:
        return
    while True:
        try:
            await asyncio.to_thread(sweep, context)
        except Exception as error:
            # The Control Plane may still be starting: routine at first, a WARNING later.
            logging.getLogger(__name__).log(dependency_wait_level(), "Manager derived cleanup will retry", extra={"reason": _cause(error)})
        await asyncio.sleep(30)


def _cause(error: BaseException) -> str:
    """Name a failure without its message: responses and credentials stay out of logs."""
    if isinstance(error, ManagerError):
        return f"{error.code} {error.reason}" if error.reason else error.code
    return type(error).__name__
