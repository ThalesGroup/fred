"""add standard created_at updated_at to all tables

Adds TimestampMixin columns (created_at, updated_at) to all tables that were
missing them, normalises existing timestamp columns to use server_default/onupdate,
and back-fills existing rows with the prod opening sentinel (2026-05-04 15:30 UTC).

Revision ID: b5393ea7a65d
Revises: 5978e4ad3e1b
Create Date: 2026-05-07 18:05:27.796417

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5393ea7a65d"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "5978e4ad3e1b"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SENTINEL = "2026-05-04 15:30:00+00"

ts_type = postgresql.TIMESTAMP(timezone=True).with_variant(
    sa.DateTime(timezone=True), "sqlite"
)


def upgrade() -> None:
    """Upgrade schema."""
    # -- agent: no prior timestamps --
    # server_default=CURRENT_TIMESTAMP for future inserts; existing rows get sentinel.
    with op.batch_alter_table("agent", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
    op.execute(f"UPDATE agent SET created_at = '{SENTINEL}', updated_at = '{SENTINEL}'")

    # -- mcp-server: no prior timestamps --
    with op.batch_alter_table("mcp-server", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
    op.execute(
        f"UPDATE \"mcp-server\" SET created_at = '{SENTINEL}', updated_at = '{SENTINEL}'"
    )

    # -- feedbacks: had created_at (no server_default), no updated_at --
    # Add updated_at back-filled from created_at, then normalise server_defaults.
    with op.batch_alter_table("feedbacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "updated_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
    op.execute("UPDATE feedbacks SET updated_at = created_at")

    # -- tasks: had created_at + updated_at (TimestampColumn, no server_default) --
    # Normalise server_defaults only (no data change needed, columns already exist).
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )

    # -- session: had updated_at (no server_default), no created_at --
    # Back-fill created_at from updated_at when it predates the sentinel.
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
    # Use the real updated_at as created_at when it is earlier than the sentinel.
    # On SQLite there is no LEAST(); fall back to a plain CASE expression.
    op.execute(
        f"""
        UPDATE session
        SET created_at = CASE
            WHEN updated_at < '{SENTINEL}' THEN updated_at
            ELSE '{SENTINEL}'
        END
        """
    )

    # -- session_attachments: had both (DateTime, no server_default) --
    with op.batch_alter_table("session_attachments", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )

    # -- session_history: no prior timestamps --
    # Back-fill from the existing `timestamp` domain column (message time).
    with op.batch_alter_table("session_history", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                ts_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
    op.execute(
        "UPDATE session_history SET created_at = timestamp, updated_at = timestamp"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("session_history", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")

    with op.batch_alter_table("session_attachments", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )

    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        batch_op.drop_column("created_at")

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            nullable=False,
            server_default=None,
        )

    with op.batch_alter_table("feedbacks", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("mcp-server", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")

    with op.batch_alter_table("agent", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
