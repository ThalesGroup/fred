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

from datetime import datetime

from fred_core.models.base import JsonColumn
from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agentic_backend.models.base import Base


class SessionHistoryRow(Base):
    """ORM model for the ``session_history`` table."""

    __tablename__ = "session_history"

    __table_args__ = (Index("ix_session_history_timestamp", "timestamp"),)

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    exchange_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parts_json: Mapped[list | None] = mapped_column(JsonColumn, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
