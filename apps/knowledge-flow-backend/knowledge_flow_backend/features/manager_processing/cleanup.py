# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded repeated sweeps of manager-authorized obsolete generations."""

import asyncio
import itertools
import logging
from uuid import UUID, uuid5

from knowledge_flow_backend.features.manager_processing.artifacts import Artifacts
from knowledge_flow_backend.features.manager_processing.client import ManagerClient
from knowledge_flow_backend.features.manager_processing.contracts import Cleaned, Work


def sweep(context):
    settings = context.configuration.manager_processing
    artifacts = Artifacts(settings)
    with ManagerClient(settings) as client:
        candidates = client.get("/document-processing/cleanup")
        for candidate in candidates:
            # The manager leases each candidate; a failing one returns later, behind the others.
            try:
                clean(context.get_manager_vector_store, client, artifacts, candidate)
            except Exception:
                logging.getLogger(__name__).warning("Manager cleanup candidate will retry: %s", candidate.get("generation"), exc_info=True)


def clean(store, client, artifacts, candidate):
    work = Work.model_validate(candidate["work"])
    generation = UUID(candidate["generation"])
    if candidate.get("purge_document"):
        store().delete_vectors_for_document(document_uid=str(work.document_id))
        if store().get_document_chunk_count(document_uid=str(work.document_id)) > 0:
            logging.getLogger(__name__).info("Document vector cleanup will retry: %s", work.document_id)
            return
        objects = list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 201))
        for item in objects[:200]:
            if item.object_name is None:
                raise RuntimeError("Invalid object cleanup response")
            artifacts.client.remove_object(artifacts.bucket, item.object_name)
        client.post(
            "/document-processing/cleanup",
            Cleaned(work=work, generation=generation, cursor=0, next_cursor=0, objects_empty=len(objects) <= 200, purge_document=True),
        )
        return
    start = candidate["cursor"]
    end = min(candidate["chunks"], start + candidate["batch"])
    for ordinal in range(start, end):
        if ordinal in candidate["protected_ordinals"]:
            continue
        identifier = str(uuid5(generation, str(ordinal)))
        store().delete_chunk(str(work.document_id), identifier)
        if "text" in store().get_chunk(str(work.document_id), identifier):
            raise RuntimeError("Vector cleanup is incomplete")
    # One complete pass finishes a generation whose lease expired 60 s ago; a
    # later stray write stays until the document purge and is never served.
    objects = [] if candidate["preserve_objects"] else list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 201))
    for item in objects[:200]:
        if item.object_name is None:
            raise RuntimeError("Invalid object cleanup response")
        artifacts.client.remove_object(artifacts.bucket, item.object_name)
    client.post("/document-processing/cleanup", Cleaned(work=work, generation=generation, cursor=start, next_cursor=end, objects_empty=not candidate["preserve_objects"] and len(objects) <= 200))


async def run():
    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    settings = context.configuration.manager_processing
    if settings is None or not settings.enabled:
        return
    while True:
        try:
            await asyncio.to_thread(sweep, context)
        except Exception:
            logging.getLogger(__name__).warning("Manager derived cleanup will retry")
        await asyncio.sleep(30)
