from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
)


class LifecycleManagerInput(BaseModel):
    dry_run: bool = False
    batch_size: int = Field(default=100, ge=1, le=5000)


class WikiProposalLifecycleResult(BaseModel):
    """The wiki-proposal half of one lifecycle tick — kept as its own nested
    result rather than flat fields on `LifecycleManagerResult`, so a future
    third sweep does not have to keep inventing prefixed field names."""

    scanned: int = 0
    rejected: int = 0
    dry_run_actions: int = 0


class LifecycleManagerResult(BaseModel):
    scanned: int = 0
    deleted: int = 0
    dry_run_actions: int = 0
    wiki_proposals: WikiProposalLifecycleResult = Field(
        default_factory=WikiProposalLifecycleResult
    )


class ListConversationCandidatesInput(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)


class ConversationCandidateBatch(BaseModel):
    candidates: list[ConversationLifecycleEvent] = Field(default_factory=list)


class DeleteConversationInput(BaseModel):
    event: ConversationLifecycleEvent


class ConversationActionResult(BaseModel):
    conversation_id: str
    action: str
    ok: bool = True


class WikiProposalCandidate(BaseModel):
    """One `status="proposed"` row old enough for the sweep to act on —
    the Temporal-serializable twin of `store.StaleProposalCandidate`."""

    revision_id: str
    team_id: str
    page_id: str
    created_at: datetime


class ListWikiProposalCandidatesInput(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)


class WikiProposalCandidateBatch(BaseModel):
    candidates: list[WikiProposalCandidate] = Field(default_factory=list)


class RejectWikiProposalInput(BaseModel):
    candidate: WikiProposalCandidate


class WikiProposalActionResult(BaseModel):
    revision_id: str
    action: str
    ok: bool = True
    # False when the conditional UPDATE matched no row — the proposal was
    # already resolved (published or already rejected) by the time this ran.
    # Distinct from `ok`: that is never false here (there is no failure path
    # besides an exception), this is what the tick's `rejected` count means.
    changed: bool = True
