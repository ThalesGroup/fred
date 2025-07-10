from typing import List, Literal, Optional,Union
from pydantic import BaseModel

class TabularColumnSchema(BaseModel):
    name: str
    dtype: Literal["string", "integer", "float", "boolean", "datetime", "unknown"]

class TabularSchemaResponse(BaseModel):
    document_name: str
    columns: List[TabularColumnSchema]
    row_count: Optional[int] = None

class AggregationSpec(BaseModel):
    function: str
    column: str
    alias: Optional[str] = None

class JoinSpec(BaseModel):
    table: str
    on: str
    type: Optional[str] = "INNER"

class SQLQueryPlan(BaseModel):
    table: str
    columns: Optional[List[str]] = None
    filters: Optional[dict] = None
    group_by: Optional[List[str]] = None
    order_by: Optional[List[str]] = None
    limit: Optional[int] = None
    joins: Optional[List[JoinSpec]] = None
    aggregations: Optional[List[AggregationSpec]] = None

class TabularQueryRequest(BaseModel):
    query: Optional[Union[str, SQLQueryPlan]] = None

class TabularQueryResponse(BaseModel):
    document_name: str
    rows: List[dict]

class TabularDatasetMetadata(BaseModel):
    document_name: str
    title: str
    description: Optional[str] = ""
    tags: List[str] = []
    domain: Optional[str] = ""
    row_count: Optional[int] = None
