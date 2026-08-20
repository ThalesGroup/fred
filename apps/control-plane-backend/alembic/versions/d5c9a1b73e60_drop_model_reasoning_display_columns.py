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

"""model_reasoning: drop the two display-only columns (#2387)

`default_effort` (c9e1f74b2a63) and `display_name` (a7d2e9c41f38) both existed
to feed the composer's reasoning chip. #2387 removed that whole display chain:
the chip now reads its model identity from the routing resolver and its state
as two modes (Rapide / Boost), so neither column has a reader left. They are
not on `ModelReasoningRow`, so leaving them would keep `alembic check` red.

Why the two revisions above are kept rather than deleted along with their
columns: `code/v2.1.35` shipped with `a7d2e9c41f38` as its head, so every
deployment running that release has exactly that id in
`alembic_version_control_plane`. Deleting the file makes the id unresolvable
and alembic refuses to start — it cannot place itself in the graph, so it
cannot move forward either. The columns are removed here, at the head, where
every deployment reaches them by walking forward normally.

Conditional on both sides because the graph now has two kinds of database
behind it. One came through v2.1.35 and has the columns; one was migrated from
a `swift` checkout taken while these revisions were briefly absent, is stamped
at `552d32c2b935`, and never had them. Both must land on the same schema.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5c9a1b73e60"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "552d32c2b935"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "model_reasoning"


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Upgrade schema."""
    present = _existing_columns()
    for column in ("display_name", "default_effort"):
        if column in present:
            op.drop_column(_TABLE, column)


def downgrade() -> None:
    """Downgrade schema."""
    present = _existing_columns()
    if not present:
        return
    if "default_effort" not in present:
        op.add_column(
            _TABLE,
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
    if "display_name" not in present:
        op.add_column(
            _TABLE,
            sa.Column(
                "display_name",
                sa.String(),
                nullable=True,
                comment=(
                    "The model's ops-authored model_display_name, snapshotted "
                    "from the catalog entry when reasoning was (re-)toggled. "
                    "NULL = no display name authored in models_catalog.yaml."
                ),
            ),
        )
