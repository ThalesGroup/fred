# Copyright Thales 2025
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
Temporal worker responsible for running ingestion pipelines.

One process serves one or more roles (`scheduler.worker_roles`), each with its own
Temporal worker on its own queue: the common role runs every workflow and every
activity but extraction, while an extraction role runs nothing but the two
extraction activities for one processing profile. A Kubernetes deployment declares
a single role so its pods size and scale independently; a developer's single
process declares all four.
"""

import asyncio
import concurrent.futures
import logging
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from knowledge_flow_backend.common.structures import (
    IngestionWorkerRole,
    TemporalSchedulerConfig,
    extraction_task_queue,
)
from knowledge_flow_backend.features.scheduler.activities import (
    delete_vectors,
    emit_ingestion_task_event,
    fast_delete_vectors,
    fast_store_vectors,
    get_chunk_count,
    list_documents_in_scope,
    mark_document_vectorized,
    output_process,
    output_process_trusted,
    prepare_revectorize_file,
)
from knowledge_flow_backend.features.scheduler.pdf_render_expiry_activities import expire_pdf_renders
from knowledge_flow_backend.features.scheduler.pdf_render_expiry_schedule import sync_pdf_render_expiry_schedule
from knowledge_flow_backend.features.scheduler.pdf_render_expiry_workflow import ExpirePdfRendersWorkflow
from knowledge_flow_backend.features.scheduler.pull_files_activities import (
    create_pull_file_metadata,
    pull_input_process,
)
from knowledge_flow_backend.features.scheduler.push_files_activities import (
    get_push_file_metadata,
    push_input_process,
)
from knowledge_flow_backend.features.scheduler.repair_vector_metadata_activities import (
    bulk_repair_vector_metadata,
    emit_repair_vector_metadata_task_event,
    list_repair_candidates_for_source_tag,
    list_strict_content_document_uids,
    list_strict_vector_document_uids,
)
from knowledge_flow_backend.features.scheduler.repair_vector_metadata_workflow import RepairVectorMetadataWorkflow
from knowledge_flow_backend.features.scheduler.workflow import (
    CreatePullFileMetadata,
    FastDeleteVectors,
    FastStoreVectors,
    GetPushFileMetadata,
    OutputProcess,
    ProcessPull,
    ProcessPullFile,
    ProcessPush,
    ProcessPushFile,
    PullInputProcess,
    PushInputProcess,
    RevectorizeCorpusWorkflow,
    RevectorizeDocument,
)

logger = logging.getLogger(__name__)

# Every workflow in the ingestion namespace, plus the recurring-maintenance one.
# They run on the common queue whatever profile their documents carry: only the
# extraction activity is routed away.
_COMMON_WORKFLOWS = [
    ProcessPull,
    ProcessPullFile,
    ProcessPush,
    ProcessPushFile,
    CreatePullFileMetadata,
    GetPushFileMetadata,
    PullInputProcess,
    PushInputProcess,
    OutputProcess,
    FastStoreVectors,
    FastDeleteVectors,
    RevectorizeCorpusWorkflow,
    RevectorizeDocument,
    RepairVectorMetadataWorkflow,
    ExpirePdfRendersWorkflow,
]

# The two heavy, profile-dependent activities, and the only ones an extraction
# role registers. Everything else — metadata, progress events, indexing, repair,
# maintenance — belongs to the common role below.
_EXTRACTION_ACTIVITIES = [
    pull_input_process,
    push_input_process,
]

_COMMON_ACTIVITIES = [
    create_pull_file_metadata,
    get_push_file_metadata,
    output_process,
    output_process_trusted,
    fast_store_vectors,
    fast_delete_vectors,
    emit_ingestion_task_event,
    list_documents_in_scope,
    get_chunk_count,
    delete_vectors,
    prepare_revectorize_file,
    mark_document_vectorized,
    list_repair_candidates_for_source_tag,
    list_strict_vector_document_uids,
    list_strict_content_document_uids,
    bulk_repair_vector_metadata,
    emit_repair_vector_metadata_task_event,
    expire_pdf_renders,
]


def _role_task_queue(config: TemporalSchedulerConfig, role: IngestionWorkerRole) -> str:
    """The queue a role polls. Derived through the same function the submission
    side uses, so the two cannot name a queue differently."""
    profile = role.extraction_profile
    return config.task_queue if profile is None else extraction_task_queue(config.task_queue, profile)


def _build_worker(
    *,
    client: Client,
    config: TemporalSchedulerConfig,
    role: IngestionWorkerRole,
    workflow_task_concurrency: int,
    activity_concurrency: int,
) -> Worker:
    """One Temporal worker for one role, registering only what that role runs."""
    is_common = role is IngestionWorkerRole.common
    queue = _role_task_queue(config, role)
    if is_common:
        logger.info(
            "[SCHEDULER] role=%s queue=%s max_concurrent_activities=%d max_concurrent_workflow_tasks=%d",
            role.value,
            queue,
            activity_concurrency,
            workflow_task_concurrency,
        )
    else:
        # No workflow is registered here, so the workflow-task limit would say
        # nothing about what this pod actually does.
        logger.info(
            "[SCHEDULER] role=%s queue=%s max_concurrent_activities=%d (extraction only, no workflows)",
            role.value,
            queue,
            activity_concurrency,
        )

    return Worker(
        client=client,
        task_queue=queue,
        workflows=_COMMON_WORKFLOWS if is_common else [],
        activities=_COMMON_ACTIVITIES if is_common else _EXTRACTION_ACTIVITIES,
        # Sync activities run in threads; one pool per role keeps a saturated
        # extraction role from starving the common one in a multi-role process.
        activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=activity_concurrency),
        max_concurrent_workflow_tasks=workflow_task_concurrency,
        max_concurrent_activities=activity_concurrency,
        # Heartbeat responses are how the server tells a running activity it was
        # cancelled, and the SDK throttles outgoing heartbeats — by default to
        # min(80% of heartbeat_timeout, 60s), i.e. one per minute with our 300s
        # timeouts, no matter how often the activity calls heartbeat(). That
        # throttle IS the cancellation latency: a user's stop took ~40s to reach
        # the vectorization stage (#2315). 5s makes a cancel land in seconds for
        # one cheap RPC per running activity every 5s.
        max_heartbeat_throttle_interval=timedelta(seconds=5),
        default_heartbeat_throttle_interval=timedelta(seconds=5),
    )


async def run_worker(
    config: TemporalSchedulerConfig,
    *,
    roles: list[IngestionWorkerRole] | None = None,
    max_concurrent_workflow_tasks: int = 1,
    max_concurrent_activities: int = 1,
    pdf_render_ttl_days: int = 30,
):
    """
    Connect to Temporal and start one worker per configured role.

    Why:
        Extraction is the expensive, profile-dependent stage; serving it from its
        own queue and pods keeps a slow document from holding the activity slots
        a cheap one needs. Workflow-task and activity concurrency have different
        runtime bottlenecks, so they stay independently configured.
    How:
        Build one `Worker` per role — the common role registers every workflow and
        every activity but extraction, an extraction role registers nothing but the
        two extraction activities — and run them together until one stops.
    Usage example:
        `await run_worker(config, roles=[IngestionWorkerRole.extraction_rich], max_concurrent_activities=1)`

    Args:
        config (TemporalSchedulerConfig): Temporal connection + base task queue.
        roles (list[IngestionWorkerRole] | None): Roles this process serves;
            defaults to the common role alone.
        max_concurrent_workflow_tasks (int): Max concurrent workflow tasks per role.
        max_concurrent_activities (int): Max concurrent activity tasks per role.
        pdf_render_ttl_days (int): Lifetime of cached PDF renders; drives the
            nightly expiry Schedule (0 removes it).
    """
    active_roles = list(roles) if roles else [IngestionWorkerRole.common]
    workflow_task_concurrency = max(1, int(max_concurrent_workflow_tasks))
    activity_concurrency = max(1, int(max_concurrent_activities))

    logger.info(f"🔗 Connecting to Temporal at {config.host} (namespace={config.namespace})")
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
    )

    # The Schedule always targets the common queue, which is where its workflow is
    # registered, so an extraction role has nothing to post and nothing to move.
    if IngestionWorkerRole.common in active_roles:
        # Housekeeping must never keep ingestion from starting: log and carry on.
        try:
            await sync_pdf_render_expiry_schedule(client, config, pdf_render_ttl_days)
        except Exception:  # noqa: BLE001
            logger.exception("[SCHEDULER] Could not sync the PDF render expiry schedule; ingestion worker starts anyway")
    else:
        logger.info("[SCHEDULER] Extraction-only worker; maintenance schedules stay with the common role")

    workers = [
        _build_worker(
            client=client,
            config=config,
            role=role,
            workflow_task_concurrency=workflow_task_concurrency,
            activity_concurrency=activity_concurrency,
        )
        for role in active_roles
    ]

    if len(workers) > 1:
        logger.info(
            "[SCHEDULER] %d roles in this process: up to %d activities at once across them",
            len(workers),
            len(workers) * activity_concurrency,
        )
    logger.info("[SCHEDULER] Temporal worker is now running and ready to receive ingestion jobs.")
    # A TaskGroup, not gather: when one role's worker dies the others must be
    # cancelled before the caller's shutdown disposes the database engine and the
    # KPI writer their activities are still using.
    async with asyncio.TaskGroup() as group:
        for worker in workers:
            group.create_task(worker.run())
