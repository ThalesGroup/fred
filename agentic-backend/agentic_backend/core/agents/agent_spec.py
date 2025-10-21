# app/common/tuning_spec.py
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

FieldType = Literal[
    "string",
    "text",
    "text-multiline",
    "number",
    "integer",
    "boolean",
    "select",
    "array",
    "object",
    "prompt",
    "secret",
    "url",
]


class UIHints(BaseModel):
    multiline: bool = False
    max_lines: int = 6
    placeholder: Optional[str] = None
    markdown: bool = False
    textarea: bool = False
    group: Optional[str] = None  # e.g., "Prompts", "MCP", "Advanced"


class FieldSpec(BaseModel):
    key: str  # dotted path under agent.settings (e.g., "prompts.system")
    type: FieldType
    title: str
    description: Optional[str] = None  # "why this matters" → your style
    required: bool = False
    default: Optional[Any] = None
    enum: Optional[List[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    item_type: Optional[FieldType] = None  # for arrays
    ui: UIHints = UIHints()


class McpServerSpec(BaseModel):
    allow_user_add: bool = True
    allowed_transports: List[str] = ["streamable_http", "sse", "http"]
    required_fields: List[str] = ["name", "transport", "url"]


class AgentTuning(BaseModel):
    fields: List[FieldSpec] = Field(default_factory=list)
    mcp_servers: Optional[McpServerSpec] = None
