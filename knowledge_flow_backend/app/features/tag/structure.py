from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from fred_core import BaseModelWithId

class TagType(Enum):
    LIBRARY = "library"

class TagCreate(BaseModel):
    name: str
    description: str | None = None
    type: TagType
    document_ids: list[str] = []


class TagUpdate(BaseModel):
    name: str
    description: str | None = None
    type: TagType
    document_ids: list[str] = []


class Tag(BaseModelWithId):
    created_at: datetime
    updated_at: datetime
    owner_id: str

    name: str
    description: str | None = None
    type: TagType
    document_ids: list[str] = []
