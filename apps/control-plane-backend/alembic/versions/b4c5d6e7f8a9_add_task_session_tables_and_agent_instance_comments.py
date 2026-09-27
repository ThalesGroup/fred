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

"""merge heads: agent_instance comments + task/session tables

Revision ID: b4c5d6e7f8a9
Revises: a2b3c4d5e6f7, a3b4c5d6e7f8
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a2b3c4d5e6f7",  # pragma: allowlist secret
    "a3b4c5d6e7f8",  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
