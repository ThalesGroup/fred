"""Backward-compatible policy catalog loader."""

from __future__ import annotations

from pathlib import Path

from control_plane_backend.scheduler.policies.policy_loader import (
    load_conversation_policy_catalog,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)

__all__ = ["ConversationPolicyCatalog", "load_conversation_policy_catalog"]


def load_catalog(path: str | Path) -> ConversationPolicyCatalog:
    return load_conversation_policy_catalog(path)
