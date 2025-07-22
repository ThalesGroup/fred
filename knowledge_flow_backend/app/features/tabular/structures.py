# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import List, Literal, Optional,Union, Any
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
    distinct: bool = False
    filter: Optional[dict] = None  # ex: {"status": "PAID"}

class FilterCondition(BaseModel):
    column: str
    op: str = "="
    value: Any

class JoinSpec(BaseModel):
    table: str
    on: str
    type: Optional[str] = "INNER"

class OrderBySpec(BaseModel):
    column: str
    direction: Optional[str] = "ASC"  # Default ascending

class SQLQueryPlan(BaseModel):
    table: str
    columns: Optional[List[str]] = None
    filters: Optional[List[FilterCondition]] = None
    group_by: Optional[List[str]] = None
    order_by: Optional[List[OrderBySpec]] = None
    limit: Optional[int] = None
    joins: Optional[List[JoinSpec]] = None
    aggregations: Optional[List[AggregationSpec]] = None

class TabularQueryRequest(BaseModel):
    query: Optional[Union[str, SQLQueryPlan]] = None

class TabularQueryResponse(BaseModel):
    document_name: str
    rows: List[dict]

class HowToMakeAQueryResponse(BaseModel):
    how: str

class TabularDatasetMetadata(BaseModel):
    document_name: str
    title: str
    description: Optional[str] = ""
    tags: List[str] = []
    domain: Optional[str] = ""
    row_count: Optional[int] = None
