from __future__ import annotations

from datetime import datetime

from fred_core.models.base import JsonColumn, TimestampColumn
from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from knowledge_flow_backend.models.base import Base


class CrawlSourceRow(Base):
    """ORM row for one configured website crawl source."""

    __tablename__ = "crawl_source"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TimestampColumn, nullable=False)
    doc: Mapped[dict] = mapped_column(JsonColumn, nullable=False)


class CrawlRunRow(Base):
    """ORM row for one execution of a crawl source."""

    __tablename__ = "crawl_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, index=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    doc: Mapped[dict] = mapped_column(JsonColumn, nullable=False)


class CrawlUrlRow(Base):
    """ORM row for the persistent crawl frontier."""

    __tablename__ = "crawl_url"
    __table_args__ = (UniqueConstraint("run_id", "normalized_url", name="uq_crawl_url_run_url"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    normalized_url: Mapped[str] = mapped_column(String, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, index=True, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_eligible_at: Mapped[datetime] = mapped_column(TimestampColumn, index=True, nullable=False)
    doc: Mapped[dict] = mapped_column(JsonColumn, nullable=False)


class CrawlPageVersionRow(Base):
    """ORM row for extracted page content versions."""

    __tablename__ = "crawl_page_version"
    __table_args__ = (UniqueConstraint("normalized_url", "content_hash", name="uq_crawl_page_version_url_hash"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    normalized_url: Mapped[str] = mapped_column(String, index=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, index=True, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(TimestampColumn, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict] = mapped_column(JsonColumn, nullable=False)
