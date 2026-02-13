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

This worker supports role-based queue topology:
- orchestrator: parent workflows + status tracking activities
- io: metadata/load workflow steps
- cpu: processing/vector workflow steps
- all: starts all roles in the same process (default, local-friendly)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import inspect
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Sequence

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client
from temporalio.worker import Worker

from knowledge_flow_backend.common.structures import TemporalSchedulerConfig
from knowledge_flow_backend.features.scheduler.activities import (
    create_pull_file_metadata,
    fast_delete_vectors,
    fast_store_vectors,
    get_push_file_metadata,
    input_process,
    load_pull_file,
    load_push_file,
    output_process,
    record_current_document,
    record_workflow_status,
)
from knowledge_flow_backend.features.scheduler.workflow import (
    CreatePullFileMetadata,
    FastDeleteVectors,
    FastStoreVectors,
    GetPushFileMetadata,
    InputProcess,
    LoadPullFile,
    LoadPushFile,
    OutputProcess,
    Process,
    ProcessFile,
)

logger = logging.getLogger(__name__)

ROLE_ALL = "all"
ROLE_ORCHESTRATOR = "orchestrator"
ROLE_IO = "io"
ROLE_CPU = "cpu"


@dataclass(frozen=True)
class _WorkerRoleSpec:
    role: str
    task_queue: str
    workflows: tuple[type, ...]
    activities: tuple[Callable, ...]


@dataclass
class _MergedQueueSpec:
    roles: list[str]
    workflows: list[type]
    activities: list[Callable]


def _dedupe_ordered(items: Sequence) -> list:
    return list(OrderedDict((item, None) for item in items).keys())


def _role_specs(config: TemporalSchedulerConfig) -> list[_WorkerRoleSpec]:
    workflow_queue = config.get_workflow_task_queue()
    io_queue = config.get_io_task_queue()
    cpu_queue = config.get_cpu_task_queue()

    base_specs = [
        _WorkerRoleSpec(
            role=ROLE_ORCHESTRATOR,
            task_queue=workflow_queue,
            workflows=(Process, ProcessFile),
            activities=(record_current_document, record_workflow_status),
        ),
        _WorkerRoleSpec(
            role=ROLE_IO,
            task_queue=io_queue,
            workflows=(CreatePullFileMetadata, GetPushFileMetadata, LoadPullFile, LoadPushFile),
            activities=(create_pull_file_metadata, get_push_file_metadata, load_pull_file, load_push_file),
        ),
        _WorkerRoleSpec(
            role=ROLE_CPU,
            task_queue=cpu_queue,
            workflows=(InputProcess, OutputProcess, FastStoreVectors, FastDeleteVectors),
            activities=(input_process, output_process, fast_store_vectors, fast_delete_vectors),
        ),
    ]

    if config.worker_role != ROLE_ALL:
        return [spec for spec in base_specs if spec.role == config.worker_role]

    # Merge specs by queue for backward compatibility when all queues are identical.
    by_queue: dict[str, _MergedQueueSpec] = {}
    for spec in base_specs:
        if spec.task_queue not in by_queue:
            by_queue[spec.task_queue] = _MergedQueueSpec(
                roles=[spec.role],
                workflows=list(spec.workflows),
                activities=list(spec.activities),
            )
            continue
        merged = by_queue[spec.task_queue]
        merged.roles.append(spec.role)
        merged.workflows.extend(spec.workflows)
        merged.activities.extend(spec.activities)

    merged_specs: list[_WorkerRoleSpec] = []
    for queue, data in by_queue.items():
        roles = "+".join(data.roles)
        workflows = tuple(_dedupe_ordered(data.workflows))
        activities = tuple(_dedupe_ordered(data.activities))
        merged_specs.append(
            _WorkerRoleSpec(
                role=roles,
                task_queue=queue,
                workflows=workflows,
                activities=activities,
            )
        )
    return merged_specs


def _create_activity_executor(
    config: TemporalSchedulerConfig,
    activities: Sequence[Callable],
) -> concurrent.futures.ThreadPoolExecutor | None:
    has_sync_activity = any(not inspect.iscoroutinefunction(activity_fn) for activity_fn in activities)
    if not has_sync_activity:
        return None
    if config.activity_executor_max_workers is None:
        return concurrent.futures.ThreadPoolExecutor()
    return concurrent.futures.ThreadPoolExecutor(max_workers=config.activity_executor_max_workers)


def _create_workflow_task_executor(
    config: TemporalSchedulerConfig,
) -> concurrent.futures.ThreadPoolExecutor | None:
    if config.workflow_task_executor_max_workers is None:
        return None
    return concurrent.futures.ThreadPoolExecutor(max_workers=config.workflow_task_executor_max_workers)


async def _log_queue_stats_loop(
    client: Client,
    *,
    namespace: str,
    task_queues: Sequence[str],
    interval_seconds: float,
) -> None:
    unique_queues = list(OrderedDict((name, None) for name in task_queues if name).keys())
    while True:
        for queue_name in unique_queues:
            for queue_type, queue_type_name in (
                (TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW, "workflow"),
                (TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY, "activity"),
            ):
                try:
                    response = await client.workflow_service.describe_task_queue(
                        DescribeTaskQueueRequest(
                            namespace=namespace,
                            task_queue=TaskQueue(name=queue_name),
                            task_queue_type=queue_type,
                        )
                    )
                    stats = response.stats
                    logger.info(
                        "[SCHEDULER][QUEUE_STATS] queue=%s type=%s backlog=%s backlog_age=%s add_rate=%s dispatch_rate=%s",
                        queue_name,
                        queue_type_name,
                        stats.approximate_backlog_count,
                        stats.approximate_backlog_age,
                        stats.tasks_add_rate,
                        stats.tasks_dispatch_rate,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[SCHEDULER][QUEUE_STATS] Failed to describe queue=%s type=%s: %s",
                        queue_name,
                        queue_type_name,
                        exc,
                    )
        await asyncio.sleep(interval_seconds)


async def run_worker(config: TemporalSchedulerConfig):
    """
    Connect to Temporal and start one or more ingestion workers.
    """
    logger.info("🔗 Connecting to Temporal at %s (namespace=%s)", config.host, config.namespace)
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
    )

    specs = _role_specs(config)
    if not specs:
        raise ValueError(f"No worker roles resolved for worker_role='{config.worker_role}'")

    logger.info(
        "[SCHEDULER] Connected to Temporal. role=%s workflow_queue=%s io_queue=%s cpu_queue=%s",
        config.worker_role,
        config.get_workflow_task_queue(),
        config.get_io_task_queue(),
        config.get_cpu_task_queue(),
    )

    workers: list[Worker] = []
    executors: list[concurrent.futures.Executor] = []

    for spec in specs:
        activity_executor = _create_activity_executor(config, spec.activities)
        if activity_executor is not None:
            executors.append(activity_executor)
        workflow_task_executor = _create_workflow_task_executor(config)
        if workflow_task_executor is not None:
            executors.append(workflow_task_executor)

        worker = Worker(
            client=client,
            task_queue=spec.task_queue,
            workflows=list(spec.workflows),
            activities=list(spec.activities),
            activity_executor=activity_executor,
            workflow_task_executor=workflow_task_executor,
            max_cached_workflows=config.max_cached_workflows,
            max_concurrent_workflow_tasks=config.max_concurrent_workflow_tasks,
            max_concurrent_activities=config.max_concurrent_activities,
            max_concurrent_workflow_task_polls=config.max_concurrent_workflow_task_polls,
            max_concurrent_activity_task_polls=config.max_concurrent_activity_task_polls,
            max_activities_per_second=config.max_activities_per_second,
            max_task_queue_activities_per_second=config.max_task_queue_activities_per_second,
            graceful_shutdown_timeout=timedelta(seconds=max(0, config.graceful_shutdown_timeout_seconds)),
        )
        workers.append(worker)
        logger.info(
            "[SCHEDULER] Worker role=%s queue=%s workflows=%d activities=%d max_concurrent_workflow_tasks=%s max_concurrent_activities=%s",
            spec.role,
            spec.task_queue,
            len(spec.workflows),
            len(spec.activities),
            config.max_concurrent_workflow_tasks,
            config.max_concurrent_activities,
        )

    logger.info("[SCHEDULER] Temporal worker(s) ready. count=%d", len(workers))
    queue_monitor_task: asyncio.Task[None] | None = None
    if config.queue_stats_log_interval_seconds > 0:
        queue_monitor_task = asyncio.create_task(
            _log_queue_stats_loop(
                client,
                namespace=config.namespace,
                task_queues=[spec.task_queue for spec in specs],
                interval_seconds=config.queue_stats_log_interval_seconds,
            )
        )
    try:
        await asyncio.gather(*(worker.run() for worker in workers))
    finally:
        if queue_monitor_task is not None:
            queue_monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await queue_monitor_task
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)
