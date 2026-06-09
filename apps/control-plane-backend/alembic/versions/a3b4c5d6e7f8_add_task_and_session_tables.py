"""add session, task_run, task_event_log tables; fix storage nullable columns

Revision ID: a3b4c5d6e7f8
Revises: f0f1e2d3c4b5
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f0f1e2d3c4b5"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
_BIGINT_PK = sa.BigInteger().with_variant(sa.INTEGER(), "sqlite")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("session_data", _JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(op.f("ix_session_user_id"), "session", ["user_id"], unique=False)
    op.create_index(op.f("ix_session_team_id"), "session", ["team_id"], unique=False)
    op.create_index(op.f("ix_session_agent_id"), "session", ["agent_id"], unique=False)
    op.create_index(
        op.f("ix_session_updated_at"), "session", ["updated_at"], unique=False
    )

    op.create_table(
        "task_run",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("detail", _JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("target", _JSONB, nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("team_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(op.f("ix_task_run_kind"), "task_run", ["kind"], unique=False)
    op.create_index(op.f("ix_task_run_state"), "task_run", ["state"], unique=False)
    op.create_index(
        op.f("ix_task_run_created_by"), "task_run", ["created_by"], unique=False
    )
    op.create_index(op.f("ix_task_run_team_id"), "task_run", ["team_id"], unique=False)

    op.create_table(
        "task_event_log",
        sa.Column("id", _BIGINT_PK, nullable=False, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("detail", _JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("target", _JSONB, nullable=True),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "seq", name="uq_task_event_log_task_seq"),
    )
    op.create_index(
        op.f("ix_task_event_log_task_id"), "task_event_log", ["task_id"], unique=False
    )

    # Backfill NULLs before enforcing NOT NULL — safe on a fresh DB and on
    # deployments that never wrote a non-zero value yet.
    op.execute(
        "UPDATE users SET current_resources_storage_size = 0 WHERE current_resources_storage_size IS NULL"
    )
    op.execute(
        "UPDATE teammetadata SET current_resources_storage_size = 0 WHERE current_resources_storage_size IS NULL"
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "current_resources_storage_size",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "current_resources_storage_size",
            existing_type=sa.BigInteger(),
            nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "current_resources_storage_size",
            existing_type=sa.BigInteger(),
            nullable=True,
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "current_resources_storage_size",
            existing_type=sa.BigInteger(),
            nullable=True,
        )

    op.drop_index(op.f("ix_task_event_log_task_id"), table_name="task_event_log")
    op.drop_table("task_event_log")

    op.drop_index(op.f("ix_task_run_team_id"), table_name="task_run")
    op.drop_index(op.f("ix_task_run_created_by"), table_name="task_run")
    op.drop_index(op.f("ix_task_run_state"), table_name="task_run")
    op.drop_index(op.f("ix_task_run_kind"), table_name="task_run")
    op.drop_table("task_run")

    op.drop_index(op.f("ix_session_updated_at"), table_name="session")
    op.drop_index(op.f("ix_session_agent_id"), table_name="session")
    op.drop_index(op.f("ix_session_team_id"), table_name="session")
    op.drop_index(op.f("ix_session_user_id"), table_name="session")
    op.drop_table("session")
