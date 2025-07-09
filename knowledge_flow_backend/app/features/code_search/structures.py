# app/features/code_search/structures.py
from pydantic import BaseModel, Field
from typing import Optional

from app.common.structures import Status

class CodeSearchRequest(BaseModel):
    query: str
    top_k: int = 10

class CodeDocumentSource(BaseModel):
    content: str
    file_path: str
    file_name: str
    language: str
    symbol: Optional[str] = None  # e.g., method or class name
    uid: str
    score: float
    rank: Optional[int] = None
    embedding_model: Optional[str] = None
    vector_index: Optional[str] = None


class CodeIndexRequest(BaseModel):
    path: str

class CodeIndexProgress(BaseModel):
    step: str
    status: Status
    message: Optional[str] = None
    error: Optional[str] = None