"""upgrade session schema

Brings the session table up to date with the current ORM:
- add team_id column
- change session_data from json to jsonb
- set NOT NULL on user_id, session_data, updated_at
- add ix_session_team_id and ix_session_history_timestamp indexes

Revision ID: 5c9bc83efbfb
Revises: bb94940fde0c
Create Date: 2026-03-26 17:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5c9bc83efbfb'
down_revision: Union[str, Sequence[str], None] = 'bb94940fde0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # -- session table --

    # Add team_id column (nullable, new column)
    op.add_column('session', sa.Column('team_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_session_team_id'), 'session', ['team_id'], unique=False)

    # Fill NULLs before setting NOT NULL constraints
    op.execute("UPDATE session SET user_id = 'unknown' WHERE user_id IS NULL")
    op.execute("UPDATE session SET session_data = '{}' WHERE session_data IS NULL")
    op.execute("UPDATE session SET updated_at = NOW() WHERE updated_at IS NULL")

    # Change session_data from json to jsonb (PostgreSQL only, no-op on SQLite)
    op.execute(
        "ALTER TABLE session "
        "ALTER COLUMN session_data TYPE jsonb USING session_data::jsonb"
    )

    # Set NOT NULL constraints
    op.alter_column('session', 'user_id', existing_type=sa.String(), nullable=False)
    op.alter_column('session', 'session_data', nullable=False)
    op.alter_column('session', 'updated_at', existing_type=sa.DateTime(timezone=True), nullable=False)

    # -- session_history table --
    op.create_index('ix_session_history_timestamp', 'session_history', ['timestamp'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # -- session_history table --
    op.drop_index('ix_session_history_timestamp', table_name='session_history')

    # -- session table --
    op.alter_column('session', 'updated_at', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column('session', 'session_data', nullable=True)
    op.alter_column('session', 'user_id', existing_type=sa.String(), nullable=True)

    # Change session_data back from jsonb to json
    op.execute(
        "ALTER TABLE session "
        "ALTER COLUMN session_data TYPE json USING session_data::text::json"
    )

    op.drop_index(op.f('ix_session_team_id'), table_name='session')
    op.drop_column('session', 'team_id')
