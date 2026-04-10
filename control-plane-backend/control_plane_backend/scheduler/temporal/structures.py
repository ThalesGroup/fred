from __future__ import annotations

from pydantic import BaseModel, Field

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
)


class LifecycleManagerInput(BaseModel):
    dry_run: bool = False
    batch_size: int = Field(default=100, ge=1, le=5000)


class LifecycleManagerResult(BaseModel):
    scanned: int = 0
    deleted: int = 0
    dry_run_actions: int = 0


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
