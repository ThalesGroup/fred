from typing import List, Literal, Optional
from pydantic import BaseModel

class TabularColumnSchema(BaseModel):
    name: str
    dtype: Literal["string", "integer", "float", "boolean", "datetime", "unknown"]

class TabularSchemaResponse(BaseModel):
    document_uid: str
    columns: List[TabularColumnSchema]
    row_count: Optional[int] = None

class TabularQueryRequest(BaseModel):
    columns: Optional[List[str]] = None
    filters: Optional[dict] = None  # keep flexible for now, will evolve
    limit: Optional[int] = 100

class TabularQueryResponse(BaseModel):
    document_uid: str
    rows: List[dict]

class TabularDatasetMetadata(BaseModel):
    document_uid: str
    title: str
    description: Optional[str] = ""
    tags: List[str] = []
    domain: Optional[str] = ""
    row_count: Optional[int] = None
