# Copyright Thales 2025
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

from __future__ import annotations

from fred_core.models.base import JsonColumn
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from agentic_backend.models.base import Base


class McpServerRow(Base):
    """ORM model for the ``mcp-server`` table.

    Each row stores a serialised :class:`~agentic_backend.core.agents.agent_spec.MCPServerConfiguration`
    payload in ``payload_json``.
    """

    __tablename__ = "mcp-server"

    server_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload_json: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
