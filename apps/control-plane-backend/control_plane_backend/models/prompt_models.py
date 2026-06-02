from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import PrimaryKeyConstraint

from control_plane_backend.models.base import Base, utcnow


class PromptRow(Base):
    """ORM model for the ``prompt`` table.

    Stores control-plane prompt-library records scoped to one team, including
    the reserved ``personal`` team.
    """

    __tablename__ = "prompt"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_prompt_team_name"),)

    prompt_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emoji: Mapped[str | None] = mapped_column(String(8), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    import_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class DefaultPromptUsageRow(Base):
    """Usage counter for immutable platform-default prompts.

    Default prompts are never stored in the ``prompt`` table (they are generated
    at query time from in-memory specs), so their session_count cannot be tracked
    in PromptRow. This table stores one counter per (team, category) pair and is
    incremented atomically whenever a user activates a default prompt as their
    chat context.

    Primary key: (team_id, category) — one row per default prompt per team.
    """

    __tablename__ = "default_prompt_usage"
    __table_args__ = (PrimaryKeyConstraint("team_id", "category"),)

    team_id: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
