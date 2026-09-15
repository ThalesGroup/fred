from __future__ import annotations

from datetime import datetime, timezone

import pytest
from control_plane_backend.scheduler.memory.lifecycle_runner import (
    run_lifecycle_manager_once_in_memory,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    LifecycleTrigger,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
    DeleteConversationInput,
    LifecycleManagerInput,
    ListConversationCandidatesInput,
    ListWikiProposalCandidatesInput,
    RejectWikiProposalInput,
    WikiProposalActionResult,
    WikiProposalCandidate,
    WikiProposalCandidateBatch,
)


def _patch_empty_wiki_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the conversation sweep only — give the wiki
    sweep an empty batch so it runs (proving the two are independent) without
    adding assertions unrelated to what each test is actually checking."""

    async def _no_candidates(
        _input_data: ListWikiProposalCandidatesInput,
    ) -> WikiProposalCandidateBatch:
        return WikiProposalCandidateBatch(candidates=[])

    async def _unreachable(
        _input_data: RejectWikiProposalInput,
    ) -> WikiProposalActionResult:  # pragma: no cover — no candidate to reject
        raise AssertionError("no wiki candidate was listed")

    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.list_wiki_proposal_candidates",
        _no_candidates,
    )
    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.reject_wiki_proposal",
        _unreachable,
    )


@pytest.mark.asyncio
async def test_in_memory_runner_uses_temporal_activity_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = ConversationLifecycleEvent(
        conversation_id="s-1",
        team_id="team-a",
        trigger=LifecycleTrigger.MEMBER_REMOVED,
        created_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
    )
    list_calls: list[int] = []
    delete_calls: list[int] = []

    async def _fake_list_candidates(
        input_data: ListConversationCandidatesInput,
    ) -> ConversationCandidateBatch:
        list_calls.append(1)
        assert input_data.limit == 42
        return ConversationCandidateBatch(candidates=[event])

    async def _fake_delete_conversation(
        input_data: DeleteConversationInput,
    ) -> ConversationActionResult:
        delete_calls.append(1)
        assert input_data.event == event
        return ConversationActionResult(
            conversation_id=input_data.event.conversation_id,
            action="deleted",
            ok=True,
        )

    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.list_conversation_candidates",
        _fake_list_candidates,
    )
    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.delete_conversation",
        _fake_delete_conversation,
    )
    _patch_empty_wiki_sweep(monkeypatch)

    result = await run_lifecycle_manager_once_in_memory(
        LifecycleManagerInput(dry_run=False, batch_size=42)
    )

    assert list_calls == [1]
    assert delete_calls == [1]
    assert result.scanned == 1
    assert result.deleted == 1
    assert result.dry_run_actions == 0
    assert result.wiki_proposals.scanned == 0


@pytest.mark.asyncio
async def test_in_memory_runner_dry_run_skips_delete_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = ConversationLifecycleEvent(
        conversation_id="s-2",
        team_id="team-a",
        trigger=LifecycleTrigger.MEMBER_REMOVED,
        created_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
    )
    delete_calls: list[int] = []

    async def _fake_list_candidates(
        input_data: ListConversationCandidatesInput,
    ) -> ConversationCandidateBatch:
        assert input_data.limit == 10
        return ConversationCandidateBatch(candidates=[event])

    async def _fake_delete_conversation(
        input_data: DeleteConversationInput,
    ) -> ConversationActionResult:
        delete_calls.append(1)
        return ConversationActionResult(
            conversation_id=input_data.event.conversation_id,
            action="deleted",
            ok=True,
        )

    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.list_conversation_candidates",
        _fake_list_candidates,
    )
    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.delete_conversation",
        _fake_delete_conversation,
    )
    _patch_empty_wiki_sweep(monkeypatch)

    result = await run_lifecycle_manager_once_in_memory(
        LifecycleManagerInput(dry_run=True, batch_size=10)
    )

    assert delete_calls == []
    assert result.scanned == 1
    assert result.deleted == 0
    assert result.dry_run_actions == 1


def _patch_empty_conversation_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mirror of `_patch_empty_wiki_sweep`, for tests about the wiki sweep
    only."""

    async def _no_candidates(
        _input_data: ListConversationCandidatesInput,
    ) -> ConversationCandidateBatch:
        return ConversationCandidateBatch(candidates=[])

    async def _unreachable(
        _input_data: DeleteConversationInput,
    ) -> ConversationActionResult:  # pragma: no cover — no candidate to delete
        raise AssertionError("no conversation candidate was listed")

    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.list_conversation_candidates",
        _no_candidates,
    )
    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.delete_conversation",
        _unreachable,
    )


@pytest.mark.asyncio
async def test_in_memory_runner_also_sweeps_wiki_proposals_in_the_same_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WIKI-05: one in-memory tick runs both sweeps — no second scheduled
    entrypoint was added for the wiki proposal lifecycle."""

    candidate = WikiProposalCandidate(
        revision_id="rev-1",
        team_id="team-a",
        page_id="page-1",
        created_at=datetime.now(timezone.utc),
    )
    reject_calls: list[str] = []

    async def _fake_list_wiki_candidates(
        input_data: ListWikiProposalCandidatesInput,
    ) -> WikiProposalCandidateBatch:
        assert input_data.limit == 42
        return WikiProposalCandidateBatch(candidates=[candidate])

    async def _fake_reject(
        input_data: RejectWikiProposalInput,
    ) -> WikiProposalActionResult:
        reject_calls.append(input_data.candidate.revision_id)
        return WikiProposalActionResult(
            revision_id=input_data.candidate.revision_id,
            action="rejected",
            ok=True,
            changed=True,
        )

    _patch_empty_conversation_sweep(monkeypatch)
    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.list_wiki_proposal_candidates",
        _fake_list_wiki_candidates,
    )
    monkeypatch.setattr(
        "control_plane_backend.scheduler.memory.lifecycle_runner.reject_wiki_proposal",
        _fake_reject,
    )

    result = await run_lifecycle_manager_once_in_memory(
        LifecycleManagerInput(dry_run=False, batch_size=42)
    )

    assert reject_calls == ["rev-1"]
    assert result.wiki_proposals.scanned == 1
    assert result.wiki_proposals.rejected == 1
    assert result.wiki_proposals.dry_run_actions == 0
