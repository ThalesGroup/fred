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

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

MetricField = Literal[
    "metric.value",
    "cost.tokens_total",
    "cost.usd",
    "cost.tokens_prompt",
    "cost.tokens_completion",
]
GroupByField = Literal[
    "dims.file_type",
    "dims.doc_uid",
    "dims.doc_source",
    "dims.user_id",
    "dims.agent_id",
    "dims.step",
    "dims.agent_step",
    "dims.tool_name",
    "dims.model",
    "dims.http_status",
    "dims.error_code",
    "dims.status",
    "dims.service",
]
AggOp = Literal["sum", "avg", "min", "max", "count", "value_count", "percentile"]
OrderDir = Literal["asc", "desc"]


class TimeBucket(BaseModel):
    interval: str = Field(..., description="e.g. '1h', '1d', '15m'")
    timezone: Optional[str] = Field(None, description="IANA TZ, e.g. 'Europe/Paris'")


class FilterTerm(BaseModel):
    field: Literal[
        "metric.name",
        "metric.type",
        "dims.status",
        "dims.user_id",
        "dims.agent_id",
        "dims.doc_uid",
        "dims.file_type",
        "dims.http_status",
        "dims.error_code",
        "dims.model",
        "dims.step",
        "dims.agent_step",
        "dims.service",
    ]
    value: str


class SelectMetric(BaseModel):
    alias: str = Field(..., description="name in response, e.g. 'p95' or 'cost_usd'")
    op: AggOp
    field: Optional[MetricField] = Field(
        None, description="Required except for count/percentile"
    )
    p: Optional[float] = Field(None, ge=0, le=100, description="Percentile, e.g. 95")

    @field_validator("field")
    @classmethod
    def check_field(cls, v, info):
        op = info.data.get("op")
        if op == "count":
            return None
        if op == "percentile" and v is None:
            return "metric.value"
        if v is None:
            raise ValueError(f"field is required for op={op}")
        return v


class OrderBy(BaseModel):
    by: Literal["doc_count", "metric"] = "doc_count"
    metric_alias: Optional[str] = None
    direction: OrderDir = "desc"


class KPIQuery(BaseModel):
    since: str = Field(..., description="ISO or 'now-24h'")
    until: Optional[str] = None
    view_global: bool = False
    filters: List[FilterTerm] = Field(default_factory=list)
    select: List[SelectMetric] = Field(..., min_length=1)  # require at least one metric
    group_by: List[GroupByField] = Field(default_factory=list)
    time_bucket: Optional[TimeBucket] = None
    limit: int = Field(10, ge=1, le=1000)
    order_by: Optional[OrderBy] = None


class KPIQueryResultRow(BaseModel):
    group: Dict[str, Any]
    metrics: Dict[str, float]
    doc_count: int


class KPIQueryResult(BaseModel):
    rows: List[KPIQueryResultRow] = Field(default_factory=list)
