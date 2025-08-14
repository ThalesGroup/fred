from typing import List
from pydantic import BaseModel, Field


class CIRAssessmentOutput(BaseModel):
    novelty: str
    scientific_uncertainty: str
    systematic_approach: str
    knowledge_creation: str
    eligibility_binary: str = Field(..., description="'yes' or 'no'")


class CIROutlineOutput(BaseModel):
    title: str
    sections: List[str]


class CIRSectionDraft(BaseModel):
    section_title: str
    content_markdown: str
