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

"""model_reasoning: snapshot the model's ops-authored display name

Ops now name each model in `models_catalog.yaml` (`model_display_name`)
instead of leaving the composer chip to derive a label by splitting the
capability id apart. The send path performs no catalog fetch, so the value is
snapshotted here when an admin (re-)toggles the model's reasoning — same
lifecycle and rationale as `default_effort` (c9e1f74b2a63). NULL = unnamed,
and the frontend falls back to the heuristic. Display only.

Revision ID: a7d2e9c41f38
Revises: c9e1f74b2a63
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d2e9c41f38"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c9e1f74b2a63"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "model_reasoning",
        sa.Column(
            "display_name",
            sa.String(),
            nullable=True,
            comment=(
                "The model's ops-authored model_display_name, snapshotted from "
                "the catalog entry when reasoning was (re-)toggled. NULL = no "
                "display name authored in models_catalog.yaml."
            ),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("model_reasoning", "display_name")
