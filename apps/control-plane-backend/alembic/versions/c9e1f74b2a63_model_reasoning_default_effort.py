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

"""model_reasoning: snapshot the model's ops-authored reasoning effort

The composer's reasoning menu shows the level a reasoning turn actually runs
with (the thinking profile's own `settings.reasoning_effort` — the single
source of truth, no separate supported-efforts declaration; review
2026-08-12). The send path deliberately performs no catalog fetch, so the
value is snapshotted here when an admin (re-)toggles the model's reasoning
and served on the reasoning control's `params.effort`. NULL = the profile
ships no effort key (the menu falls back to a generic On label). Display
only — the pod always applies the live settings value.

Revision ID: c9e1f74b2a63
Revises: f3790013f637
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e1f74b2a63"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f3790013f637"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "model_reasoning",
        sa.Column(
            "default_effort",
            sa.String(),
            nullable=True,
            comment=(
                "The model's ops-authored settings.reasoning_effort, "
                "snapshotted from the catalog entry when reasoning was "
                "(re-)toggled. NULL = no effort key on the thinking profile."
            ),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("model_reasoning", "default_effort")
