# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Corpus folders classify documents within one canonical owning space."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base, TimestampColumn


class CorpusFolderRow(Base):
    __tablename__ = "corpus_folder"
    __table_args__ = (
        UniqueConstraint("id", "space_id", name="uq_corpus_folder_id_space"),
        UniqueConstraint(
            "space_id", "parent_id", "name", name="uq_corpus_folder_sibling_name"
        ),
        ForeignKeyConstraint(
            ["parent_id", "space_id"],
            ["corpus_folder.id", "corpus_folder.space_id"],
            name="fk_corpus_folder_parent_space",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_corpus_folder_parent"
        ),
        CheckConstraint(
            "length(name) > 0 AND name = trim(name) AND name NOT LIKE '%/%' AND name NOT LIKE '%\\%' ESCAPE '!'",
            name="ck_corpus_folder_name",
        ),
        CheckConstraint(
            "parent_id IS NULL OR (source_version IS NULL AND synchronized_by IS NULL)",
            name="ck_corpus_folder_root_source",
        ),
        Index(
            "uq_corpus_folder_root_name",
            "space_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
            sqlite_where=text("parent_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    space_id: Mapped[str] = mapped_column(
        String, ForeignKey("space.id", name="fk_corpus_folder_space")
    )
    parent_id: Mapped[str | None] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn, server_default=func.now()
    )
    source_version: Mapped[str | None] = mapped_column(String)
    synchronized_by: Mapped[str | None] = mapped_column(String)


class CorpusFolder(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    space_id: str
    parent_id: str | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    source_version: str | None
    synchronized_by: str | None
