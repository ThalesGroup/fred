# app/common/document_structures.py

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


class SourceType(str, Enum):
    PUSH = "push"
    PULL = "pull"


class ProcessingStage(str, Enum):
    RAW_AVAILABLE = "raw"  # raw file can be downloaded
    PREVIEW_READY = "preview"  # e.g., Markdown or DataFrame generated
    VECTORIZED = "vector"  # content chunked and embedded
    SQL_INDEXED = "sql"  # content indexed into SQL backend
    MCP_SYNCED = "mcp"  # content synced to external system


class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    CSV = "csv"
    MD = "md"
    HTML = "html"
    TXT = "txt"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class Identity(BaseModel):
    document_name: str = Field(..., description="Original file name incl. extension")
    document_uid: str = Field(..., description="Stable unique id across the system")
    title: Optional[str] = Field(None, description="Human-friendly title for UI")
    author: Optional[str] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    last_modified_by: Optional[str] = None

    @field_validator("created", "modified")
    @classmethod
    def _ensure_tz(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @property
    def stem(self) -> str:
        return Path(self.document_name).stem

    @property
    def suffix(self) -> str:
        return Path(self.document_name).suffix.lstrip(".").lower()


class SourceInfo(BaseModel):
    source_type: SourceType
    source_tag: Optional[str] = Field(None, description="Repository/connector id, e.g. 'uploads', 'github'")
    pull_location: Optional[str] = Field(None, description="Path or URI to the original pull file")

    retrievable: bool = Field(default=False, description="True if raw file can be re-fetched")
    date_added_to_kb: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="When the document was added to the system",
    )
    repository_web: Optional[AnyHttpUrl] = Field(  # AnyHttpUrl allows http/https + custom ports
        default=None, description="Web base of the repository, e.g. https://git/org/repo"
    )
    repo_ref: Optional[str] = Field(default=None, description="Commit SHA or branch used when pulling")
    file_path: Optional[str] = Field(default=None, description="Path within the repository (POSIX style)")


class FileInfo(BaseModel):
    file_type: FileType = FileType.OTHER
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None  # PDFs/slides
    row_count: Optional[int] = None  # tables/csv
    sha256: Optional[str] = None
    md5: Optional[str] = None
    language: Optional[str] = None  # ISO code like 'fr', 'en'

    @model_validator(mode="after")
    def infer_file_type(self):
        # keep existing value if set; otherwise try to infer from mime
        if self.file_type == FileType.OTHER and self.mime_type:
            if "pdf" in self.mime_type:
                self.file_type = FileType.PDF
            elif "word" in self.mime_type or "docx" in self.mime_type:
                self.file_type = FileType.DOCX
            elif "powerpoint" in self.mime_type or "ppt" in self.mime_type:
                self.file_type = FileType.PPTX
            elif "excel" in self.mime_type or "spreadsheet" in self.mime_type or "xlsx" in self.mime_type:
                self.file_type = FileType.XLSX
            elif "csv" in self.mime_type:
                self.file_type = FileType.CSV
            elif "markdown" in self.mime_type:
                self.file_type = FileType.MD
            elif "html" in self.mime_type:
                self.file_type = FileType.HTML
            elif "text" in self.mime_type:
                self.file_type = FileType.TXT
        return self


class Tagging(BaseModel):
    """
    REBAC-ready: store stable tag ids and display names.
    Optionally store one canonical breadcrumb path for the UI.
    """

    tag_ids: List[str] = Field(default_factory=list, description="Stable tag IDs (UUIDs)")
    tag_names: List[str] = Field(default_factory=list, description="Display names for chips")

    @field_validator("tag_ids", "tag_names")
    @classmethod
    def dedupe_lists(cls, v: List[str]) -> List[str]:
        # preserve order while deduping
        seen: Set[str] = set()
        out: List[str] = []
        for x in v:
            if x and x not in seen:
                out.append(x)
                seen.add(x)
        return out


class AccessInfo(BaseModel):
    license: Optional[str] = None
    confidential: bool = False
    # Future pre-filter for search: principals that can read this doc (user:alice, role:admin)
    acl: List[str] = Field(default_factory=list)


class Processing(BaseModel):
    """Typed processing status per stage (+ optional error messages)."""

    stages: Dict[ProcessingStage, ProcessingStatus] = Field(default_factory=dict)
    errors: Dict[ProcessingStage, str] = Field(default_factory=dict)

    def mark_done(self, stage: ProcessingStage) -> None:
        self.stages[stage] = ProcessingStatus.DONE
        self.errors.pop(stage, None)

    def mark_error(self, stage: ProcessingStage, msg: str) -> None:
        self.stages[stage] = ProcessingStatus.FAILED
        self.errors[stage] = msg

    def set_status(self, stage: ProcessingStage, status: ProcessingStatus) -> None:
        self.stages[stage] = status

    def is_fully_processed(self) -> bool:
        return all(v == ProcessingStatus.DONE for v in self.stages.values())


class DocumentMetadata(BaseModel):
    # === Core ===
    identity: Identity
    source: SourceInfo
    file: FileInfo = Field(default_factory=FileInfo)

    # === Business & Access ===
    tags: Tagging = Field(default_factory=Tagging)
    access: AccessInfo = Field(default_factory=AccessInfo)

    # === Processing ===
    processing: Processing = Field(default_factory=Processing)

    # === Optional UX links ===
    preview_url: Optional[str] = None
    viewer_url: Optional[str] = None

    extensions: Optional[Dict[str, Any]] = Field(default=None, description="Processor-specific additional attributes (namespaced keys).")

    # ---- Convenience passthroughs (compat with v1) ----
    @property
    def document_name(self) -> str:
        return self.identity.document_name

    @property
    def document_uid(self) -> str:
        return self.identity.document_uid

    @property
    def title(self) -> Optional[str]:
        return self.identity.title

    @property
    def author(self) -> Optional[str]:
        return self.identity.author

    @property
    def created(self) -> Optional[datetime]:
        return self.identity.created

    @property
    def modified(self) -> Optional[datetime]:
        return self.identity.modified

    @property
    def last_modified_by(self) -> Optional[str]:
        return self.identity.last_modified_by

    @property
    def date_added_to_kb(self) -> datetime:
        return self.source.date_added_to_kb

    @property
    def source_tag(self) -> Optional[str]:
        return self.source.source_tag

    @property
    def pull_location(self) -> Optional[str]:
        return self.source.pull_location

    @property
    def source_type(self) -> SourceType:
        return self.source.source_type

    @property
    def retrievable(self) -> bool:
        return self.source.retrievable

    # ---- Small helpers ----
    def mark_stage_done(self, stage: ProcessingStage) -> None:
        self.processing.mark_done(stage)

    def mark_retrievable(self) -> None:
        self.source.retrievable = True

    def mark_unretrievable(self) -> None:
        self.source.retrievable = False

    def mark_stage_error(self, stage: ProcessingStage, error_msg: str) -> None:
        self.processing.mark_error(stage, error_msg)

    def set_stage_status(self, stage: ProcessingStage, status: ProcessingStatus) -> None:
        self.processing.set_status(stage, status)

    def is_fully_processed(self) -> bool:
        return self.processing.is_fully_processed()
