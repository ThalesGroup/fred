# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Durable, capability-neutral inputs and preparation state."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class CapabilityAssetRow(Base):
    __tablename__ = "capability_asset"
    __table_args__ = (
        CheckConstraint(
            "owner_kind in ('agent', 'platform', 'draft')", name="ck_cap_asset_owner"
        ),
        CheckConstraint(
            "(owner_kind in ('agent', 'draft') and team_id is not null) or "
            "(owner_kind = 'platform' and team_id is null)",
            name="ck_cap_asset_team",
        ),
        CheckConstraint("state in ('stored', 'retired')", name="ck_cap_asset_state"),
        CheckConstraint("size >= 0 and size <= 67108864", name="ck_cap_asset_size"),
        UniqueConstraint("object_key", name="uq_cap_asset_object_key"),
        Index("ix_cap_asset_owner", "owner_kind", "owner_id", "capability_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(255))
    runtime_id: Mapped[str] = mapped_column(String(255), nullable=False)
    capability_id: Mapped[str] = mapped_column(String(255), nullable=False)
    slot_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="stored")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CapabilityPreparationRow(Base):
    __tablename__ = "capability_preparation"
    __table_args__ = (
        CheckConstraint(
            "owner_kind in ('agent', 'platform', 'draft')", name="ck_cap_prep_owner"
        ),
        CheckConstraint(
            "(owner_kind in ('agent', 'draft') and team_id is not null) or "
            "(owner_kind = 'platform' and team_id is null)",
            name="ck_cap_prep_team",
        ),
        CheckConstraint(
            "state in ('pending', 'running', 'succeeded', 'failed', 'obsolete')",
            name="ck_cap_prep_state",
        ),
        CheckConstraint(
            "attempts >= 0 and attempts <= max_attempts", name="ck_cap_prep_attempts"
        ),
        CheckConstraint(
            "max_attempts between 1 and 10", name="ck_cap_prep_max_attempts"
        ),
        CheckConstraint(
            "dispatch_attempts between 0 and 10", name="ck_cap_prep_dispatch_attempts"
        ),
        CheckConstraint(
            "not (is_current and state = 'obsolete')", name="ck_cap_prep_current"
        ),
        UniqueConstraint(
            "owner_kind",
            "owner_id",
            "capability_id",
            "input_revision",
            "rules_version",
            name="uq_cap_prep_revision",
        ),
        UniqueConstraint("workflow_id", name="uq_cap_prep_workflow"),
        Index(
            "uq_cap_prep_current_owner",
            "owner_kind",
            "owner_id",
            "capability_id",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current"),
        ),
        Index("ix_cap_prep_due", "state", "delivery_due_at", "id"),
        Index("ix_cap_prep_readiness", "owner_kind", "owner_id", "is_current", "state"),
        Index(
            "ix_cap_prep_draft_expiry",
            "runtime_id",
            "owner_kind",
            "draft_expires_at",
            "id",
        ),
        Index(
            "ix_cap_prep_draft_author",
            "team_id",
            "draft_author_id",
            "owner_kind",
            "is_current",
        ),
        Index(
            "ix_cap_prep_cleanup",
            "runtime_id",
            "is_current",
            "cleaned_at",
            "superseded_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(255))
    draft_author_id: Mapped[str | None] = mapped_column(String(255))
    draft_target_id: Mapped[str | None] = mapped_column(String(512))
    draft_generation: Mapped[int | None] = mapped_column(Integer)
    draft_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runtime_id: Mapped[str] = mapped_column(String(255), nullable=False)
    capability_id: Mapped[str] = mapped_column(String(255), nullable=False)
    input_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    public_config_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    gates_readiness: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    dispatch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workflow_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_queue: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_token: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid4())
    )
    run_id: Mapped[str | None] = mapped_column(String(255))
    delivery_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    dispatch_owner: Mapped[str | None] = mapped_column(String(36))
    dispatch_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_reference: Mapped[str | None] = mapped_column(String(512))
    result_summary: Mapped[str | None] = mapped_column(String(2000))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CapabilityPreparationAssetRow(Base):
    __tablename__ = "capability_preparation_asset"
    __table_args__ = (
        UniqueConstraint("preparation_id", "asset_id", name="uq_cap_prep_asset_once"),
        Index("ix_cap_prep_asset_asset", "asset_id"),
    )

    preparation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("capability_preparation.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("capability_asset.id", ondelete="RESTRICT"),
        nullable=False,
    )


class CapabilityPlatformSelectionRow(Base):
    __tablename__ = "capability_platform_selection"
    __table_args__ = (Index("ix_cap_platform_candidate", "candidate_preparation_id"),)

    runtime_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    capability_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    slot_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    active_preparation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("capability_preparation.id")
    )
    candidate_preparation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("capability_preparation.id")
    )
    settings_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
