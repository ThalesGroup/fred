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
    vectors = None
    with ManagerClient(settings) as client:
        candidates = client.get("/document-processing/cleanup")
        for candidate in candidates:
            work = Work.model_validate(candidate["work"])
            generation = UUID(candidate["generation"])
            start = candidate["cursor"]
            end = min(candidate["chunks"], start + candidate["batch"])
            if end > start:
                if vectors is None:
                    vectors = context.get_manager_vector_store()
                for ordinal in range(start, end):
                    if ordinal in candidate["protected_ordinals"]:
                        continue
                    identifier = str(uuid5(generation, str(ordinal)))
                    vectors.delete_chunk(str(work.document_id), identifier)
                    if "text" in vectors.get_chunk(str(work.document_id), identifier):
                        raise RuntimeError("Vector cleanup is incomplete")
            # Keep sweeping even after a clean observation: a delayed remote write
            # cannot escape because IDs remain derivable from the retained fence.
            objects = [] if candidate["preserve_objects"] else list(itertools.islice(artifacts.client.list_objects(artifacts.bucket, prefix=candidate["output_prefix"], recursive=True), 201))
            for item in objects[:200]:
                if item.object_name is None:
                    raise RuntimeError("Invalid object cleanup response")
                artifacts.client.remove_object(artifacts.bucket, item.object_name)
            client.post(
                "/document-processing/cleanup", Cleaned(work=work, generation=generation, cursor=start, next_cursor=end, objects_empty=not candidate["preserve_objects"] and len(objects) <= 200)
            )


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
