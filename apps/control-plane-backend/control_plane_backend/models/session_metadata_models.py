from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class SessionMetadataRow(Base):
    """ORM model for the ``session_metadata`` table.

    Stores control-plane-owned session metadata records.
    Runtime message history stays in fred-runtime (session_history table).
    session_id is frontend-generated; control-plane never mints it.
    """

    __tablename__ = "session_metadata"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent_instance_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    # Captured once at create_session from the (then-live) agent instance's
    # source_runtime_id — immutable, config-level runtime catalog key. Lets
    # erasure resolve the owning runtime even after agent_instance_id's row is
    # later deleted (issue #2089, FRED-2.0.2-RGPD-READY-RFC §7). NULL for rows
    # created before this column existed.
    source_runtime_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    # Soft-hide marker for the deferred delete window (CTRLP-12 A5). When set,
    # the conversation is hidden from the sidebar/team list but its row and
    # history survive until the lifecycle erases it at window expiry. NULL for
    # live conversations. Set by `SessionMetadataStore.mark_deleted`.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SessionContextPromptRow(Base):
    """ORM model for the ``session_context_prompts`` association table.

    Ordered many-to-many between a session and the prompt-library prompts a user
    has attached as chat context (PROMPT-05 / PROMPTS.md §5). Replaces the scalar
    ``session_metadata.context_prompt_id`` so a conversation can carry 0, 1, or
    many prompts, concatenated in ``position`` order at execution time.

    ``prompt_id`` is a prompt UUID or a synthetic ``default:{category}`` id for
    platform defaults; it is intentionally not a foreign key so a deleted prompt
    never breaks an open conversation (stale ids are skipped at resolution).
    """

    __tablename__ = "session_context_prompts"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("session_metadata.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    prompt_id: Mapped[str] = mapped_column(String, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
