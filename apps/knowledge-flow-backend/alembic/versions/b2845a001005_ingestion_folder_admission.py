"""Record the ingestion destination before shared corpus writes.

Revision ID: b2845a001005
Revises: b2845a001004
"""

import sqlalchemy as sa

from alembic import op

revision = "b2845a001005"
down_revision = "b2845a001004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    active = op.get_bind().execute(sa.text("SELECT task_id FROM kf_task_run WHERE kind = 'ingestion' AND state NOT IN ('succeeded', 'failed', 'cancelled') LIMIT 1")).scalar()
    if active is not None:
        raise RuntimeError(f"Finish or manually resolve ingestion task {active} before upgrading. Its destination cannot be inferred safely during upload preparation.")
    invalid_folder = (
        op.get_bind()
        .execute(
            sa.text("""
        SELECT child.tag_id FROM tag child
        WHERE child.owner_id IS NULL OR child.owner_id = ''
           OR child.name IS NULL OR child.name = '' OR child.name LIKE '%/%'
           OR (child.path IS NOT NULL AND child.path <> '' AND NOT EXISTS (
               SELECT 1 FROM tag parent WHERE parent.owner_id = child.owner_id
               AND (CASE WHEN parent.path IS NULL OR parent.path = '' THEN parent.name
                    ELSE parent.path || '/' || parent.name END) = child.path
           )) LIMIT 1
    """)
        )
        .scalar()
    )
    if invalid_folder is not None:
        raise RuntimeError(f"Review folder {invalid_folder}: a canonical team, single-segment name and existing parent are required. No hierarchy is inferred.")
    op.add_column("tag", sa.Column("deletion_task_id", sa.String(), nullable=True))
    op.add_column("kf_task_run", sa.Column("folder_id", sa.String(), nullable=True))
    op.create_index("ix_kf_task_run_folder_id", "kf_task_run", ["folder_id"])


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM tag WHERE deletion_task_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Finish or resolve corpus deletions before downgrading.")
    op.drop_column("tag", "deletion_task_id")
    op.drop_index("ix_kf_task_run_folder_id", table_name="kf_task_run")
    op.drop_column("kf_task_run", "folder_id")
