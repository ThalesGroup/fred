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

from __future__ import annotations

import logging
import time
from typing import Any

from fred_core.kpi import Dims
from temporalio import activity

logger = logging.getLogger(__name__)

TEMPORAL_SYSTEM_ACTIVITY_QUEUE_WAIT_MS = "temporal.system.activity_queue_wait_ms"
TEMPORAL_SYSTEM_ACTIVITY_DURATION_MS = "temporal.system.activity_duration_ms"
TEMPORAL_INGESTION_DOCUMENTS_TOTAL = "temporal.ingestion.documents_total"
TEMPORAL_INGESTION_WORKFLOWS_TOTAL = "temporal.ingestion.workflows_total"


def emit_temporal_activity_queue_wait_kpi(
    *,
    phase: str,
) -> float | None:
    """
    Why:
    Measure how long Temporal keeps an activity task queued before a worker
    starts it, so ingestion launch delay is observable in Prometheus/KPI.

    How:
    Read Temporal activity `scheduled_time` and `started_time`, compute
    wait duration in milliseconds, then emit a KPI timer metric with stable
    low-cardinality dimensions.

    Example:
    emit_temporal_activity_queue_wait_kpi(phase="metadata")
    """
    if not activity.in_activity():
        return None

    info = activity.info()
    wait_ms = max(0.0, (info.started_time - info.scheduled_time).total_seconds() * 1000.0)

    try:
        from knowledge_flow_backend.application_context import ApplicationContext

        actor = build_temporal_activity_kpi_actor()
        kpi = ApplicationContext.get_instance().get_kpi_writer()
        kpi.emit(
            name=TEMPORAL_SYSTEM_ACTIVITY_QUEUE_WAIT_MS,
            type="timer",
            value=wait_ms,
            unit="ms",
            dims={
                "phase": phase,
                "activity_type": info.activity_type,
                "task_queue": info.task_queue,
                "workflow_type": info.workflow_type or "unknown",
                "attempt": str(info.attempt),
            },
            actor=actor,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[SCHEDULER][ACTIVITY][KPI] Failed to emit activity queue wait metric for phase=%s: %s",
            phase,
            exc,
        )
    return wait_ms


def build_temporal_activity_kpi_actor():
    """
    Why:
    Keep Temporal activity KPI emissions consistent for scheduler/runtime
    metrics that describe worker execution rather than end-user business usage.

    How:
    Return a system-scoped KPIActor so Temporal infrastructure metrics do not
    inherit end-user identity or user-level label cardinality.

    Example:
    actor = build_temporal_activity_kpi_actor()
    """
    from fred_core.kpi import KPIActor

    return KPIActor(type="system")


def _temporal_activity_file_type(*, metadata: Any | None, file: Any | None) -> str:
    """
    Why:
    Normalize file format dimensions so dashboards can aggregate push and pull
    ingestion events under the same low-cardinality label.

    How:
    Prefer extracted metadata file type, then fall back to filename suffix or
    "other" when the format is still unknown.
    """
    if metadata is not None:
        file_info = getattr(metadata, "file", None)
        file_type = getattr(file_info, "file_type", None)
        value = getattr(file_type, "value", file_type)
        if value:
            return str(value)

        document_name = getattr(metadata, "document_name", None)
        if isinstance(document_name, str) and "." in document_name:
            return document_name.rsplit(".", 1)[-1].lower()

    display_name = getattr(file, "display_name", None)
    if isinstance(display_name, str) and "." in display_name:
        return display_name.rsplit(".", 1)[-1].lower()

    external_path = getattr(file, "external_path", None)
    if isinstance(external_path, str) and "." in external_path:
        return external_path.rsplit(".", 1)[-1].lower()

    return "other"


def _temporal_activity_source_type(*, metadata: Any | None, file: Any | None) -> str:
    """
    Why:
    Distinguish push and pull ingestion flows in metrics without relying on
    high-cardinality identifiers.

    How:
    Prefer normalized metadata source_type, then infer from FileToProcess shape.
    """
    if metadata is not None:
        source_type = getattr(metadata, "source_type", None)
        value = getattr(source_type, "value", source_type)
        if value:
            return str(value)

    if file is not None:
        external_path = getattr(file, "external_path", None)
        return "pull" if external_path else "push"

    return "unknown"


def _temporal_activity_source_tag(*, metadata: Any | None, file: Any | None) -> str:
    """
    Why:
    Surface the ingestion connector/source in Temporal KPIs while keeping
    dimensions stable enough for Prometheus dashboards.

    How:
    Prefer metadata.source_tag and fall back to the submitted file source_tag.
    """
    source_tag = getattr(metadata, "source_tag", None)
    if source_tag:
        return str(source_tag)

    source_tag = getattr(file, "source_tag", None)
    if source_tag:
        return str(source_tag)

    return "unknown"


def _temporal_exception_code(exc: BaseException | None) -> str:
    """
    Why:
    Normalize failure labels so dashboards group similar ingestion errors
    together instead of exploding cardinality on raw messages.

    How:
    Use the exception class name as a short machine-friendly error code.
    """
    if exc is None:
        return "none"
    return type(exc).__name__


def emit_temporal_activity_result_kpis(
    *,
    phase: str,
    started_at_monotonic: float,
    metadata: Any | None = None,
    file: Any | None = None,
    status: str,
    exc: BaseException | None = None,
) -> float | None:
    """
    Why:
    Centralize Temporal ingestion result metrics so every activity emits the
    same success/failure, duration and routing signals.

    How:
    Emit one duration histogram plus one success/failure counter using only
    information already available in the Temporal activity context and document
    metadata.

    Example:
    emit_temporal_activity_result_kpis(
        phase="input",
        started_at_monotonic=start,
        metadata=metadata,
        file=file,
        status="success",
    )
    """
    if not activity.in_activity():
        return None

    info = activity.info()
    duration_ms = max(0.0, (time.perf_counter() - started_at_monotonic) * 1000.0)
    error_code = _temporal_exception_code(exc)
    dims: Dims = {
        "phase": phase,
        "status": status,
        "error_code": error_code,
        "activity_type": info.activity_type,
        "task_queue": info.task_queue,
        "workflow_type": info.workflow_type or "unknown",
        "attempt": str(info.attempt),
        "file_type": _temporal_activity_file_type(metadata=metadata, file=file),
        "source_type": _temporal_activity_source_type(metadata=metadata, file=file),
        "source_tag": _temporal_activity_source_tag(metadata=metadata, file=file),
    }

    try:
        from knowledge_flow_backend.application_context import ApplicationContext

        actor = build_temporal_activity_kpi_actor()
        kpi = ApplicationContext.get_instance().get_kpi_writer()
        kpi.emit(
            name=TEMPORAL_SYSTEM_ACTIVITY_DURATION_MS,
            type="timer",
            value=duration_ms,
            unit="ms",
            dims=dims,
            actor=actor,
        )
        kpi.count(
            TEMPORAL_INGESTION_DOCUMENTS_TOTAL,
            1,
            dims=dims,
            actor=actor,
        )
    except Exception as metric_exc:  # noqa: BLE001
        logger.warning(
            "[SCHEDULER][ACTIVITY][KPI] Failed to emit result metrics for phase=%s status=%s: %s",
            phase,
            status,
            metric_exc,
        )
    return duration_ms


def emit_temporal_workflow_status_kpi(
    *,
    status: str,
    workflow_id: str,
    document_uid: str | None = None,
    filename: str | None = None,
    error: str | None = None,
) -> None:
    """
    Why:
    Parent ingestion workflows need their own success/failure signal so teams
    can distinguish document-level failures from whole-pipeline outcomes.

    How:
    Emit one counter per final workflow status using the persisted workflow id
    context already available in `record_workflow_status`.

    Example:
    emit_temporal_workflow_status_kpi(
        status="COMPLETED",
        workflow_id="pipeline-123",
    )
    """
    if not activity.in_activity():
        return

    try:
        from knowledge_flow_backend.application_context import ApplicationContext

        actor = build_temporal_activity_kpi_actor()
        kpi = ApplicationContext.get_instance().get_kpi_writer()
        workflow_dims: Dims = {
            "status": status.lower(),
            "task_queue": activity.info().task_queue,
            "workflow_type": activity.info().workflow_type or "unknown",
            "has_error": "true" if error else "false",
            "has_document_uid": "true" if bool(document_uid) else "false",
            "has_filename": "true" if bool(filename) else "false",
            "workflow_id_prefix": workflow_id.split("-", 1)[0] if workflow_id else "unknown",
        }
        kpi.count(
            TEMPORAL_INGESTION_WORKFLOWS_TOTAL,
            1,
            dims=workflow_dims,
            actor=actor,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[SCHEDULER][ACTIVITY][KPI] Failed to emit workflow status metric for workflow_id=%s: %s",
            workflow_id,
            exc,
        )
