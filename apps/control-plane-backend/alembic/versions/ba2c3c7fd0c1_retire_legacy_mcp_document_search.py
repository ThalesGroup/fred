# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Remove retired document-search and GitHub MCP selections/configuration.

Revision ID: ba2c3c7fd0c1
Revises: c4d7e2a91b30
Create Date: 2026-09-30
"""

import json
import logging
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "ba2c3c7fd0c1"  # pragma: allowlist secret
down_revision: str = "c4d7e2a91b30"  # pragma: allowlist secret
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")
_RETIRED_IDS = {
    "mcp-knowledge-flow-mcp-text",
    "mcp:mcp-knowledge-flow-mcp-text",
    "mcp-web-github-readonly",
    "mcp:mcp-web-github-readonly",
}


def _remove_retired_mcp(tuning: dict[str, Any]) -> dict[str, Any]:
    # Persisted JSON can contain unknown fields; preserve them without revalidation.
    updated = dict(tuning)
    selected = tuning.get("selected_capability_ids")
    if isinstance(selected, list):
        updated["selected_capability_ids"] = [
            cap_id
            for cap_id in selected
            if not isinstance(cap_id, str) or cap_id not in _RETIRED_IDS
        ]
    config = tuning.get("capability_config")
    if isinstance(config, dict):
        updated["capability_config"] = {
            key: value for key, value in config.items() if key not in _RETIRED_IDS
        }
    return updated


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT agent_instance_id, tuning_json FROM agent_instance "
            "WHERE tuning_json IS NOT NULL"
        )
    ).fetchall()
    for agent_instance_id, original in rows:
        try:
            tuning = json.loads(original)
        except (TypeError, ValueError):
            tuning = None
        if not isinstance(tuning, dict):
            logger.warning(
                "Skipping agent_instance %s: tuning_json is not a JSON object",
                agent_instance_id,
            )
            continue
        updated = _remove_retired_mcp(tuning)
        if updated == tuning:
            continue
        # Compare-and-swap prevents overwriting an edit made after the SELECT.
        result = conn.execute(
            sa.text(
                "UPDATE agent_instance SET tuning_json = :updated "
                "WHERE agent_instance_id = :id AND tuning_json = :original"
            ),
            {
                "id": agent_instance_id,
                "original": original,
                "updated": json.dumps(updated),
            },
        )
        if result.rowcount != 1:
            raise RuntimeError(
                f"Concurrent edit of agent_instance {agent_instance_id}; "
                "quiesce agent writes and retry the migration"
            )


def downgrade() -> None:
    """No-op: restoring removed selections/configuration requires a backup."""
