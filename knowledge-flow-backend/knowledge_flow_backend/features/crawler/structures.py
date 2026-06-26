from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


def utc_now() -> datetime:
    """
    Return a timezone-aware UTC timestamp for crawler records.

    Why this exists:
    - crawler persistence stores timestamps from API handlers, background tasks,
      and Temporal activities, so every caller needs one consistent clock shape.

    How to use:
    - call when creating or updating crawler models.

    Example:
    - `run.started_at = utc_now()`
    """
    return datetime.now(timezone.utc)


class CrawlStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CrawlUrlStatus(str, Enum):
    PENDING = "pending"
    RESERVED = "reserved"
    FETCHED = "fetched"
    EXTRACTED = "extracted"
    SKIPPED = "skipped"
    FAILED = "failed"


class ProcessingProfile(str, Enum):
    FAST = "fast"
    MEDIUM = "medium"
    RICH = "rich"


class CrawlSource(BaseModel):
    id: str
    workspace_id: str
    name: str
    seed_urls: list[str]
    allowed_domains: list[str]
    max_depth: int = Field(ge=0, le=10)
    max_pages: int = Field(ge=1, le=10000)
    restrict_to_domain: bool = True
    respect_robots_txt: bool = True
    status: CrawlStatus = CrawlStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)


class CrawlRun(BaseModel):
    id: str
    source_id: str
    status: CrawlStatus = CrawlStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    discovered_count: int = 0
    fetched_count: int = 0
    extracted_count: int = 0
    failed_count: int = 0
    document_uids: list[str] = Field(default_factory=list)
    error: str | None = None


class CrawlUrl(BaseModel):
    id: str
    run_id: str
    normalized_url: str
    original_url: str
    parent_url: str | None = None
    depth: int = 0
    status: CrawlUrlStatus = CrawlUrlStatus.PENDING
    retry_count: int = 0
    next_eligible_at: datetime = Field(default_factory=utc_now)
    content_fingerprint: str | None = None
    error: str | None = None


class CrawlPageVersion(BaseModel):
    id: str
    run_id: str
    normalized_url: str
    content_hash: str
    markdown: str
    extracted_text: str
    fetched_at: datetime = Field(default_factory=utc_now)
    title: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    document_uid: str | None = None


class CrawlSiteRequest(BaseModel):
    site_url: HttpUrl
    directory_name: str = Field(min_length=1, max_length=120)
    processing_profile: ProcessingProfile = ProcessingProfile.FAST
    max_depth: int = Field(default=2, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=10000)
    restrict_to_domain: bool = True
    respect_robots_txt: bool = True

    @field_validator("directory_name")
    @classmethod
    def normalize_directory_name(cls, value: str) -> str:
        """
        Normalize user-provided crawler directory names.

        Why this exists:
        - document libraries are tag paths, and blank or slash-heavy names create
          confusing folder trees.

        How to use:
        - Pydantic calls this automatically for `CrawlSiteRequest`.
        """
        normalized = " ".join(value.strip().split())
        if "/" in normalized or "\\" in normalized:
            raise ValueError("Directory name cannot contain path separators")
        return normalized


class CrawlSiteResponse(BaseModel):
    resource: dict
    run: CrawlRun


class CrawlRunStatusResponse(BaseModel):
    run: CrawlRun
    ui_status: Literal["Crawling in progress", "Ready", "Failed"]
