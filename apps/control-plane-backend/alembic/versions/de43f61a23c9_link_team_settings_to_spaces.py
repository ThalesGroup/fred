# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Make team settings an extension of the canonical space identity.

Revision ID: de43f61a23c9
Revises: cd32e50f12b8
"""

import sqlalchemy as sa
from alembic import op

revision = "de43f61a23c9"
down_revision = "cd32e50f12b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The stopped-platform translator must supply explicit ancestry first.
    unmapped = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT t.id FROM teammetadata t LEFT JOIN space s ON s.id = t.id "
                "WHERE s.id IS NULL OR s.kind <> 'team' OR s.name <> t.name LIMIT 1"
            )
        )
        .first()
    )
    if unmapped is not None:
        raise RuntimeError(
            "Translate existing team identities into organization-owned spaces "
            "before applying the team-settings migration."
        )
    with op.batch_alter_table("teammetadata") as batch:
        batch.add_column(
            sa.Column(
                "space_kind", sa.String(20), nullable=False, server_default="team"
            )
        )
        batch.create_check_constraint(
            "ck_teammetadata_space_kind", "space_kind = 'team'"
        )
        batch.create_foreign_key(
            "fk_teammetadata_space", "space", ["id", "space_kind"], ["id", "kind"]
        )
        batch.drop_constraint("uq_teammetadata_name", type_="unique")
        batch.drop_column("name")


def downgrade() -> None:
    with op.batch_alter_table("teammetadata") as batch:
        batch.add_column(sa.Column("name", sa.String(180), nullable=True))
    op.execute(
        sa.text(
            "UPDATE teammetadata SET name = "
            "(SELECT space.name FROM space WHERE space.id = teammetadata.id)"
        )
    )
    with op.batch_alter_table("teammetadata") as batch:
        batch.alter_column("name", nullable=False, existing_type=sa.String(180))
        batch.create_unique_constraint("uq_teammetadata_name", ["name"])
        batch.drop_constraint("fk_teammetadata_space", type_="foreignkey")
        batch.drop_constraint("ck_teammetadata_space_kind", type_="check")
        batch.drop_column("space_kind")
