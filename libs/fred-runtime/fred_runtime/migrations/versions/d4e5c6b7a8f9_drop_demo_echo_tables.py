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

"""drop the retired demo capability's tables

The demo capability was a tracer, shipped as a real entry point: every pod
that ever ran migrations holds its table and its own version row. Retiring
the capability deletes its migration tree, which would leave both behind, so
this revision drops them from the runtime tree instead.

`IF EXISTS` because this also runs on databases that never had them — a fresh
install applies this revision before any capability tree would have created
anything.

Revision ID: d4e5c6b7a8f9
Revises: c3d4b5a6f7e8
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5c6b7a8f9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c3d4b5a6f7e8"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cap_demo_echo_notes")
    op.execute("DROP TABLE IF EXISTS cap_demo_echo_alembic_version")


def downgrade() -> None:
    """No-op: the capability that owned these tables no longer exists, so there
    is no schema to restore them for."""
