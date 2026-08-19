# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""simplify team_routing_policy: operation_rules -> agent_profile_overrides

Model routing policy is simplified from `(operation, purpose, agent_id) ->
profile` rules to a plain `agent_id -> profile_id` override — no shipped
deployment has ever configured an `operation`- or `purpose`-scoped rule (the
only real rules anywhere were agent_id-only), so this is a one-time cleanup
migration, not a compatibility shim: the application code after this change
never parses the old shape.

Renames `operation_rules_json` (JSON array of
`{rule_id, operation, purpose, agent_id, target_profile_id}`) to
`agent_profile_overrides_json` (JSON object `{agent_id: target_profile_id}`),
transforming each team's stored data in place: rows without an `agent_id`
carried no signal under the new model and are dropped; a later row wins on a
duplicate `agent_id` (write-time validation already prevented duplicates, so
this is a no-op in practice).

Revision ID: b4d5e6f7a8c9
Revises: b7e1c4a09d52
Create Date: 2026-08-13 00:00:00.000000

"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "b4d5e6f7a8c9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b7e1c4a09d52"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_team_routing_policy = sa.table(
    "team_routing_policy",
    sa.column("team_id", sa.String()),
    sa.column("operation_rules_json", sa.Text()),
    sa.column("agent_profile_overrides_json", sa.Text()),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "team_routing_policy",
        sa.Column(
            "agent_profile_overrides_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
            comment="JSON-serialized {agent_id: target_profile_id} dict.",
        ),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            _team_routing_policy.c.team_id, _team_routing_policy.c.operation_rules_json
        )
    ).fetchall()
    for team_id, operation_rules_json in rows:
        old_rules = json.loads(operation_rules_json or "[]")
        overrides: dict[str, str] = {}
        dropped = 0
        for rule in old_rules:
            agent_id = rule.get("agent_id")
            target_profile_id = rule.get("target_profile_id")
            if not agent_id or not target_profile_id:
                # No agent_id: an operation-/purpose-only rule carries no
                # signal under the new agent_id -> profile_id shape and is
                # deliberately dropped. Missing target_profile_id despite an
                # agent_id: a malformed row that predates this migration's
                # own assumptions — skip rather than crash the deploy on it.
                dropped += 1
                continue
            overrides[agent_id] = target_profile_id
        if dropped:
            logger.warning(
                "team_routing_policy migration: dropped %d operation_rules "
                "entr%s with no agent_id/target_profile_id for team_id=%s "
                "(agent-scoped entries are preserved as agent_profile_overrides)",
                dropped,
                "y" if dropped == 1 else "ies",
                team_id,
            )
        connection.execute(
            _team_routing_policy.update()
            .where(_team_routing_policy.c.team_id == team_id)
            .values(agent_profile_overrides_json=json.dumps(overrides))
        )

    op.drop_column("team_routing_policy", "operation_rules_json")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "team_routing_policy",
        sa.Column(
            "operation_rules_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
            comment="JSON-serialized list of TeamOperationRouteRule.",
        ),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            _team_routing_policy.c.team_id,
            _team_routing_policy.c.agent_profile_overrides_json,
        )
    ).fetchall()
    for team_id, agent_profile_overrides_json in rows:
        overrides = json.loads(agent_profile_overrides_json or "{}")
        rules = [
            {
                "rule_id": agent_id,
                "operation": None,
                "purpose": None,
                "agent_id": agent_id,
                "target_profile_id": target_profile_id,
            }
            for agent_id, target_profile_id in overrides.items()
        ]
        connection.execute(
            _team_routing_policy.update()
            .where(_team_routing_policy.c.team_id == team_id)
            .values(operation_rules_json=json.dumps(rules))
        )

    op.drop_column("team_routing_policy", "agent_profile_overrides_json")
