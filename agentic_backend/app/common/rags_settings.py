# app/core/rag/rag_settings.py
from pydantic import BaseModel, Field
from typing import List, Optional


class RagSettings(BaseModel):
    knowledge_flow_url: str = Field(default="http://localhost:8111/knowledge-flow/v1")
    top_k: int = 3
    timeout_s: int = 10
    snippet_chars: int = 500
    include_tags_from_runtime_context: bool = True
    default_libraries: Optional[List[str]] = None  # fallback tags if runtime has none
