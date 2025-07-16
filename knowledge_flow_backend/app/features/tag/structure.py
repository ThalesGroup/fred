from datetime import datetime
from pydantic import BaseModel
from fred_core import BaseModelWithId

class TagCreate(BaseModel):
    name: str
    description: str | None = None
    document_ids: list[str] = []


class TagUpdate(BaseModel):
    name: str
    description: str | None = None
    document_ids: list[str] = []


class Tag(BaseModelWithId):
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str
    description: str | None = None
    document_ids: list[str] = []
