"""add knowledge_base_instances and knowledge_base_runs

Revision ID: b6e2f9a04c31
Revises: a3b8d5c17f42
Create Date: 2026-09-13

An instance is a folder that fills itself: the library it fills lives in
knowledge-flow, and this row is what binds it to the definition that fills it,
the team that owns it and the cadence Fred runs it on.

A run row records only that a run exists and where the workflow engine holds
it. Its state is deliberately absent — a stored state would be a copy that goes
stale the moment a pod is killed, which is the case it would exist to cover.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6e2f9a04c31"  # pragma: allowlist secret
down_revision: Union[str, None] = "a3b8d5c17f42"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_instances",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("definition_id", sa.String(length=256), nullable=False),
        sa.Column("team_id", sa.String(length=255), nullable=False),
        sa.Column(
            "library_id",
            sa.String(length=255),
            nullable=False,
            comment=(
                "knowledge-flow tag this instance fills. Unique: two instances "
                "sharing a library would each grant a different pod over it."
            ),
        ),
        sa.Column("library_name", sa.String(length=255), nullable=False),
        sa.Column(
            "cadence",
            sa.String(length=32),
            nullable=False,
            comment=(
                "How often Fred dispatches a run. One of the SDK's declared "
                "cadences — the vocabulary is the platform's, not each author's."
            ),
        ),
        sa.Column("suspended", sa.Boolean(), nullable=False),
        sa.Column(
            "configuration_json",
            sa.Text(),
            nullable=False,
            comment=(
                "JSON-serialized values for the definition's declared fields. "
                "Validated on write and again before a handler is invoked; "
                "never interpreted, and handed back to the pod exactly as "
                "supplied."
            ),
        ),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["knowledge_base_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("library_id"),
    )
    op.create_index(
        op.f("ix_knowledge_base_instances_definition_id"),
        "knowledge_base_instances",
        ["definition_id"],
    )
    op.create_index(
        op.f("ix_knowledge_base_instances_team_id"),
        "knowledge_base_instances",
        ["team_id"],
    )

    op.create_table(
        "knowledge_base_runs",
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("instance_id", sa.String(length=64), nullable=False),
        sa.Column(
            "execution_id",
            sa.String(length=255),
            nullable=False,
            comment=(
                "Workflow id this run belongs to. With run_id it addresses one "
                "execution in the engine, which is where the run's state is "
                "read from."
            ),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["knowledge_base_instances.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_knowledge_base_runs_instance_id"),
        "knowledge_base_runs",
        ["instance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_knowledge_base_runs_instance_id"), table_name="knowledge_base_runs"
    )
    op.drop_table("knowledge_base_runs")
    op.drop_index(
        op.f("ix_knowledge_base_instances_team_id"),
        table_name="knowledge_base_instances",
    )
    op.drop_index(
        op.f("ix_knowledge_base_instances_definition_id"),
        table_name="knowledge_base_instances",
    )
    op.drop_table("knowledge_base_instances")
