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

"""Query pieces shared by the analytics section presets.

Each section answers for the selected period and the previous one of the same
length in a single search: a `filters` agg splits the documents in two.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from fred_core.kpi import estimate_green_cost, usd_to_eur
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import BaseModel

from control_plane_backend.kpi.presets.common import (
    TOKEN_USAGE_FILTER,
    TURN_COMPLETED_METRIC,
    scope_filter,
)

TURN_ERROR_METRIC = "agent.turn_error_total"
SESSION_CREATED_METRIC = "session.created_total"
API_REQUEST_METRIC = "api.request_latency_ms"
AGENT_CREATED_METRIC = "agent.created_total"
DOCUMENT_CREATED_METRIC = "document.created_total"
RAG_SEARCH_METRIC = "rag.search_latency_ms"

PERIODS_AGG = "periods"
# Precision up to which OpenSearch counts distinct values exactly.
CARDINALITY_PRECISION = 40000


def metric(name: str) -> dict[str, Any]:
    return {"term": {"metric.name": name}}


TURNS = metric(TURN_COMPLETED_METRIC)
TURN_ERRORS = metric(TURN_ERROR_METRIC)
SESSIONS = metric(SESSION_CREATED_METRIC)
VISITS: dict[str, Any] = {
    "bool": {
        "filter": [metric(API_REQUEST_METRIC), {"term": {"dims.actor_type": "human"}}]
    }
}
TEAM_SPACE: dict[str, Any] = {
    "bool": {
        "filter": [{"exists": {"field": "dims.team_id"}}],
        "must_not": [
            {"prefix": {"dims.team_id": "personal-"}},
            {"term": {"dims.team_id": ""}},
        ],
    }
}


class PeriodValue(BaseModel):
    """One indicator for the period and for the previous one. None = no data."""

    current: float | None = None
    previous: float | None = None


class BucketPoint(BaseModel):
    """One calendar bucket: its ISO start in the request time zone, and a value per series."""

    start: str
    values: dict[str, float]


@dataclass(frozen=True)
class Windows:
    since: datetime
    until: datetime
    previous_since: datetime

    @classmethod
    def of(cls, since: datetime, until: datetime) -> "Windows":
        return cls(since=since, until=until, previous_since=since - (until - since))


def distinct(field: str) -> dict[str, Any]:
    return {
        "cardinality": {"field": field, "precision_threshold": CARDINALITY_PRECISION}
    }


def time_range(
    gte: datetime, lte: datetime, *, inclusive_end: bool = True
) -> dict[str, Any]:
    end = "lte" if inclusive_end else "lt"
    return {"range": {"@timestamp": {"gte": gte.isoformat(), end: lte.isoformat()}}}


def two_period_body(
    windows: Windows,
    team_ids: Sequence[str],
    metrics: Sequence[dict[str, Any]],
    aggs: dict[str, Any],
    *,
    only: Literal["current", "previous"] | None = None,
    user_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Documents of `metrics` over both periods, with `aggs` computed per period.

    `only` keeps one period, for bodies whose buckets would exceed OpenSearch's
    `search.max_buckets` twice over; `search_by_period` then runs both.
    """
    periods = {
        "current": time_range(windows.since, windows.until),
        "previous": time_range(
            windows.previous_since, windows.since, inclusive_end=False
        ),
    }
    scope = time_range(windows.previous_since, windows.until)
    if only is not None:
        periods = {only: periods[only]}
        scope = periods[only]
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    scope,
                    {"bool": {"should": list(metrics), "minimum_should_match": 1}},
                    *scope_filter(team_ids, user_ids),
                ]
            }
        },
        "aggs": {PERIODS_AGG: {"filters": {"filters": periods}, "aggs": aggs}},
    }


async def search_by_period(
    store: OpenSearchKPIStore,
    windows: Windows,
    team_ids: Sequence[str],
    metrics: Sequence[dict[str, Any]],
    aggs: dict[str, Any],
    user_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """`two_period_body` as two concurrent searches, merged into one response."""
    current, previous = await asyncio.gather(
        *(
            search(
                store,
                two_period_body(
                    windows, team_ids, metrics, aggs, only=only, user_ids=user_ids
                ),
            )
            for only in ("current", "previous")
        )
    )
    return {
        "aggregations": {
            PERIODS_AGG: {
                "buckets": {
                    "current": period_buckets(current)[0],
                    "previous": period_buckets(previous)[1],
                }
            }
        }
    }


def period_buckets(response: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    buckets = response.get("aggregations", {}).get(PERIODS_AGG, {}).get("buckets", {})
    return buckets.get("current", {}), buckets.get("previous", {})


def per_period(
    response: dict[str, Any], read: Callable[[dict[str, Any]], float | None]
) -> PeriodValue:
    current, previous = period_buckets(response)
    return PeriodValue(
        current=read(current) if current else None,
        previous=read(previous) if previous else None,
    )


def doc_count(path: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda bucket: float(bucket.get(path, {}).get("doc_count", 0))


def sub_value(path: str, name: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda bucket: float(bucket.get(path, {}).get(name, {}).get("value") or 0)


def ratio(numerator: PeriodValue, denominator: PeriodValue) -> PeriodValue:
    def one(n: float | None, d: float | None) -> float | None:
        return n / d if n is not None and d else None

    return PeriodValue(
        current=one(numerator.current, denominator.current),
        previous=one(numerator.previous, denominator.previous),
    )


async def search(store: OpenSearchKPIStore, body: dict[str, Any]) -> dict[str, Any]:
    """The KPI client is synchronous: keep it off the event loop."""
    return await asyncio.to_thread(store.client.search, index=store.index, body=body)


# --- Token cost --------------------------------------------------------------

MODEL_TERMS_SIZE = 200


def token_aggs() -> dict[str, Any]:
    """Token sums per model, under the token usage filter (turns and assistant drafts)."""
    return {
        "filter": TOKEN_USAGE_FILTER,
        "aggs": {
            "by_model": {
                "terms": {
                    "field": "dims.model_name",
                    "size": MODEL_TERMS_SIZE,
                    "missing": "",
                },
                "aggs": {
                    "input": {"sum": {"field": "quantities.input_tokens"}},
                    "output": {"sum": {"field": "quantities.output_tokens"}},
                    "cached": {"sum": {"field": "quantities.cache_read_tokens"}},
                },
            }
        },
    }


@dataclass
class TokenTotals:
    input_tokens: float = 0.0
    output_tokens: float = 0.0
    cached_input_tokens: float = 0.0
    cost_eur: float = 0.0
    co2e_grams: float = 0.0
    kwh: float = 0.0

    def add(self, other: "TokenTotals") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cost_eur += other.cost_eur
        self.co2e_grams += other.co2e_grams
        self.kwh += other.kwh


def model_totals(model_bucket: dict[str, Any]) -> TokenTotals:
    input_tokens = float(model_bucket.get("input", {}).get("value") or 0)
    output_tokens = float(model_bucket.get("output", {}).get("value") or 0)
    cached = float(model_bucket.get("cached", {}).get("value") or 0)
    estimate = estimate_green_cost(
        str(model_bucket.get("key") or "") or None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cached,
    )
    return TokenTotals(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        cost_eur=usd_to_eur(estimate.cost_usd),
        co2e_grams=estimate.co2e_grams,
        kwh=estimate.kwh,
    )


def token_totals(tokens_bucket: dict[str, Any]) -> TokenTotals:
    """Sum of every model bucket under a `token_aggs()` result."""
    total = TokenTotals()
    for bucket in tokens_bucket.get("by_model", {}).get("buckets", []):
        total.add(model_totals(bucket))
    return total
