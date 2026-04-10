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

    result = await run_lifecycle_manager_once_in_memory(
        LifecycleManagerInput(dry_run=False, batch_size=42)
    )

    assert list_calls == [1]
    assert delete_calls == [1]
    assert result.scanned == 1
    assert result.deleted == 1
    assert result.dry_run_actions == 0


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

    result = await run_lifecycle_manager_once_in_memory(
        LifecycleManagerInput(dry_run=True, batch_size=10)
    )

    assert delete_calls == []
    assert result.scanned == 1
    assert result.deleted == 0
    assert result.dry_run_actions == 1
