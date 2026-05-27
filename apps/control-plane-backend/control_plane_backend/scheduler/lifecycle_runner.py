from __future__ import annotations

from typing import Awaitable, Callable, Protocol

from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
    DeleteConversationInput,
    LifecycleManagerInput,
    LifecycleManagerResult,
    ListConversationCandidatesInput,
)


class _Logger(Protocol):
    def info(self, msg: str, *args: object) -> None: ...


ListConversationCandidatesExecutor = Callable[
    [ListConversationCandidatesInput],
    Awaitable[ConversationCandidateBatch],
]
DeleteConversationExecutor = Callable[
    [DeleteConversationInput],
    Awaitable[ConversationActionResult],
]


async def run_lifecycle_manager_once(
    *,
    input_data: LifecycleManagerInput,
    list_candidates: ListConversationCandidatesExecutor,
    delete_conversation: DeleteConversationExecutor,
    logger: _Logger,
    log_prefix: str,
) -> LifecycleManagerResult:
    """
    Shared lifecycle manager loop used by both scheduler backends.

    Temporal and memory backends must execute the same decision flow so
    in-memory tests validate the same behavior as Temporal workflow runs.
    """
    scanned = 0
    deleted = 0
    dry_run_actions = 0

    batch = await list_candidates(
        ListConversationCandidatesInput(limit=input_data.batch_size)
    )
    if not batch.candidates:
        logger.info("%s no due candidates", log_prefix)
        return LifecycleManagerResult()

    logger.info(
        "%s processing due candidates size=%s",
        log_prefix,
        len(batch.candidates),
    )

    for event in batch.candidates:
        scanned += 1
        if input_data.dry_run:
            dry_run_actions += 1
            logger.info(
                "%s[DRY_RUN] conversation_id=%s",
                log_prefix,
                event.conversation_id,
            )
            continue

        deletion = await delete_conversation(DeleteConversationInput(event=event))
        if deletion.ok:
            deleted += 1

    logger.info(
        "%s completed scanned=%s deleted=%s dry_run_actions=%s",
        log_prefix,
        scanned,
        deleted,
        dry_run_actions,
    )

    return LifecycleManagerResult(
        scanned=scanned,
        deleted=deleted,
        dry_run_actions=dry_run_actions,
    )
