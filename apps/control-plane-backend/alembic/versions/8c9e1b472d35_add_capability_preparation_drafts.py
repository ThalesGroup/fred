# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Allow temporary capability preparation ownership before agent save."""

import sqlalchemy as sa
from alembic import op

revision = "8c9e1b472d35"  # pragma: allowlist secret
down_revision = "d7a2f591c034"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capability_preparation", sa.Column("draft_author_id", sa.String(255))
    )
    op.add_column(
        "capability_preparation", sa.Column("draft_target_id", sa.String(512))
    )
    op.add_column("capability_preparation", sa.Column("draft_generation", sa.Integer()))
    op.add_column(
        "capability_preparation",
        sa.Column("draft_expires_at", sa.DateTime(timezone=True)),
    )
    op.drop_constraint("ck_cap_asset_owner", "capability_asset", type_="check")
    op.drop_constraint("ck_cap_asset_team", "capability_asset", type_="check")
    op.drop_constraint("ck_cap_prep_owner", "capability_preparation", type_="check")
    op.drop_constraint("ck_cap_prep_team", "capability_preparation", type_="check")
    op.create_check_constraint(
        "ck_cap_asset_owner",
        "capability_asset",
        "owner_kind in ('agent', 'platform', 'draft')",
    )
    op.create_check_constraint(
        "ck_cap_asset_team",
        "capability_asset",
        "(owner_kind in ('agent', 'draft') and team_id is not null) or (owner_kind = 'platform' and team_id is null)",
    )
    op.create_check_constraint(
        "ck_cap_prep_owner",
        "capability_preparation",
        "owner_kind in ('agent', 'platform', 'draft')",
    )
    op.create_check_constraint(
        "ck_cap_prep_team",
        "capability_preparation",
        "(owner_kind in ('agent', 'draft') and team_id is not null) or (owner_kind = 'platform' and team_id is null)",
    )
    op.create_check_constraint(
        "ck_cap_prep_draft",
        "capability_preparation",
        "(owner_kind = 'draft' and draft_author_id is not null and draft_target_id is not null and draft_generation is not null and draft_expires_at is not null) or (owner_kind != 'draft' and draft_author_id is null and draft_target_id is null and draft_generation is null and draft_expires_at is null)",
    )
    op.create_index(
        "ix_cap_prep_draft_expiry",
        "capability_preparation",
        ["runtime_id", "owner_kind", "draft_expires_at", "id"],
    )
    op.create_index(
        "ix_cap_prep_draft_author",
        "capability_preparation",
        ["team_id", "draft_author_id", "owner_kind", "is_current"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("capability_preparation", "capability_asset"):
        if connection.execute(
            sa.text(f"select 1 from {table} where owner_kind = 'draft' limit 1")
        ).first():
            raise RuntimeError("Discard and clean draft preparations before downgrade")
    op.drop_index("ix_cap_prep_draft_author", table_name="capability_preparation")
    op.drop_index("ix_cap_prep_draft_expiry", table_name="capability_preparation")
    op.drop_constraint("ck_cap_prep_draft", "capability_preparation", type_="check")
    op.drop_constraint("ck_cap_prep_team", "capability_preparation", type_="check")
    op.drop_constraint("ck_cap_prep_owner", "capability_preparation", type_="check")
    op.drop_constraint("ck_cap_asset_team", "capability_asset", type_="check")
    op.drop_constraint("ck_cap_asset_owner", "capability_asset", type_="check")
    op.create_check_constraint(
        "ck_cap_asset_owner", "capability_asset", "owner_kind in ('agent', 'platform')"
    )
    op.create_check_constraint(
        "ck_cap_asset_team",
        "capability_asset",
        "(owner_kind = 'agent' and team_id is not null) or (owner_kind = 'platform' and team_id is null)",
    )
    op.create_check_constraint(
        "ck_cap_prep_owner",
        "capability_preparation",
        "owner_kind in ('agent', 'platform')",
    )
    op.create_check_constraint(
        "ck_cap_prep_team",
        "capability_preparation",
        "(owner_kind = 'agent' and team_id is not null) or (owner_kind = 'platform' and team_id is null)",
    )
    op.drop_column("capability_preparation", "draft_expires_at")
    op.drop_column("capability_preparation", "draft_generation")
    op.drop_column("capability_preparation", "draft_target_id")
    op.drop_column("capability_preparation", "draft_author_id")
