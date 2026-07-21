from __future__ import annotations

import logging

from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    LifecycleTrigger,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
)

logger = logging.getLogger(__name__)


async def list_due_conversation_candidates(
    *,
    limit: int,
    deps: LifecycleActionDependencies,
) -> ConversationCandidateBatch:
    """
    List due conversation purge candidates from the queue store.

    Why this function exists:
    - lifecycle workflows need one typed batch of conversation candidates built
      from queued purge entries

    How to use it:
    - pass the maximum number of items to load
    - optionally pass explicit lifecycle-action dependencies for offline tests
      or in-memory execution

    Example:
    - `batch = await list_due_conversation_candidates(limit=100, deps=deps)`
    """
    queue_store = deps.get_purge_queue_store()
    due_items = await queue_store.list_due(limit=limit)
    candidates = [
        ConversationLifecycleEvent(
            conversation_id=item.session_id,
            team_id=item.team_id,
            # CTRLP-12 E1: thread the queue row's real owner so the erase runs
            # against it (previously dropped). The trigger/reason is deliberately
            # not carried — erase_session does not depend on it.
            user_id=item.user_id,
            trigger=LifecycleTrigger.MEMBER_REMOVED,
            created_at=item.created_at,
            last_activity_at=item.created_at,
        )
        for item in due_items
    ]
    return ConversationCandidateBatch(candidates=candidates)


async def delete_conversation_and_mark_done(
    *,
    event: ConversationLifecycleEvent,
    deps: LifecycleActionDependencies,
) -> ConversationActionResult:
    """
    Erase one conversation across every store at window expiry, then complete the
    queue entry — but **only** once the erasure receipt is fully ok.

    CTRLP-12 E1 (RFC §3.C): the deferred delete window has expired, so this runs
    the full `ConversationErasureService.erase_session` (not a single-store
    metadata delete) as the platform service principal — a minted service bearer
    (C2) plus the `can_manage_platform` admin branch on the runtime/KF delete
    endpoints (C1) — threading the queue row's real `user_id`/`team_id`/
    `session_id`. The queue entry is marked done **only** on `receipt.ok`; a
    partial receipt (or a failure to mint the bearer) leaves it queued so the
    next tick retries. The `trigger`/reason is not carried — erase is erase.
    """
    # Lazy imports: keep the erasure/task modules out of the Temporal workflow
    # sandbox import graph (this module is reachable from the workflow).
    from control_plane_backend.sessions.erasure_tasks import (
        find_active_erasure_task_id,
        mark_erasure_running,
        record_erasure_result,
    )

    queue_store = deps.get_purge_queue_store()
    session_id = event.conversation_id

    # The purge-queue row always carries team_id + user_id; a missing one means a
    # malformed/legacy event we cannot safely erase — leave it queued, don't guess.
    if event.team_id is None or event.user_id is None:
        logger.error(
            "lifecycle erase skipped: session %s missing team_id/user_id", session_id
        )
        return ConversationActionResult(
            conversation_id=session_id, action="erase_skipped", ok=False
        )

    # Flip the scheduled erasure task to running so admins see it in-flight. Any
    # task bookkeeping is best-effort and never blocks the erase.
    task_service = deps.get_task_service()
    task_id = await find_active_erasure_task_id(
        task_service, session_id=session_id, team_id=event.team_id
    )
    if task_id is not None:
        await mark_erasure_running(task_service, task_id=task_id)

    try:
        authorization = await deps.get_service_bearer()
        # team_id is the queue row's str; TeamId is a NewType (runtime identity),
        # and erase_session treats it as a team id string. Not wrapping keeps the
        # heavy fred_core.common import out of the Temporal workflow sandbox graph.
        receipt = await deps.erase_session(
            team_id=event.team_id,
            session_id=session_id,
            user_id=event.user_id,
            authorization=authorization,
        )
    except Exception as exc:
        # Bearer mint / transport failure is retryable: leave the entry un-done.
        logger.warning(
            "lifecycle erase failed for session %s (retryable): %s", session_id, exc
        )
        return ConversationActionResult(
            conversation_id=session_id, action="erase_failed", ok=False
        )

    # Reflect the outcome on the task: succeeded when ok, else stays running with
    # partial progress (so the retry re-finds it). Never marks the task failed.
    if task_id is not None:
        await record_erasure_result(task_service, task_id=task_id, receipt=receipt)

    if not receipt.ok:
        logger.warning(
            "lifecycle erase incomplete for session %s; leaving queued for retry. stores=%r",
            session_id,
            [(s.store, s.ok, s.error) for s in receipt.stores],
        )
        return ConversationActionResult(
            conversation_id=session_id, action="erase_incomplete", ok=False
        )

    await queue_store.mark_done(session_id=session_id)
    return ConversationActionResult(
        conversation_id=session_id,
        action="erased",
        ok=True,
    )
