# Copyright Thales 2026
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

from pydantic import BaseModel, ConfigDict, Field, field_validator

PrometheusTimeValue = str | int | float | datetime


class _PrometheusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrometheusQueryRequest(_PrometheusRequest):
    query: str = Field(..., description="PromQL expression to evaluate.")
    time: PrometheusTimeValue | None = Field(
        default=None,
        description="Optional evaluation timestamp accepted by the Prometheus HTTP API.",
    )
    timeout: str | None = Field(
        default=None,
        description="Optional upstream Prometheus timeout, for example 5s.",
    )

    @field_validator("query", mode="after")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


class PrometheusQueryRangeRequest(_PrometheusRequest):
    query: str = Field(..., description="PromQL expression to evaluate over a range.")
    start: PrometheusTimeValue = Field(
        ...,
        description="Range start accepted by the Prometheus HTTP API.",
    )
    end: PrometheusTimeValue = Field(
        ...,
        description="Range end accepted by the Prometheus HTTP API.",
    )
    step: str | int | float = Field(
        ...,
        description="Range step duration accepted by the Prometheus HTTP API.",
    )
    timeout: str | None = Field(
        default=None,
        description="Optional upstream Prometheus timeout, for example 30s.",
    )

    @field_validator("query", mode="after")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


class PrometheusSeriesRequest(_PrometheusRequest):
    matchers: list[str] = Field(
        ...,
        min_length=1,
        description="Prometheus series matchers, for example up or http_requests_total{job='api'}.",
    )
    start: PrometheusTimeValue | None = Field(
        default=None,
        description="Optional range start used to bound series discovery.",
    )
    end: PrometheusTimeValue | None = Field(
        default=None,
        description="Optional range end used to bound series discovery.",
    )

    @field_validator("matchers", mode="after")
    @classmethod
    def validate_matchers(cls, value: list[str]) -> list[str]:
        normalized = [matcher.strip() for matcher in value if matcher and matcher.strip()]
        if not normalized:
            raise ValueError("matchers must contain at least one non-empty matcher")
        return normalized
