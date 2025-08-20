from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Minimal Pydantic models kept in one place ---


class EvidenceLink(BaseModel):
    document_uid: str
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    quote: Optional[str] = None
    score: Optional[float] = None


class CIRAssessmentOutput(BaseModel):
    novelty: str = ""
    uncertainty: str = ""
    systematic_approach: str = ""
    knowledge_creation: str = ""
    eligibility_binary: str = "no" # "yes" if clearly eligible based on evidence


class CIROutlineOutput(BaseModel):
    sections: List[str] = Field(default_factory=list)


class CIRSectionDraft(BaseModel):
    section_title: str
    content_markdown: str


class CirEvent(BaseModel):
    kind: str # 'commit','meeting','experiment','benchmark','failure','event'
    date: Optional[datetime] = None
    title: Optional[str] = None
    ref: Optional[str] = None
    snippet: Optional[str] = None