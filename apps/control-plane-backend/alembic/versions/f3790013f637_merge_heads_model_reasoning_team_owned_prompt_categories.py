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

"""merge heads: model reasoning + team-owned prompt categories

Revision ID: f3790013f637
Revises: d8e4f7a2c1b9, 8ca7cafc292f
Create Date: 2026-08-01 09:05:10.182240

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f3790013f637"
down_revision: Union[str, Sequence[str], None] = ("d8e4f7a2c1b9", "8ca7cafc292f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
