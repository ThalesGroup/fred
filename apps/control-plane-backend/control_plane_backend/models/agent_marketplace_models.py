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

"""Agents marketplace: one entry per published agent, its snapshot files, and
dated likes and imports kept across removal and republication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

AGENT_MARKETPLACE_ACTIVE_LIKE_INDEX = "uq_agent_marketplace_like_active"


class AgentMarketplaceEntryRow(Base):
    """ORM model for the ``agent_marketplace_entry`` table.

    `state` is `published`, `removed` (automatic or platform admin removal,
    shown on the team card) or `dismissed` (removed by the team or hidden).
    """

    __tablename__ = "agent_marketplace_entry"

    entry_id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_instance_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_instance.agent_instance_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    removed_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    removed_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    template_id: Mapped[str] = mapped_column(String, nullable=False)
    source_runtime_id: Mapped[str] = mapped_column(String, nullable=False)
    source_agent_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tuning_json: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    first_published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    snapshot_source_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AgentMarketplaceEntryFileRow(Base):
    """ORM model for ``agent_marketplace_entry_file``: one configuration file of
    the snapshot, keyed by capability and asset key."""

    __tablename__ = "agent_marketplace_entry_file"

    entry_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_marketplace_entry.entry_id", ondelete="CASCADE"),
        primary_key=True,
    )
    capability_id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_key: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class AgentMarketplaceLikeRow(Base):
    """ORM model for ``agent_marketplace_like``: an unlike sets `removed_at`,
    a new like inserts a new row, so the history stays."""

    __tablename__ = "agent_marketplace_like"

    like_id: Mapped[str] = mapped_column(String, primary_key=True)
    entry_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_marketplace_entry.entry_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# One active like per user and entry.
Index(
    AGENT_MARKETPLACE_ACTIVE_LIKE_INDEX,
    AgentMarketplaceLikeRow.entry_id,
    AgentMarketplaceLikeRow.user_id,
    unique=True,
    postgresql_where=text("removed_at IS NULL"),
    sqlite_where=text("removed_at IS NULL"),
)


class AgentMarketplaceImportRow(Base):
    """ORM model for ``agent_marketplace_import``: one row per destination that
    received a copy; the resulting agent is kept while it exists."""

    __tablename__ = "agent_marketplace_import"

    import_id: Mapped[str] = mapped_column(String, primary_key=True)
    entry_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_marketplace_entry.entry_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_team_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_instance_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("agent_instance.agent_instance_id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
