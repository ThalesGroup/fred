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

"""merge heads: team routing policy + team visibility/joining-mode

Revision ID: 8b8e6a86022a
Revises: 8092a626d4d0, bc06439e4cf9
Create Date: 2026-07-27 06:05:56.424527

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "8b8e6a86022a"
down_revision: Union[str, Sequence[str], None] = ("8092a626d4d0", "bc06439e4cf9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
