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

"""require a team description

Missing, blank or too-short descriptions get the fred-core placeholder, then
`teammetadata.description` becomes `VARCHAR(500) NOT NULL` with a CHECK on its
trimmed length. Downgrade clears placeholders and cuts descriptions to 180
characters (lossy) before restoring the nullable `VARCHAR(180)`.

Revision ID: c9acb7dd3ad0
Revises: c3a7e5d9f1b2
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9acb7dd3ad0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c3a7e5d9f1b2"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]

_CHECK = "ck_teammetadata_description_min_length"
_OLD_MAX = 180
# Frozen copies: a revision must keep doing the same thing whatever the
# application later decides about the bounds or the default text.
_MIN = 20
_PLACEHOLDER = "Description à compléter par l'administrateur de l'équipe."

_teams = sa.table(
    "teammetadata",
    sa.column("id", sa.String),
    sa.column("description", sa.String),
)


def _normalise(description: str | None) -> str:
    cleaned = (description or "").strip()
    return cleaned if len(cleaned) >= _MIN else _PLACEHOLDER


def _rewrite(changes: list[dict[str, str | None]]) -> None:
    if changes:
        op.get_bind().execute(
            _teams.update()
            .where(_teams.c.id == sa.bindparam("team_id"))
            .values(description=sa.bindparam("value")),
            changes,
        )


def upgrade() -> None:
    """Upgrade schema."""
    rows = op.get_bind().execute(sa.select(_teams.c.id, _teams.c.description)).all()
    changes: list[dict[str, str | None]] = []
    for team_id, description in rows:
        value = _normalise(description)
        if value != description:
            changes.append({"team_id": team_id, "value": value})
    _rewrite(changes)

    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=_OLD_MAX),
            type_=sa.String(length=500),
            nullable=False,
        )
        batch_op.create_check_constraint(_CHECK, "length(trim(description)) >= 20")


def downgrade() -> None:
    """Downgrade schema."""
    rows = op.get_bind().execute(sa.select(_teams.c.id, _teams.c.description)).all()
    changes: list[dict[str, str | None]] = []
    for team_id, description in rows:
        if description == _PLACEHOLDER:
            changes.append({"team_id": team_id, "value": None})
        elif description is not None and len(description) > _OLD_MAX:
            changes.append({"team_id": team_id, "value": description[:_OLD_MAX]})

    # Drop the CHECK first: clearing a placeholder would violate it.
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.drop_constraint(_CHECK, type_="check")
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=500),
            nullable=True,
        )
    _rewrite(changes)
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "description",
            existing_type=sa.String(length=500),
            type_=sa.String(length=_OLD_MAX),
            existing_nullable=True,
        )
