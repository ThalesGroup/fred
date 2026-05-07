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

from typing import Any

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base, JsonColumn
from fred_core.sql.mixin import TimestampMixin


class SessionRow(Base, TimestampMixin):
    """ORM model for the ``session`` table.

    Schema matches the existing table created by the legacy PostgresJsonSessionStore.
    The ``session_data`` JSONB column stores the full ``SessionSchema`` payload.
    Future migrations will decompose it into typed columns.
    """

    __tablename__ = "session"
    __table_args__ = (Index("ix_session_updated_at", "updated_at"),)

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    team_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    session_data: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn,
        nullable=False,
    )
