"""Introduce the default organization without changing existing resource identities."""

import sqlalchemy as sa
from alembic import op

revision = "c01d28000001"
down_revision = "a3f7c9e2d514"
branch_labels = None
depends_on = None


def upgrade():
    """Preserve existing teams and the saved prompt under stable organization fred."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column(
            "admin_migration_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute("INSERT INTO organizations (id, name) VALUES ('fred', 'Fred')")
    with op.batch_alter_table("teammetadata") as batch:
        batch.add_column(
            sa.Column(
                "organization_id", sa.String(180), nullable=False, server_default="fred"
            )
        )
        batch.create_index("ix_teammetadata_organization_id", ["organization_id"])
        batch.create_foreign_key(
            "fk_teammetadata_organization", "organizations", ["organization_id"], ["id"]
        )
    with op.batch_alter_table("platform_prompt") as batch:
        batch.drop_constraint("ck_platform_prompt_singleton", type_="check")
    op.execute("UPDATE platform_prompt SET id = 'fred' WHERE id = 'default'")
    with op.batch_alter_table("platform_prompt") as batch:
        batch.create_foreign_key(
            "fk_platform_prompt_organization", "organizations", ["id"], ["id"]
        )


def downgrade():
    """Refuse destructive rollback after additional organizations have been introduced."""
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT count(*) FROM organizations WHERE id <> 'fred'")
    ).scalar():
        raise RuntimeError("Remove additional organizations before downgrading")
    with op.batch_alter_table("platform_prompt") as batch:
        batch.drop_constraint("fk_platform_prompt_organization", type_="foreignkey")
    op.execute("UPDATE platform_prompt SET id = 'default' WHERE id = 'fred'")
    with op.batch_alter_table("platform_prompt") as batch:
        batch.create_check_constraint("ck_platform_prompt_singleton", "id = 'default'")
    with op.batch_alter_table("teammetadata") as batch:
        batch.drop_constraint("fk_teammetadata_organization", type_="foreignkey")
        batch.drop_index("ix_teammetadata_organization_id")
        batch.drop_column("organization_id")
    op.drop_table("organizations")
