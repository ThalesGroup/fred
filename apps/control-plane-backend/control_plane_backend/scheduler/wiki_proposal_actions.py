from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
from control_plane_backend.scheduler.temporal.structures import (
    WikiProposalActionResult,
    WikiProposalCandidate,
    WikiProposalCandidateBatch,
)

logger = logging.getLogger(__name__)


async def list_due_wiki_proposal_candidates(
    *,
    limit: int,
    deps: LifecycleActionDependencies,
) -> WikiProposalCandidateBatch:
    """List `status="proposed"` rows old enough to expire.

    "Due" here is computed, not queued: unlike conversation purge there is no
    separate schedule row to enqueue — a proposal's own `created_at` plus the
    configured retention IS the due date (CONTROL-PLANE-PRODUCT-CONTRACT.md
    §49). No decline signal exists to schedule against (see the store's own
    module docstring): this is the only fact available to sweep on.
    """

    store = deps.get_team_wiki_store()
    retention = deps.get_policy_catalog().wiki_policies.proposal.retention_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention)

    candidates = await store.list_stale_proposals(older_than=cutoff, limit=limit)
    return WikiProposalCandidateBatch(
        candidates=[
            WikiProposalCandidate(
                revision_id=c.revision_id,
                team_id=str(c.team_id),
                page_id=c.page_id,
                created_at=c.created_at,
            )
            for c in candidates
        ]
    )


async def reject_stale_wiki_proposal(
    *,
    candidate: WikiProposalCandidate,
    deps: LifecycleActionDependencies,
) -> WikiProposalActionResult:
    """Reject one stale proposal — idempotent and race-safe by construction.

    `TeamWikiStore.reject_stale_proposal` is a single conditional `UPDATE
    ... WHERE status = 'proposed'`: if a human approved this exact proposal
    between the list step above and this call, it matches nothing and
    returns `False` rather than corrupting a page that now points at a
    published revision. Either outcome is reported `ok=True` here — a
    proposal that resolved itself in the meantime is not a failure of this
    sweep, only nothing left to do.
    """

    # Lazy: `fred_core.common` pulls in httpx/anyio, sandbox-forbidden at
    # workflow-module load time (same reason as `lifecycle_actions.py`).
    from fred_core.common import TeamId

    store = deps.get_team_wiki_store()
    changed = await store.reject_stale_proposal(
        team_id=TeamId(candidate.team_id), revision_id=candidate.revision_id
    )
    logger.info(
        "[LIFECYCLE][WIKI] reject revision_id=%s team_id=%s changed=%s",
        candidate.revision_id,
        candidate.team_id,
        changed,
    )
    return WikiProposalActionResult(
        revision_id=candidate.revision_id,
        action="rejected" if changed else "already_resolved",
        ok=True,
        changed=changed,
    )
