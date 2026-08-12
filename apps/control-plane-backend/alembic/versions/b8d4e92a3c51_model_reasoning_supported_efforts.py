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

"""model_reasoning: snapshot the provider-accepted reasoning efforts

Level 4b (per-question effort picker): the composer needs the list of
`reasoning_effort` values a model's provider actually accepts (measured:
Mistral small rejects low/medium with a 400), and the send path deliberately
performs no catalog fetch — so the list is SNAPSHOTTED from the catalog entry
at the moment an admin enables the model's reasoning, and served on the
reasoning control's `params.efforts`. NULL = not declared ("unknown, don't
narrow"); existing rows stay NULL until the next admin re-toggle, which is the
documented refresh path. The pod-side clamp is the enforcement either way.

Revision ID: b8d4e92a3c51
Revises: f3790013f637
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8d4e92a3c51"  # pragma: allowlist secret
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
            "supported_efforts_json",
            sa.Text(),
            nullable=True,
            comment=(
                "JSON array of the reasoning_effort values this model's "
                "provider accepts (level 4b), snapshotted from the catalog "
                "entry when reasoning was enabled. NULL = not declared "
                "('unknown, don't narrow')."
            ),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("model_reasoning", "supported_efforts_json")
