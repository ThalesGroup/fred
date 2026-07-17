"""drop the `mcp:` prefix from persisted capability tuning

#1988 (CAPAB-01, supersedes part of #1978). An MCP-backed capability's id is now
the plain catalog server id — the `mcp:` prefix is gone, because a `:` is illegal
in an OpenFGA object id and crashed capability seeding. This rewrites the tuning
persisted by branch-only migration ``f5b6c7d8e9a0_retire_mcp_tuning_trio.py``
(which had folded the MCP trio into ``mcp:<server>`` slices) so every id becomes
FGA-safe:

- entries in ``selected_capability_ids`` of the form ``mcp:X`` become ``X``
- keys of ``capability_config`` of the form ``mcp:X`` become ``X``

Mechanics mirror ``f5b6c7d8e9a0``: iterate ``agent_instance.tuning_json``, decode,
transform, re-encode. Self-contained (no app imports), idempotent (a payload with
no ``mcp:`` ids is left byte-for-byte unchanged), and best-effort per row (a
malformed payload is skipped, never fatal).

Revision ID: a1b2c3d4e5f7
Revises: f5b6c7d8e9a0
Create Date: 2026-07-15 00:00:00.000000

"""

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f5b6c7d8e9a0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MCP_PREFIX = "mcp:"


def _strip(cap_id: Any) -> Any:
    """`mcp:X` -> `X`; anything else returned unchanged."""

    if isinstance(cap_id, str) and cap_id.startswith(_MCP_PREFIX):
        return cap_id[len(_MCP_PREFIX) :]
    return cap_id


def _forward(tuning: dict[str, Any]) -> dict[str, Any]:
    """Strip the `mcp:` prefix from every capability id in one tuning payload."""

    selected = tuning.get("selected_capability_ids")
    if isinstance(selected, list):
        tuning["selected_capability_ids"] = [_strip(cid) for cid in selected]

    config = tuning.get("capability_config")
    if isinstance(config, dict):
        # Last write wins if a bare `X` and an `mcp:X` ever coexist (they cannot
        # in practice — the retire migration only ever wrote `mcp:X` slices).
        tuning["capability_config"] = {
            _strip(key): value for key, value in config.items()
        }

    return tuning


def _rewrite_all(transform) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT agent_instance_id, tuning_json FROM agent_instance")
    ).fetchall()
    for agent_instance_id, tuning_json in rows:
        if not tuning_json:
            continue
        try:
            tuning = json.loads(tuning_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(tuning, dict):
            continue
        new_json = json.dumps(transform(tuning))
        if new_json == tuning_json:
            # Idempotent: nothing to rewrite for this row.
            continue
        conn.execute(
            sa.text(
                "UPDATE agent_instance SET tuning_json = :tuning "
                "WHERE agent_instance_id = :id"
            ),
            {"tuning": new_json, "id": agent_instance_id},
        )


def upgrade() -> None:
    """Strip the `mcp:` prefix from every stored capability id (#1988)."""

    _rewrite_all(_forward)


def downgrade() -> None:
    """No-op — the prefix strip is NOT safely reversible.

    The inverse rule (`X` -> `mcp:X`) is pod-agnostic and cannot tell an
    MCP-backed capability id apart from an ordinary package capability id: a
    blind re-prefix would corrupt every non-MCP id. Since the prior branch-only
    state this restores to is itself unshipped, there is nothing to roll back
    to, so downgrade intentionally does nothing.
    """
