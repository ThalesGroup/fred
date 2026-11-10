# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Add capability-neutral asset and preparation state.

Revision ID: 52344270c256
Revises: b8e1f4a2c6d9
Create Date: 2026-11-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Alembic reads these revision identifiers by introspection.
# codeql[py/unused-global-variable]
revision: str = "52344270c256"  # pragma: allowlist secret
# codeql[py/unused-global-variable]
down_revision: Union[str, Sequence[str], None] = (
    "b8e1f4a2c6d9"  # pragma: allowlist secret
)
# codeql[py/unused-global-variable]
branch_labels: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> tuple[sa.Table, sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    asset = sa.Table(
        "capability_asset",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_kind", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("team_id", sa.String(255)),
        sa.Column("runtime_id", sa.String(255), nullable=False),
        sa.Column("capability_id", sa.String(255), nullable=False),
        sa.Column("slot_key", sa.String(128), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "owner_kind in ('agent', 'platform')", name="ck_cap_asset_owner"
        ),
        sa.CheckConstraint(
            "(owner_kind = 'agent' and team_id is not null) or "
            "(owner_kind = 'platform' and team_id is null)",
            name="ck_cap_asset_team",
        ),
        sa.CheckConstraint("state in ('stored', 'retired')", name="ck_cap_asset_state"),
        sa.CheckConstraint("size >= 0 and size <= 67108864", name="ck_cap_asset_size"),
        sa.UniqueConstraint("object_key", name="uq_cap_asset_object_key"),
    )
    sa.Index(
        "ix_cap_asset_owner",
        asset.c.owner_kind,
        asset.c.owner_id,
        asset.c.capability_id,
        asset.c.state,
    )

    preparation = sa.Table(
        "capability_preparation",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_kind", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("team_id", sa.String(255)),
        sa.Column("runtime_id", sa.String(255), nullable=False),
        sa.Column("capability_id", sa.String(255), nullable=False),
        sa.Column("input_revision", sa.String(128), nullable=False),
        sa.Column("rules_version", sa.String(64), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("public_config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("gates_readiness", sa.Boolean(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "dispatch_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("workflow_id", sa.String(255), nullable=False),
        sa.Column("task_queue", sa.String(255), nullable=False),
        sa.Column("worker_token", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(255)),
        sa.Column("delivery_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatch_owner", sa.String(36)),
        sa.Column("dispatch_until", sa.DateTime(timezone=True)),
        sa.Column("result_reference", sa.String(512)),
        sa.Column("result_summary", sa.String(2000)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_detail", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("cleaned_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "owner_kind in ('agent', 'platform')", name="ck_cap_prep_owner"
        ),
        sa.CheckConstraint(
            "(owner_kind = 'agent' and team_id is not null) or "
            "(owner_kind = 'platform' and team_id is null)",
            name="ck_cap_prep_team",
        ),
        sa.CheckConstraint(
            "state in ('pending', 'running', 'succeeded', 'failed', 'obsolete')",
            name="ck_cap_prep_state",
        ),
        sa.CheckConstraint(
            "attempts >= 0 and attempts <= max_attempts", name="ck_cap_prep_attempts"
        ),
        sa.CheckConstraint(
            "max_attempts between 1 and 10", name="ck_cap_prep_max_attempts"
        ),
        sa.CheckConstraint(
            "dispatch_attempts between 0 and 10", name="ck_cap_prep_dispatch_attempts"
        ),
        sa.CheckConstraint(
            "not (is_current and state = 'obsolete')", name="ck_cap_prep_current"
        ),
        sa.UniqueConstraint(
            "owner_kind",
            "owner_id",
            "capability_id",
            "input_revision",
            "rules_version",
            name="uq_cap_prep_revision",
        ),
        sa.UniqueConstraint("workflow_id", name="uq_cap_prep_workflow"),
    )
    sa.Index(
        "uq_cap_prep_current_owner",
        preparation.c.owner_kind,
        preparation.c.owner_id,
        preparation.c.capability_id,
        unique=True,
        postgresql_where=sa.text("is_current"),
        sqlite_where=sa.text("is_current"),
    )
    sa.Index(
        "ix_cap_prep_due",
        preparation.c.state,
        preparation.c.delivery_due_at,
        preparation.c.id,
    )
    sa.Index(
        "ix_cap_prep_readiness",
        preparation.c.owner_kind,
        preparation.c.owner_id,
        preparation.c.is_current,
        preparation.c.state,
    )
    sa.Index(
        "ix_cap_prep_cleanup",
        preparation.c.runtime_id,
        preparation.c.is_current,
        preparation.c.cleaned_at,
        preparation.c.superseded_at,
    )

    link = sa.Table(
        "capability_preparation_asset",
        metadata,
        sa.Column(
            "preparation_id",
            sa.String(36),
            sa.ForeignKey("capability_preparation.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("capability_asset.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "preparation_id", "asset_id", name="uq_cap_prep_asset_once"
        ),
    )
    sa.Index("ix_cap_prep_asset_asset", link.c.asset_id)
    selection = sa.Table(
        "capability_platform_selection",
        metadata,
        sa.Column("runtime_id", sa.String(255), primary_key=True),
        sa.Column("capability_id", sa.String(255), primary_key=True),
        sa.Column("slot_key", sa.String(128), primary_key=True),
        sa.Column(
            "active_preparation_id",
            sa.String(36),
            sa.ForeignKey("capability_preparation.id"),
        ),
        sa.Column(
            "candidate_preparation_id",
            sa.String(36),
            sa.ForeignKey("capability_preparation.id"),
        ),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_cap_platform_candidate", selection.c.candidate_preparation_id)
    return asset, preparation, link, selection


def upgrade() -> None:
    for table in _tables():
        table.create(op.get_bind())


def downgrade() -> None:
    for table in reversed(_tables()):
        table.drop(op.get_bind())
