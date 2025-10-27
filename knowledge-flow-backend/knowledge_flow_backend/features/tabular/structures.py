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

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, model_validator

# -- Constants for consistent types --
DTypes = Literal["string", "integer", "float", "boolean", "datetime", "unknown"]

# -- Schema models --


class TabularColumnSchema(BaseModel):
    name: str
    dtype: DTypes


class ListTableResponse(BaseModel):
    db_name: str
    tables: list[str]


class TabularSchemaResponse(BaseModel):
    db_name: str
    table_name: str
    columns: List[TabularColumnSchema]
    row_count: Optional[int] = None


class RawSQLRequest(BaseModel):
    query: str


class TabularQueryResponse(BaseModel):
    db_name: str
    sql_query: str
    rows: Optional[List[dict]] = []
    error: Optional[str] = None


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
