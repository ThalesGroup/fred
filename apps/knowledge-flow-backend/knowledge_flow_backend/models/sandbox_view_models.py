# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Short-lived source bindings for a conversation's mounted sandbox view."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from knowledge_flow_backend.models.base import Base


class SandboxViewRow(Base):
    __tablename__ = "sandbox_file_views"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    team_id: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sources: Mapped[dict[str, dict[str, str | int]]] = mapped_column(JSON, nullable=False, default=dict)
    bytes_served: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_window_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SandboxAttachmentOriginalRow(Base):
    __tablename__ = "sandbox_attachment_originals"

    document_uid: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(String, nullable=False)
