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
The execution plumbing an author never sees: the activity side.

All I/O lives here, in the activity, so an author never writes workflow code and
cannot break replay determinism. The workflow itself sits in `_workflow.py`
because Temporal re-imports a workflow's module inside its sandbox — this one is
free to import whatever it needs, that one is not. Nothing here is exported from
the package's public surface.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.runtime import (
    LogForwardingConfig,
    LoggingConfig,
    PrometheusConfig,
    Runtime,
    TelemetryConfig,
)
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from fred_sdk.knowledge_base import telemetry
from fred_sdk.knowledge_base._workflow import (
    SYNCHRONIZE_ACTIVITY,
    SynchronizeInput,
    SynchronizeWorkflow,
    WeaverSynchronizeWorkflow,
)
from fred_sdk.knowledge_base.client import ControlPlaneClient
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.documents import declare_library_synchronized
from fred_sdk.knowledge_base.knowledge_base import KnowledgeBase
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseReconciliation,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
)
from fred_sdk.knowledge_base.routing import task_queue_for

logger = logging.getLogger(__name__)


def build_workflow_runner() -> SandboxedWorkflowRunner:
    """The sandbox configuration `serve()` runs under, shared with its test.

    `fred_sdk` is passed through because importing it is not sandbox-safe at
    any depth: the package initializer reaches `sniffio`, which subclasses a
    proxied `threading.local`, and calls `datetime.date.today()`. Re-importing
    it per run would fail before a Knowledge Base ever received work.

    What this costs is determinism checking on `_workflow.py` itself, which is
    why that module stays small enough to audit by eye — an author writes the
    handler, never workflow code, so nothing an author writes relies on it.
    """
    return SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules("fred_sdk")
    )


def build_runtime(
    knowledge_base: KnowledgeBase, configuration: PodConfiguration
) -> Runtime:
    """Forward engine logs as the pod, with optional engine metrics.

    Logging stays configured even without an exporter. Engine series carry
    the same pod and definition labels as the SDK's own endpoint.
    """
    exporter = configuration.observability.temporal.prometheus
    runtime = Runtime(
        telemetry=TelemetryConfig(
            logging=LoggingConfig(
                filter=LoggingConfig.default.filter,
                forwarding=LogForwardingConfig(
                    logger=logger, prepend_target_on_message=False
                ),
            ),
            metrics=(
                PrometheusConfig(
                    bind_address=f"{exporter.address}:{exporter.port}",
                    counters_total_suffix=True,
                    unit_suffix=True,
                    durations_as_seconds=True,
                )
                if exporter.enabled
                else None
            ),
            global_tags={
                "service": configuration.runtime_id,
                "knowledge_base": knowledge_base.id,
            },
        )
    )
    if exporter.enabled:
        logger.info(
            "Workflow engine metrics served at %s:%s", exporter.address, exporter.port
        )
    return runtime


def _build_activity(
    knowledge_base: KnowledgeBase,
    control_plane: ControlPlaneClient,
    configuration: PodConfiguration,
):
    handler = knowledge_base.resolve_handler()

    @activity.defn(name=SYNCHRONIZE_ACTIVITY)
    async def synchronize(payload: SynchronizeInput, run_id: str) -> str:
        with telemetry.observing_run() as run:
            context = await control_plane.fetch_run_context(
                payload.definition_id,
                payload.instance_id,
                run_id,
            )
            # Before the handler, not after: a run that fails halfway still
            # filled part of the library, and people should not have been able
            # to edit it in the meantime. Idempotent, so every later run changes
            # nothing.
            run.stage = "declare"
            await declare_library_synchronized(
                configuration,
                library_id=context.library_id,
                instance_id=context.instance_id,
            )
            run.stage = "handler"
            result = await handler(context)
            run.result = result
        # Nothing but the outcome travels back: Fred runs the engine, so a second
        # source for a run's state would disagree exactly when a pod is killed
        # mid-run. The workflow turns this outcome into a terminal state.
        return result.outcome.value

    return synchronize


def _build_weaver_activity(
    knowledge_base: KnowledgeBase, control_plane: ControlPlaneClient
):
    handler = knowledge_base.resolve_handler()

    @activity.defn(name="fred_weaver_knowledge_base_synchronize")
    async def synchronize(run_id: str) -> str:
        with telemetry.observing_run() as run:
            try:
                context = await control_plane.claim_run(run_id)
            except Exception:
                raise ApplicationError("Knowledge Base admission unavailable") from None
            if isinstance(context, KnowledgeBaseRunOutcome):
                return context.value
            try:
                if context.definition_id != knowledge_base.id:
                    raise ValueError("Unexpected Knowledge Base definition")
                run.stage = "handler"
                result = await handler(context)
            except asyncio.CancelledError:
                raise
            except Exception:
                # SDK/source exceptions can embed credentials; never serialize
                # them in Temporal history or the Control Plane result.
                result = KnowledgeBaseSyncResult(
                    outcome=KnowledgeBaseRunOutcome.failed,
                    reconciliation=KnowledgeBaseReconciliation.partial,
                )
            run.result = result
            run.stage = "complete"
            try:
                await control_plane.complete_run(run_id, result)
            except Exception:
                raise ApplicationError("Knowledge Base result unavailable") from None
            return result.outcome.value

    return synchronize


async def serve(knowledge_base: KnowledgeBase, configuration: PodConfiguration) -> None:
    """Poll this definition's queue until the process is stopped."""
    task_queue = task_queue_for(knowledge_base.id)
    telemetry.bind(knowledge_base, configuration.runtime_id)
    telemetry.start_exporter(configuration.observability.kpi.prometheus)
    client = await Client.connect(
        configuration.temporal_host,
        namespace=configuration.temporal_namespace,
        runtime=build_runtime(knowledge_base, configuration),
    )
    control_plane = ControlPlaneClient(configuration)
    logger.info("Knowledge Base %s serving runs on %s", knowledge_base.id, task_queue)
    try:
        if configuration.knowledge_base.protocol == "weaver":
            admission = await control_plane.worker_configuration(knowledge_base.id)
            task_queue = admission["task_queue"]
            workflows = [WeaverSynchronizeWorkflow]
            activities = [_build_weaver_activity(knowledge_base, control_plane)]
        else:
            workflows = [SynchronizeWorkflow]
            activities = [_build_activity(knowledge_base, control_plane, configuration)]
        async with Worker(
            client,
            task_queue=task_queue,
            workflows=workflows,
            activities=activities,
            workflow_runner=build_workflow_runner(),
        ):
            await asyncio.Event().wait()
    finally:
        await control_plane.aclose()
