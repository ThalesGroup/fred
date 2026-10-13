# SPDX-License-Identifier: Apache-2.0
"""Make agent names unique within a team.

Trims every agent name, renames the later agents of a colliding name
`<name> (2)`, `<name> (3)`... in creation order, then adds the unique index on
`(team_id, lower(display_name))`; names are stored trimmed, so `trim` is not
indexed (PostgreSQL would reflect it as `TRIM(BOTH FROM …)`, failing the
autogenerate check). The downgrade only drops the index.

Revision ID: a4d85307ea0e
Revises: f9a2c7d81e40
"""

from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "a4d85307ea0e"  # pragma: allowlist secret
down_revision = "f9a2c7d81e40"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_INDEX = "uq_agent_instance_team_name"
_NAME_MAX = 255

_agents = sa.table(
    "agent_instance",
    sa.column("agent_instance_id", sa.String),
    sa.column("team_id", sa.String),
    sa.column("display_name", sa.String),
    sa.column("created_at", sa.DateTime),
)


def _norm(name: str) -> str:
    return name.strip().lower()


def _renamed(name: str, taken: set[str]) -> str:
    n = 2
    while True:
        suffix = f" ({n})"
        candidate = f"{name[: _NAME_MAX - len(suffix)]}{suffix}"
        if _norm(candidate) not in taken:
            return candidate
        n += 1


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            _agents.c.agent_instance_id,
            _agents.c.team_id,
            _agents.c.display_name,
        ).order_by(_agents.c.created_at, _agents.c.agent_instance_id)
    ).all()

    by_team: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for agent_id, team_id, name in rows:
        by_team[team_id].append((agent_id, name, name.strip()))

    updates: list[dict[str, str]] = []
    for agents in by_team.values():
        taken = {_norm(trimmed) for _, _, trimmed in agents}
        seen: set[str] = set()
        for agent_id, original, trimmed in agents:
            name = trimmed
            if _norm(name) in seen:
                name = _renamed(trimmed, taken)
                taken.add(_norm(name))
            seen.add(_norm(name))
            if name != original:
                updates.append({"agent_id": agent_id, "name": name})

    if updates:
        bind.execute(
            _agents.update()
            .where(_agents.c.agent_instance_id == sa.bindparam("agent_id"))
            .values(display_name=sa.bindparam("name")),
            updates,
        )

    op.create_index(
        _INDEX,
        "agent_instance",
        ["team_id", sa.text("lower(display_name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="agent_instance")
