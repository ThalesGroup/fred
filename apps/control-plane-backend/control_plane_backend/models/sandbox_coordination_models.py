# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Broker-owned conversation and wait state registered for migration checks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base


class SandboxConversationLeaseRow(Base):
    __tablename__ = "sandbox_conversation_leases"
    __table_args__ = (
        CheckConstraint(
            "state IN ('new','preparing','running','suspending','suspended','resuming','deleting')",
            name="ck_sandbox_conversation_state",
        ),
        Index("ix_sandbox_conversation_state_updated", "state", "updated_at"),
        Index("ix_sandbox_conversation_last_used", "last_used_at"),
    )

    session_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    view_epoch: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(63))
    owner_token: Mapped[str | None] = mapped_column(String(32))
    owner_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SandboxWaitTicketRow(Base):
    __tablename__ = "sandbox_wait_tickets"
    __table_args__ = (
        Index("ix_sandbox_wait_order", "created_at", "id"),
        Index("ix_sandbox_wait_tenant", "tenant_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sandbox_conversation_leases.session_key", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
