from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    PUSH = "push"
    PULL = "pull"


class ProcessingStage(str, Enum):
    RAW_AVAILABLE = "raw"  # raw file can be downloaded
    PREVIEW_READY = "preview"  # e.g. Markdown or DataFrame generated
    VECTORIZED = "vector"  # content chunked and embedded
    SQL_INDEXED = "sql"  # content indexed into SQL backend
    MCP_SYNCED = "mcp"  # content synced to external system


class DocumentMetadata(BaseModel):
    # Core identity
    document_name: str
    document_uid: str
    date_added_to_kb: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc), description="When the document was added to the system")

    # If true, the raw file can be retrieved again (e.g., from push uploads or a stable pull source)
    retrievable: bool = Field(default=False, description="True if the system can download or access the original file again")

    # Pull-mode specific fields (optional for push documents)
    source_tag: Optional[str] = Field(default=None, description="Tag identifying the pull source (e.g., 'local-docs', 'contracts-git')")
    pull_location: Optional[str] = Field(default=None, description="Path or URI to the original pull file")

    source_type: SourceType

    # User-assigned tags and metadata (often editable via UI)
    tags: Optional[List[str]] = Field(default=None, description="User-assigned tags")
    title: Optional[str] = None
    author: Optional[str] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    last_modified_by: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None

    # Ingestion processing stages and their status
    processing_stages: Dict[ProcessingStage, Literal["not_started", "in_progress", "done", "failed"]] = Field(default_factory=dict, description="Status of each well-defined processing stage")

    def mark_stage_done(self, stage: ProcessingStage) -> None:
        self.processing_stages[stage] = "done"

    def mark_stage_error(self, stage: ProcessingStage, error_msg: str) -> None:
        self.processing_stages[stage] = f"error: {error_msg}"

    def clear_processing_stages(self) -> None:
        self.processing_stages.clear()

    def set_stage_status(self, stage: ProcessingStage, status: str) -> None:
        self.processing_stages[stage] = status

    def is_fully_processed(self) -> bool:
        return all(v == "done" for v in self.processing_stages.values())

    def get_display_name(self) -> str:
        return self.title or self.document_name

    @field_validator("processing_stages")
    @classmethod
    def validate_stage_keys(cls, stages: dict) -> dict:
        for key in stages:
            if not isinstance(key, ProcessingStage):
                raise ValueError(f"Invalid processing stage: {key}")
        return stages

    model_config = {
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
            "examples": [
                {
                    "document_name": "report_2025.pdf",
                    "document_uid": "pull-local-docs-aabbccddeeff",
                    "date_added_to_kb": "2025-07-19T12:45:00+00:00",
                    "retrievable": False,
                    "source_tag": "local-docs",
                    "pull_location": "Archive/2025/report_2025.pdf",
                    "source_type": "pull",
                    "processing_stages": {"preview": "done", "vector": "done"},
                    "tags": ["finance", "q2"],
                    "title": "Quarterly Report Q2",
                    "author": "Finance Team",
                    "created": "2025-07-01T10:00:00+00:00",
                    "modified": "2025-07-02T14:30:00+00:00",
                }
            ]
        },
    }
