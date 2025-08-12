from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class TemplateSummary(BaseModel):
    """Lightweight identity for discovery screens + agent pickers."""

    id: str = Field(..., description="Template identifier (unique within its family).")
    family: str = Field(..., description="Functional group, e.g. 'reports'.")
    name: Optional[str] = Field(None, description="Human display name.")
    description: Optional[str] = Field(None, description="Short description.")
    versions: List[str] = Field(default_factory=list, description="Available versions.")
    tags: List[str] = Field(default_factory=list)


class TemplateMetadata(BaseModel):
    """Detailed info for one version, used by UIs and agents to know required inputs."""

    id: str
    family: str
    version: str
    name: Optional[str] = None
    description: Optional[str] = None
    format: Literal["markdown", "docx", "html", "json"] = "markdown"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None  # sha256 (optional, for integrity/audit)


class TemplateContent(BaseModel):
    id: str
    version: str
    mime: Literal["text/markdown", "text/html", "application/json", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"] = "text/markdown"
    body: str
