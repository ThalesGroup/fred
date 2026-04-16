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

"""
SQLAlchemy ORM model for conversation history storage.

Why this module exists:
- the ``session_history`` table schema must be defined in ``fred-core`` so that
  both ``agentic-backend`` and ``fred-runtime`` pods share the same table layout
  without duplicating the DDL

How to use it:
- import ``SessionHistoryRow`` when building or querying the ``session_history``
  table through SQLAlchemy
- use ``PostgresHistoryStore`` (in ``postgres_history_store``) for all reads and
  writes; do not query ``SessionHistoryRow`` directly from application code

Example:
    from fred_core.history.history_models import SessionHistoryRow
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base, JsonColumn


class SessionHistoryRow(Base):
    """
    ORM model for the ``session_history`` table.

    Primary key: ``(session_id, user_id, rank)`` — one row per message, ordered
    by rank within a session.

    Why ``rank`` is part of the primary key:
    - upserts on ``(session_id, user_id, rank)`` are idempotent; retried writes
      from the same turn overwrite the same row rather than duplicating it

    Why ``exchange_id`` is stored:
    - groups all messages produced during a single user turn so analytics and
      the UI can reconstruct the turn boundary without scanning timestamps
    """

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
