from pydantic import BaseModel, Field
from typing import Optional

class DocumentSource(BaseModel):
    content: str
    file_path: str
    file_name: str
    page: Optional[int]
    uid: str
    agent_name: Optional[str] = None
    modified: Optional[str] = None

    # Required by frontend
    title: str
    author: str
    created: str
    type: str

    # Metrics
    score: float = Field(..., description="Similarity score from vector search")
    rank: Optional[int] = None
    embedding_model: Optional[str] = None
    vector_index: Optional[str] = None
    token_count: Optional[int] = None

    # Provenance
    retrieved_at: Optional[str] = None
    retrieval_session_id: Optional[str] = None
