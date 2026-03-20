from __future__ import annotations

from pathlib import Path

import yaml

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)


def load_conversation_policy_catalog(path: str | Path) -> ConversationPolicyCatalog:
    catalog_path = Path(path)
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"Conversation policy catalog file is empty: {catalog_path}")
    if not isinstance(payload, dict):
        raise ValueError(
            f"Conversation policy catalog must be a YAML mapping object: {catalog_path}"
        )
    return ConversationPolicyCatalog.model_validate(payload)
