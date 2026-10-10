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
"""Team model exceptions; per-template overrides become instance recommendations.

Adds the team's disabled-model and reasoning-off exception lists, copies each
per-template override into `recommended_chat_profile_id` of the team's
instances of that template that have none, then drops the overrides column.
The downgrade re-adds that column empty: the copied recommendations stay in
`tuning_json`, so per-template routing is lost on rollback.

Revision ID: e9026d8e4db6
Revises: f9a2c7d81e40
"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9026d8e4db6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f9a2c7d81e40"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")
_RECOMMENDATION_KEY = "recommended_chat_profile_id"


def _copy_overrides_to_instances(conn: sa.engine.Connection) -> int:
    """Copy every stored override onto matching instances without a
    recommendation. Returns how many instances were updated."""

    policies = conn.execute(
        sa.text("SELECT team_id, agent_profile_overrides_json FROM team_routing_policy")
    ).fetchall()
    copied = 0
    for team_id, overrides_json in policies:
        try:
            overrides = json.loads(overrides_json or "{}")
        except ValueError:
            overrides = None
        if not isinstance(overrides, dict):
            logger.warning(
                "Skipping team_routing_policy %s: invalid overrides", team_id
            )
            continue
        for source_agent_id, profile_id in overrides.items():
            if not isinstance(profile_id, str) or not profile_id:
                continue
            rows = conn.execute(
                sa.text(
                    "SELECT agent_instance_id, tuning_json FROM agent_instance "
                    "WHERE team_id = :team_id AND source_agent_id = :agent_id"
                ),
                {"team_id": team_id, "agent_id": source_agent_id},
            ).fetchall()
            for agent_instance_id, original in rows:
                try:
                    tuning = json.loads(original) if original else None
                except ValueError:
                    tuning = None
                if not isinstance(tuning, dict):
                    # A row without a parseable tuning object loads with
                    # defaults, so a lone recommendation would be dropped anyway.
                    logger.warning(
                        "Skipping agent_instance %s: tuning_json is not a JSON object",
                        agent_instance_id,
                    )
                    continue
                if tuning.get(_RECOMMENDATION_KEY):
                    continue
                tuning[_RECOMMENDATION_KEY] = profile_id
                # Compare-and-swap prevents overwriting an edit made after the SELECT.
                result = conn.execute(
                    sa.text(
                        "UPDATE agent_instance SET tuning_json = :updated "
                        "WHERE agent_instance_id = :id AND tuning_json = :original"
                    ),
                    {
                        "id": agent_instance_id,
                        "original": original,
                        "updated": json.dumps(tuning),
                    },
                )
                if result.rowcount != 1:
                    raise RuntimeError(
                        f"Concurrent edit of agent_instance {agent_instance_id}; "
                        "quiesce agent writes and retry the migration"
                    )
                copied += 1
    return copied


def upgrade() -> None:
    for column, comment in (
        (
            "disabled_model_ids_json",
            "JSON list of model capability ids the team disabled.",
        ),
        (
            "reasoning_default_off_model_ids_json",
            "JSON list of model capability ids whose reasoning starts off.",
        ),
    ):
        op.add_column(
            "team_routing_policy",
            sa.Column(
                column,
                sa.Text(),
                nullable=False,
                server_default="[]",
                comment=comment,
            ),
        )
    copied = _copy_overrides_to_instances(op.get_bind())
    logger.info(
        "team_routing_policy: copied %d per-template override(s) to instances",
        copied,
    )
    with op.batch_alter_table("team_routing_policy") as batch:
        batch.drop_column("agent_profile_overrides_json")


def downgrade() -> None:
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
    with op.batch_alter_table("team_routing_policy") as batch:
        batch.drop_column("reasoning_default_off_model_ids_json")
        batch.drop_column("disabled_model_ids_json")
