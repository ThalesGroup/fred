"""Offline unit tests for the wiki proposal lifecycle actions (WIKI-05).

Ref: CONTROL-PLANE-PRODUCT-CONTRACT.md §49 — a proposal a human never acts on
resolves the same way a decline would have: `status` flips to `rejected`
via the scheduler's existing lifecycle infrastructure, never a wiki-specific
loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.scheduler.temporal.structures import (
    RejectWikiProposalInput,
    WikiProposalCandidate,
)
from control_plane_backend.scheduler.wiki_proposal_actions import (
    list_due_wiki_proposal_candidates,
    reject_stale_wiki_proposal,
)
from control_plane_backend.team_wiki.store import StaleProposalCandidate
from fred_core.common import TeamId


class _FakeWikiStore:
    def __init__(self) -> None:
        self.listed: list[tuple[datetime, int]] = []
        self.rejected: list[tuple[str, str]] = []
        self.reject_returns = True

    async def list_stale_proposals(
        self, *, older_than: datetime, limit: int
    ) -> list[StaleProposalCandidate]:
        self.listed.append((older_than, limit))
        return [
            StaleProposalCandidate(
                revision_id="rev-1",
                team_id=TeamId("team-a"),
                page_id="page-1",
                created_at=older_than - timedelta(days=1),
            )
        ]

    async def reject_stale_proposal(self, *, team_id: TeamId, revision_id: str) -> bool:
        self.rejected.append((str(team_id), revision_id))
        return self.reject_returns


def _deps(
    store: _FakeWikiStore, *, retention: str = "P30D"
) -> LifecycleActionDependencies:
    catalog = ConversationPolicyCatalog.model_validate(
        {"wiki_policies": {"proposal": {"retention": retention}}}
    )
    return LifecycleActionDependencies(
        get_session_store=cast(Any, None),
        get_purge_queue_store=cast(Any, None),
        erase_session=cast(Any, None),
        get_service_bearer=cast(Any, None),
        get_task_service=cast(Any, None),
        get_team_wiki_store=cast(Any, lambda: store),
        get_policy_catalog=cast(Any, lambda: catalog),
    )


@pytest.mark.asyncio
async def test_list_due_candidates_uses_the_configured_retention() -> None:
    store = _FakeWikiStore()
    before = datetime.now(timezone.utc)

    batch = await list_due_wiki_proposal_candidates(
        limit=10, deps=_deps(store, retention="P7D")
    )

    assert len(store.listed) == 1
    cutoff, limit = store.listed[0]
    assert limit == 10
    # ~7 days before "now" — a tight window rather than an exact instant,
    # since two `datetime.now()` calls a moment apart are never equal.
    expected = before - timedelta(days=7)
    assert abs((cutoff - expected).total_seconds()) < 5

    assert len(batch.candidates) == 1
    assert batch.candidates[0].revision_id == "rev-1"
    assert batch.candidates[0].team_id == "team-a"


@pytest.mark.asyncio
async def test_reject_stale_proposal_reports_changed_when_row_flips() -> None:
    store = _FakeWikiStore()
    store.reject_returns = True
    candidate = WikiProposalCandidate(
        revision_id="rev-1",
        team_id="team-a",
        page_id="page-1",
        created_at=datetime.now(timezone.utc),
    )

    result = await reject_stale_wiki_proposal(candidate=candidate, deps=_deps(store))

    assert result.ok is True
    assert result.changed is True
    assert result.action == "rejected"
    assert store.rejected == [("team-a", "rev-1")]


@pytest.mark.asyncio
async def test_reject_stale_proposal_is_a_harmless_no_op_once_already_resolved() -> (
    None
):
    """The race this whole design exists to make safe: the store's own
    conditional UPDATE already found nothing to change (a human approved it
    first) — this must be reported as a benign no-op, never a failure."""

    store = _FakeWikiStore()
    store.reject_returns = False
    candidate = WikiProposalCandidate(
        revision_id="rev-1",
        team_id="team-a",
        page_id="page-1",
        created_at=datetime.now(timezone.utc),
    )

    result = await reject_stale_wiki_proposal(candidate=candidate, deps=_deps(store))

    assert result.ok is True
    assert result.changed is False
    assert result.action == "already_resolved"


@pytest.mark.asyncio
async def test_reject_wiki_proposal_activity_requires_deps() -> None:
    from control_plane_backend.scheduler.temporal.activities import (
        reject_wiki_proposal,
    )

    with pytest.raises(RuntimeError):
        await reject_wiki_proposal(
            RejectWikiProposalInput(
                candidate=WikiProposalCandidate(
                    revision_id="rev-1",
                    team_id="team-a",
                    page_id="page-1",
                    created_at=datetime.now(timezone.utc),
                )
            )
        )
