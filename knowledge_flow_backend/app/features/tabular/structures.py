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

from typing import List, Literal, Optional, Union, Any, Dict
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

# -- Constants for consistent types --
DTypes = Literal["string", "integer", "float", "boolean", "datetime", "unknown"]

# -- Schema models --

class TabularColumnSchema(BaseModel):
    name: str
    dtype: DTypes


class TabularSchemaResponse(BaseModel):
    document_name: str
    columns: List[TabularColumnSchema]
    row_count: Optional[int] = None

# -- Query & Planning --

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
    direction: Optional[Literal["ASC", "DESC"]] = "ASC"


class AggregationSpec(BaseModel):
    function: str
    column: str
    alias: Optional[str] = None
    distinct: bool = False
    filter: Optional[Dict[str, Any]] = None  # Optional SQL filter within aggregation


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

# -- Aggregation Models --

class Precision(str, Enum):
    sec = "sec"
    min = "min"
    hour = "hour"
    day = "day"
    all = "all"  # for global (non-bucketed) aggregations


class Aggregation(str, Enum):
    min = "MIN"
    max = "MAX"
    count = "COUNT"
    count_distinct = "COUNT_DISTINCT"
    avg = "AVG"
    sum = "SUM"


class AggregatedBucket(BaseModel):
    time_bucket: str
    values: Dict[str, Any]
    groupby_fields: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def extract_groupby_fields(cls, values):
        if "groupby_fields" not in values:
            reserved = {"time_bucket", "values"}
            groupby = {k: v for k, v in values.items() if k not in reserved}
            if groupby:
                values["groupby_fields"] = groupby
        return values


class TabularAggregationResponse(BaseModel):
    buckets: List[AggregatedBucket]
