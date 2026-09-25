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

"""merge heads: platform bootstrap + capability system

Revision ID: 37f6de4ac781
Revises: 6e4149d46705, 7fb19a619b0e
Create Date: 2026-07-17 05:21:04.073388

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "37f6de4ac781"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = ("6e4149d46705", "7fb19a619b0e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
