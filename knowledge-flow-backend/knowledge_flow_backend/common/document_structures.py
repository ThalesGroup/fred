# Copyright Thales 2025
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


from __future__ import annotations

import re
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


class ReportFormat(str, Enum):
    """Reports only ever publish these concrete file types."""

    MD = FileType.MD.value
    HTML = FileType.HTML.value
    PDF = FileType.PDF.value

    @staticmethod
    def from_file_type(ft: FileType) -> "ReportFormat":
        if ft in (FileType.MD, FileType.HTML, FileType.PDF):
            return ReportFormat(ft.value)
        raise ValueError(f"Unsupported report format: {ft}")


class ProcessingStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class Identity(BaseModel):
    document_name: str = Field(..., description="Original file name incl. extension (display name)")
    document_uid: str = Field(..., description="Stable unique id across the system")
    canonical_name: Optional[str] = Field(
        default=None,
        description="Base file name without transient version suffix (e.g., 'report.docx' for 'report.docx (1)')",
    )
    version: int = Field(
        default=0,
        description="Version number within a folder/tag. 0 means canonical/original name, 1 -> 'name (1)', etc.",
        ge=0,
    )
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

    @model_validator(mode="after")
    def _set_canonical_defaults(self) -> "Identity":
        # Backfill canonical_name when missing for older records
        if not self.canonical_name:
            match = re.match(r"^(?P<base>.+)\s\((?P<version>\d+)\)$", self.document_name.strip())
            self.canonical_name = match.group("base") if match else self.document_name
        else:
            canon_match = re.match(r"^(?P<base>.+)\s\((?P<version>\d+)\)$", self.canonical_name.strip())
            if canon_match:
                self.canonical_name = canon_match.group("base")
        # Guard against negative versions
        if self.version is None or self.version < 0:
            self.version = 0
        return self

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


class ProcessingSummary(BaseModel):
    """
    Aggregate processing status across a set of documents.

    Intended for lightweight UI summaries (e.g. total vs processed vs in-progress).
    """

    total_documents: int
    fully_processed: int
    in_progress: int
    failed: int
    not_started: int


class ProcessingGraphNode(BaseModel):
    """
    Node in the processing graph, used to visualize how documents relate
    to downstream artifacts (tables, vector indexes, etc.).
    """

    id: str
    kind: str  # e.g. document, table, vector_index
    label: str

    # Optional metadata depending on node kind
    document_uid: Optional[str] = None
    table_name: Optional[str] = None
    vector_count: Optional[int] = None
    row_count: Optional[int] = None
    file_type: Optional[FileType] = None
    source_tag: Optional[str] = None
    version: Optional[int] = Field(
        default=None,
        description="Document version (0=base, 1=draft). Set only for document nodes.",
        ge=0,
    )


class ProcessingGraphEdge(BaseModel):
    """
    Directed edge between processing graph nodes.
    """

    source: str
    target: str
    kind: str  # e.g. vectorized, sql_indexed


class ProcessingGraph(BaseModel):
    """
    Lightweight graph structure that can be consumed directly by the UI
    to render a data lineage view (documents → tables / vectors).
    """

    nodes: List[ProcessingGraphNode]
    edges: List[ProcessingGraphEdge]


class DocSummary(BaseModel):
    """
    Fred rationale:
    - Store *document-level* summarization once (avoid chunk bloat).
    - Keep provenance to make results auditable and cache-bustable.
    - UI reads this to show 'Abstract' and 'Key terms' on demand.
    """

    abstract: Optional[str] = Field(default=None, description="Concise doc abstract for humans (UI).")
    keywords: Optional[List[str]] = Field(default=None, description="Top key terms for navigation and filters.")
    model_name: Optional[str] = Field(default=None, description="LLM/flow used to produce this summary.")
    method: Optional[str] = Field(default=None, description="Algorithm/flow id (e.g., 'SmartDocSummarizer@v1').")
    created_at: Optional[datetime] = Field(default=None, description="UTC when this summary was computed.")


class ReportExtensionV1(BaseModel):
    """
    Stored under DocumentMetadata.extensions["report"].

    Fred rationale:
    - Markdown is the canonical source of the report and MUST be persisted.
    - HTML/PDF are optional sync exports.
    - Keep v1 tiny and explicit; no revisions/status yet.
    """

    version: str = "v1"
    # Optional for traceability (which layout was used to assemble MD)
    template_id: Optional[str] = None

    # Canonical source (always present)
    md_url: str = Field(..., description="Public URL to the canonical Markdown file")
    md_type: FileType = Field(default=FileType.MD, description="Redundant but explicit typing")

    # Optional exports
    html_url: Optional[str] = Field(default=None, description="URL to rendered HTML, if built")
    pdf_url: Optional[str] = Field(default=None, description="URL to rendered PDF, if built")
    html_type: Optional[FileType] = Field(default=None, description="= FileType.HTML when html_url is set")
    pdf_type: Optional[FileType] = Field(default=None, description="= FileType.PDF when pdf_url is set")

    # Convenience (computed) – which formats are currently available
    @property
    def available_formats(self) -> List[ReportFormat]:
        out: List[ReportFormat] = [ReportFormat.MD]
        if self.html_url:
            out.append(ReportFormat.HTML)
        if self.pdf_url:
            out.append(ReportFormat.PDF)
        return out

    @model_validator(mode="after")
    def _enforce_types_match_urls(self) -> "ReportExtensionV1":
        # If a URL is present, enforce its FileType counterpart for clarity.
        if self.html_url and self.html_type not in (None, FileType.HTML):
            raise ValueError("html_type must be HTML when html_url is set")
        if self.pdf_url and self.pdf_type not in (None, FileType.PDF):
            raise ValueError("pdf_type must be PDF when pdf_url is set")
        # Ensure md_type stays MD
        if self.md_type != FileType.MD:
            raise ValueError("md_type must be MD")
        return self


class DocumentMetadata(BaseModel):
    # === Core ===
    identity: Identity
    source: SourceInfo
    file: FileInfo = Field(default_factory=FileInfo)

    # Optional summary produced by a summarization processor
    summary: Optional[DocSummary] = None

    # === Business & Access ===
    tags: Tagging = Field(default_factory=Tagging)
    access: AccessInfo = Field(default_factory=AccessInfo)

    # === Processing ===
    processing: Processing = Field(default_factory=Processing)

    # === Optional UX links ===
    preview_url: Optional[str] = None
    viewer_url: Optional[str] = None

    extensions: Optional[Dict[str, Any]] = Field(default=None, description="Processor-specific additional attributes (namespaced keys).")

    # - Optional summary lets us ingest at scale and compute value later.
    # - Helpers keep call-sites explicit and avoid None gymnastics.
    def has_summary(self) -> bool:
        """True when a human-usable abstract/keywords exist."""
        s = self.summary
        return bool(s and (s.abstract or (s.keywords and len(s.keywords) > 0)))

    def clear_summary(self) -> None:
        """Drop stale/low-quality summary without touching other fields."""
        self.summary = None

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
        """
        Mark the source as retrievable (raw file can be re-fetched).
        That means a vector search can retrieve chunks from this doc.
        This flags is set after successful ingestion of vectors into the vector store.
        """
        self.source.retrievable = True

    def mark_unretrievable(self) -> None:
        self.source.retrievable = False

    def mark_stage_error(self, stage: ProcessingStage, error_msg: str) -> None:
        self.processing.mark_error(stage, error_msg)

    def set_stage_status(self, stage: ProcessingStage, status: ProcessingStatus) -> None:
        self.processing.set_status(stage, status)

    def is_fully_processed(self) -> bool:
        return self.processing.is_fully_processed()
