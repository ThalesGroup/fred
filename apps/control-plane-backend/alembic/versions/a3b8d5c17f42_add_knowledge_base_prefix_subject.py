"""record the subject a publishing client authenticates as

Revision ID: a3b8d5c17f42
Revises: c1e4f70a2b95
Create Date: 2026-09-13

A prefix is bound to a client (`azp`), which is what a later publication is
checked against. A grant, though, names an account (`sub`) — a relation's
subject is never a client. Both travel on the token that authorizes a
publication, so the second is recorded here and creating an instance never has
to ask Keycloak's admin API which account backs a client.

Nullable: a prefix claimed before this column existed keeps working, and the
next publication under it fills the subject in.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b8d5c17f42"  # pragma: allowlist secret
down_revision: Union[str, None] = "c1e4f70a2b95"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base_prefixes",
        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=True,
            comment=(
                "Service account the claiming client authenticates as (`sub`). "
                "The client is what a prefix is bound to; this is the only one "
                "of the two the authorization engine can be told to grant, so "
                "creating an instance reads it here instead of asking "
                "Keycloak's admin API which account backs a client. Nullable "
                "for prefixes claimed before it was recorded; the next "
                "publication fills it in."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_base_prefixes", "subject")
