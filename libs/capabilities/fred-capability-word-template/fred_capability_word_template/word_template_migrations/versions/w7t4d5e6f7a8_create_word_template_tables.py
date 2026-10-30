# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""create the word_template capability's tables

The session's base, its operation log (each batch authored ``model`` or
``collaborator``), the template analysis cache, the session document snapshot
(a replay cache), the Word files and images attached in the session.
Prefixed `cap_word_template_`, no foreign keys.

Revision ID: w7t4d5e6f7a8
Revises:
Create Date: 2026-10-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w7t4d5e6f7a8"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cap_word_template_sessions",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("team_id", sa.String(length=128), nullable=True),
        sa.Column("agent_instance_id", sa.String(length=128), nullable=True),
        sa.Column("template_key", sa.String(length=255), nullable=True),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attachment_id", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "cap_word_template_batches",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("operations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "author", sa.String(length=16), nullable=False, server_default="model"
        ),
        sa.PrimaryKeyConstraint("session_id", "seq"),
    )
    op.create_table(
        "cap_word_template_analyses",
        sa.Column("template_key", sa.String(length=255), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("template_key"),
    )
    op.create_table(
        "cap_word_template_snapshots",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("docx", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "cap_word_template_attachments",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("attachment_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "images_extracted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.PrimaryKeyConstraint("session_id", "attachment_id"),
        sa.UniqueConstraint(
            "session_id", "sha256", name="uq_cap_word_template_attachments_sha256"
        ),
    )
    op.create_table(
        "cap_word_template_images",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("image_id", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=True),
        sa.Column("source_attachment_id", sa.String(length=32), nullable=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "image_id"),
        sa.UniqueConstraint(
            "session_id", "sha256", name="uq_cap_word_template_images_sha256"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cap_word_template_images")
    op.drop_table("cap_word_template_attachments")
    op.drop_table("cap_word_template_snapshots")
    op.drop_table("cap_word_template_analyses")
    op.drop_table("cap_word_template_batches")
    op.drop_table("cap_word_template_sessions")
