from datetime import datetime
from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str
    description: str | None = None
    document_ids: list[str] = []


class TagUpdate(BaseModel):
    name: str
    description: str | None = None
    document_ids: list[str] = []


class Tag(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str
    description: str | None = None
    document_ids: list[str] = []
