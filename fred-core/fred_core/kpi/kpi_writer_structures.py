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

from datetime import datetime
from typing import Any, Dict, Iterable, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# --------------------
# Metric & Event types
# --------------------
MetricType = Literal["counter", "gauge", "timer", "distribution"]


# Metric naming conventions (keep short & dot-namespaced)
# Core set to start with; extend safely later without breaking dashboards.
class MetricNames:
    # Vectorization / ingestion
    VEC_DURATION_MS = "vectorization.duration_ms"  # timer
    VEC_FAILED_TOTAL = "vectorization.failed_total"  # counter
    VEC_CHUNKS = "vectorization.chunks"  # gauge/counter
    VEC_VECTORS = "vectorization.vectors"  # gauge/counter
    ING_BYTES_IN = "ingestion.bytes_in"  # counter

    # Vector store
    VS_READ_LAT_MS = "vectorstore.read_latency_ms"  # timer
    VS_WRITE_LAT_MS = "vectorstore.write_latency_ms"  # timer
    VS_DOCS_TOTAL = "vectorstore.documents_total"  # gauge
    VS_SIZE_MB = "vectorstore.index.size_mb"  # gauge

    # LLM
    LLM_LAT_MS = "llm.request_latency_ms"  # timer
    LLM_RATE_LIMITS = "llm.rate_limit_events_total"  # counter

    # Sessions / usage
    SESS_CREATED = "session.created_total"  # counter
    SESS_DURATION = "session.duration_ms"  # timer
    SESS_EXCHANGES = "session.exchanges_total"  # counter

    # Agent orchestration
    AG_STEP_TOTAL = "agent.step_total"  # counter
    AG_TOOL_LAT_MS = "agent.tool_latency_ms"  # timer
    AG_TOOL_FAIL = "agent.tool_failed_total"  # counter

    # Document usage
    DOC_USED_TOTAL = "doc.used_total"  # counter
    DOC_CITED_TOTAL = "doc.cited_total"  # counter

    # Quality
    Q_USER_RATING = "quality.user_rating"  # gauge
    Q_AUTO_SCORE = "quality.auto_eval_score"  # gauge

    # Generic errors (catch-all)
    ERROR_TOTAL = "error.total"  # counter
    API_ERROR_TOTAL = "api.error_total"  # counter


class Metric(BaseModel):
    name: str
    type: MetricType
    unit: Optional[str] = None
    value: Optional[float] = None
    # distribution fields (optional; only if batching histograms)
    count: Optional[int] = None
    sum: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    histogram: Optional[Dict[str, Any]] = None

    @field_validator("value")
    @classmethod
    def _value_required_when_needed(cls, v, info):
        # For counter/gauge/timer, a scalar value is required.
        mtype = info.data.get("type")
        if mtype in ("counter", "gauge", "timer") and v is None:
            raise ValueError(f"metric.value is required for type={mtype}")
        return v


class Cost(BaseModel):
    tokens_prompt: Optional[int] = 0
    tokens_completion: Optional[int] = 0
    tokens_total: Optional[int] = 0
    usd: Optional[float] = 0.0


class Quantities(BaseModel):
    bytes_in: Optional[int] = 0
    bytes_out: Optional[int] = 0
    chunks: Optional[int] = 0
    vectors: Optional[int] = 0


class Trace(BaseModel):
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None


# Dims: cardinality-critical identifiers; keep them stable and few.
# - status: "ok" | "error" | "timeout" | "filtered" | "cancelled"
# - http_status: "200".."599" when relevant
# - error_code: short machine code (e.g., "rate_limit", "jwt_invalid", "timeout", "pdf_parse")
# - exception_type: short class name (e.g., "TimeoutError", "JWTError")
Dims = Dict[str, Optional[str]]


class KPIActor(BaseModel):
    """
    Required for every KPI emission.
    - type='human' requires a user_id
    - type='system' is allowed without user_id
    """

    type: Literal["human", "system"]
    user_id: Optional[str] = None

    @field_validator("user_id")
    @classmethod
    def _human_requires_user_id(cls, v, info):
        if info.data.get("type") == "human" and not v:
            raise ValueError("user_id is required when actor.type='human'")
        return v


class KPIEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow, alias="@timestamp")
    metric: Metric
    dims: Dims = Field(default_factory=dict)
    cost: Optional[Cost] = None
    quantities: Optional[Quantities] = None
    labels: Iterable[str] = Field(default_factory=list)  # low-cardinality tags
    source: Optional[str] = None
    trace: Optional[Trace] = None

    def to_doc(self) -> Dict[str, Any]:
        # Convert to a backend-agnostic dict
        doc: Dict[str, Any] = {
            "@timestamp": self.timestamp,
            "metric": self.metric.model_dump(exclude_none=True),
            "dims": {k: v for k, v in (self.dims or {}).items() if v is not None},
            "labels": list(self.labels or []),
        }
        if self.cost:
            doc["cost"] = self.cost.model_dump(exclude_none=True)
        if self.quantities:
            doc["quantities"] = self.quantities.model_dump(exclude_none=True)
        if self.source:
            doc["source"] = self.source
        if self.trace:
            doc["trace"] = self.trace.model_dump(exclude_none=True)
        return doc
