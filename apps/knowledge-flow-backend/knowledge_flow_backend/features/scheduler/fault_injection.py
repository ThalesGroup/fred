"""Opt-in, file-scoped faults for manual ingestion tests with real Temporal workers."""

from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass

from temporalio import activity
from temporalio.exceptions import ApplicationError

from knowledge_flow_backend.features.scheduler.activity_utils import await_with_heartbeat

_PREFIX = "FRED_INGESTION_FAULT"
_ACTIVITIES = {"extraction": {"push_input_process", "pull_input_process"}, "indexing": {"output_process"}}


@dataclass(frozen=True)
class IngestionFault:
    mode: str
    stage: str
    filename: str
    delay_seconds: float
    attempts: frozenset[int] | None


def read_ingestion_fault() -> IngestionFault | None:
    mode = os.environ.get(_PREFIX, "").strip()
    if not mode:
        return None
    if mode not in {"activity_error", "non_retryable_error", "worker_crash", "delay"}:
        raise ValueError(f"{_PREFIX}: expected activity_error, non_retryable_error, worker_crash or delay")
    stage = os.environ.get(f"{_PREFIX}_STAGE", "").strip()
    if stage not in _ACTIVITIES:
        raise ValueError(f"{_PREFIX}_STAGE: expected extraction or indexing")
    filename = os.environ.get(f"{_PREFIX}_FILE", "").strip()
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError(f"{_PREFIX}_FILE: an exact document filename is required, without a directory")
    try:
        delay = float(os.environ.get(f"{_PREFIX}_DELAY_SECONDS", "0"))
    except ValueError as exc:
        raise ValueError(f"{_PREFIX}_DELAY_SECONDS: expected a number of seconds") from exc
    if not math.isfinite(delay) or delay < 0:
        raise ValueError(f"{_PREFIX}_DELAY_SECONDS: expected a finite, non-negative number")
    selected = os.environ.get(f"{_PREFIX}_ATTEMPTS", "1").strip()
    try:
        attempts = None if selected == "all" else frozenset(int(token.strip()) for token in selected.split(","))
    except ValueError as exc:
        raise ValueError(f"{_PREFIX}_ATTEMPTS: expected positive attempt numbers (e.g. 1,2), or all") from exc
    if attempts is not None and any(attempt < 1 for attempt in attempts):
        raise ValueError(f"{_PREFIX}_ATTEMPTS: expected positive attempt numbers (e.g. 1,2), or all")
    return IngestionFault(mode, stage, filename, delay, attempts)


async def inject_ingestion_fault(*, stage: str, document_name: str, document_uid: str) -> None:
    # Direct/in-memory calls must never delay or kill the API process.
    if not activity.in_activity():
        return
    fault = read_ingestion_fault()
    if fault is None or fault.stage != stage or fault.filename != document_name:
        return
    info = activity.info()
    if info.activity_type not in _ACTIVITIES[stage]:
        return  # In particular, exclude trusted maintenance/revectorization activities.
    if fault.attempts is not None and info.attempt not in fault.attempts:
        return
    activity.logger.warning(
        "[SIMULATED INGESTION FAULT] armed mode=%s stage=%s document=%s attempt=%s delay_s=%s",
        fault.mode,
        stage,
        document_uid,
        info.attempt,
        fault.delay_seconds,
    )
    await await_with_heartbeat(
        asyncio.sleep(fault.delay_seconds),
        heartbeat_details={"stage": stage, "document_uid": document_uid, "simulated_fault": fault.mode},
    )
    message = f"Simulated ingestion fault: {fault.mode} at {stage}, attempt {info.attempt}, document {document_uid}."
    activity.logger.warning("[SIMULATED INGESTION FAULT] triggering: %s", message)
    if fault.mode == "worker_crash":
        os._exit(86)  # Deliberate abrupt worker exit: no finally blocks or graceful shutdown.
    if fault.mode != "delay":
        raise ApplicationError(message, type="SimulatedIngestionFailure", non_retryable=fault.mode == "non_retryable_error")
