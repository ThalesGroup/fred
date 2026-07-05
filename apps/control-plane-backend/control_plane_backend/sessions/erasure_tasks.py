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

"""Emit conversation erasure as observable tasks (CTRLP-12).

A deferred delete is scheduled now and erased later. Platform and team admins
must be able to see that whole pipeline — what is **scheduled** (with its due
date), what is running, and what finished — through the standard task surface
(`GET /tasks`, already scoped platform vs team). This module is the thin bridge
between the erasure flow and the fred-core task model:

- `schedule_erasure_task` — called when a deferred delete is enqueued: creates a
  future-dated `erasure` task so it shows up in the schedule immediately.
- `mark_erasure_running` / `record_erasure_result` — called by the lifecycle
  worker as it erases, so the same task moves running → succeeded (a partial
  receipt stays running for the retry, never `failed`).

All failures here are best-effort: task bookkeeping must never block or fail an
actual erasure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fred_core.tasks import (
    ErasureDetail,
    ErasureReason,
    ErasureTaskEvent,
    StartErasureRequest,
    TaskService,
    TaskState,
    TaskTarget,
)

if TYPE_CHECKING:
    # Type-only: importing erasure_service at runtime would close the cycle
    # product.service → erasure_tasks → erasure_service → product.service.
    # `receipt: ErasureReceipt` is a string annotation (from __future__), so the
    # class is never needed at runtime here.
    from control_plane_backend.sessions.erasure_service import ErasureReceipt

logger = logging.getLogger(__name__)

ERASURE_TASK_KIND = "erasure"
_CONVERSATION = "conversation"

# After this many failed erase attempts, a still-running erasure task is flagged
# ``stalled`` (via its ``step``) so an admin notices a wedged fan-out. It keeps
# retrying — erasure never auto-fails (RGPD) — the flag is an attention signal, not
# a terminal state. Frontend matches ``ERASURE_STEP_STALLED`` to surface it.
ERASURE_STALL_AFTER_ATTEMPTS = 5
ERASURE_STEP_STALLED = "stalled"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def schedule_erasure_task(
    task_service: TaskService,
    *,
    session_id: str,
    team_id: str,
    user_id: str,
    title: str | None,
    due_at: datetime,
    reason: ErasureReason,
) -> str | None:
    """Create a future-dated erasure task so the deferred delete is visible in the
    schedule the instant it is enqueued. Returns the task_id, or None on failure
    (never raises — scheduling the erasure must not depend on task bookkeeping)."""
    try:
        started = await task_service.start(
            StartErasureRequest(reason=reason),
            created_by=user_id,
            team_id=team_id,
            target=TaskTarget(
                type=_CONVERSATION, id=session_id, label=title or session_id
            ),
            scheduled_for=due_at,
        )
        await task_service.record(
            ErasureTaskEvent(
                task_id=started.task_id,
                state=TaskState.pending,
                seq=0,
                timestamp=_utcnow(),
                step="scheduled",
                detail=ErasureDetail(reason=reason),
                target=TaskTarget(
                    type=_CONVERSATION, id=session_id, label=title or session_id
                ),
                owner=user_id,
            )
        )
        return started.task_id
    except Exception:
        logger.exception(
            "[CTRLP-12] failed to create erasure task for session %s", session_id
        )
        return None


async def find_active_erasure_task_id(
    task_service: TaskService, *, session_id: str, team_id: str
) -> str | None:
    """The non-terminal erasure task for this conversation, if any (matched by the
    task's target)."""
    listing = await task_service.list_tasks(
        kind=ERASURE_TASK_KIND, team_id=team_id, exclude_terminal=True
    )
    for task in listing.tasks:
        if task.target is not None and task.target.id == session_id:
            return task.task_id
    return None


async def mark_erasure_running(task_service: TaskService, *, task_id: str) -> None:
    """Flip a scheduled erasure task to running as the worker begins (best-effort)."""
    try:
        await task_service.record(
            ErasureTaskEvent(
                task_id=task_id,
                state=TaskState.running,
                seq=0,
                timestamp=_utcnow(),
                step="erasing",
            )
        )
    except Exception:
        logger.exception("[CTRLP-12] failed to mark erasure task %s running", task_id)


async def _prior_attempts(task_service: TaskService, task_id: str) -> int:
    """How many erase attempts the task's durable detail has already recorded.

    Read back from the run summary (the store preserves ``detail`` across the
    sparse ``mark_erasure_running`` event), so the counter survives ticks. Best
    effort: any read/shape problem just restarts the count at 0."""
    try:
        run = await task_service.get_run(task_id)
        if run is not None and isinstance(run.detail, dict):
            return int(run.detail.get("attempts", 0) or 0)
    except Exception:
        logger.debug("[CTRLP-12] could not read prior attempts for %s", task_id)
    return 0


async def record_erasure_result(
    task_service: TaskService, *, task_id: str, receipt: ErasureReceipt
) -> None:
    """Record the outcome of an erase attempt on the task (best-effort).

    A fully-ok receipt closes the task **succeeded**. A partial receipt is
    deliberately recorded as **running** (with the per-store progress), NOT
    failed — the queue entry is retried at the next tick, so the task must stay
    non-terminal for that retry to re-find and eventually complete it. Erasure
    tasks therefore never end in `failed`; they stay visibly in-progress until the
    conversation is fully erased.

    To avoid a wedged fan-out retrying *invisibly* forever, we count attempts and,
    past ``ERASURE_STALL_AFTER_ATTEMPTS``, set the step to ``stalled`` so an admin
    sees it needs intervention. Still running, still retrying — just no longer
    silent (CTRLP-12).
    """
    try:
        stores_total = len(receipt.stores)
        stores_ok = sum(1 for store in receipt.stores if store.ok)
        progress = (stores_ok / stores_total) if stores_total else None
        if receipt.ok:
            attempts = await _prior_attempts(task_service, task_id)
            state, step = TaskState.succeeded, "erased"
        else:
            attempts = await _prior_attempts(task_service, task_id) + 1
            state = TaskState.running
            step = (
                ERASURE_STEP_STALLED
                if attempts >= ERASURE_STALL_AFTER_ATTEMPTS
                else "partial — retrying"
            )
            if step == ERASURE_STEP_STALLED:
                logger.error(
                    "[CTRLP-12] erasure task %s stalled after %d attempts "
                    "(%d/%d stores) — needs intervention",
                    task_id,
                    attempts,
                    stores_ok,
                    stores_total,
                )
        await task_service.record(
            ErasureTaskEvent(
                task_id=task_id,
                state=state,
                seq=0,
                timestamp=_utcnow(),
                progress=progress,
                step=step,
                detail=ErasureDetail(
                    stores_ok=stores_ok,
                    stores_total=stores_total,
                    attempts=attempts,
                ),
            )
        )
    except Exception:
        logger.exception("[CTRLP-12] failed to record erasure result on %s", task_id)
