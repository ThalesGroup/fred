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

from collections.abc import Sequence
from typing import Any

from pydantic import AwareDatetime, BaseModel

# Token-usage presets sum both metrics (same `quantities.*_tokens` names);
# turn, conversation and latency presets read `agent.turn_completed` only.
TURN_COMPLETED_METRIC = "agent.turn_completed"
CREATION_ASSISTANT_METRIC = "agent.creation_assistant_completed"
# Creation assistant events are emitted for every outcome; only those the
# provider answered carry tokens, so the others never open an empty bucket.
CREATION_ASSISTANT_ANSWERED_FILTER: dict[str, Any] = {
    "bool": {
        "filter": [
            {"term": {"metric.name": CREATION_ASSISTANT_METRIC}},
            {"exists": {"field": "quantities.input_tokens"}},
        ]
    }
}
TOKEN_USAGE_FILTER: dict[str, Any] = {
    "bool": {
        "should": [
            {"term": {"metric.name": TURN_COMPLETED_METRIC}},
            CREATION_ASSISTANT_ANSWERED_FILTER,
        ],
        "minimum_should_match": 1,
    }
}
# By-agent bucket of creation assistant calls, which have no agent; translated in the UI.
CREATION_ASSISTANT_LABEL = "__creation_assistant__"
BY_AGENT_SCOPE_FILTER: dict[str, Any] = {
    "bool": {
        "should": [
            {"exists": {"field": "dims.agent_instance_name"}},
            {"term": {"metric.name": CREATION_ASSISTANT_METRIC}},
        ],
        "minimum_should_match": 1,
    }
}


def team_filter(team_ids: Sequence[str]) -> list[dict[str, Any]]:
    """The `bool.filter` clause for a team scope; empty for the whole platform."""
    if not team_ids:
        return []
    return [{"terms": {"dims.team_id": [str(t) for t in team_ids]}}]


def user_filter(user_ids: Sequence[str] | None) -> list[dict[str, Any]]:
    """The `bool.filter` clause of a user filter; None = no filter, empty = nobody."""
    if user_ids is None:
        return []
    return [{"terms": {"dims.user_id": list(user_ids)}}]


def scope_filter(
    team_ids: Sequence[str], user_ids: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """Team and user clauses of a KPI query, in one call so neither is forgotten."""
    return [*team_filter(team_ids), *user_filter(user_ids)]


class TimeSeriesPoint(BaseModel):
    date: str  # display-formatted label produced by strftime (e.g. "Jan 15")
    value: float
    # Populated only by the token-usage presets (KPI-ANALYTICS-RFC.md §2.7) —
    # every other preset leaves these None. Estimates, not billing-grade.
    co2e_grams: float | None = None
    kwh: float | None = None
    cost_eur: float | None = None


class TimeSeriesResponse(BaseModel):
    rows: list[TimeSeriesPoint]
    since: AwareDatetime
    until: AwareDatetime
    interval: str


class ScalarResponse(BaseModel):
    """Single integer metric for the requested time range."""

    value: int
    since: AwareDatetime
    until: AwareDatetime


class CreationAssistantUsageResponse(BaseModel):
    """Creation assistant token consumption and call count for the time range."""

    total_tokens: int
    input_tokens: int
    output_tokens: int
    drafts: int
    since: AwareDatetime
    until: AwareDatetime


class ScalarWithDeltaResponse(BaseModel):
    """Current scalar value plus net change over the requested time range.

    When `unavailable` is True, value and delta are absent: historical data
    cannot be reconstructed (e.g. KPI instrumentation was not yet deployed
    before `until`).
    """

    value: int | None = None
    delta: int | None = None
    unavailable: bool = False
    since: AwareDatetime
    until: AwareDatetime


class LabelValuePoint(BaseModel):
    label: str
    value: int
    # Populated only by the token-usage presets (KPI-ANALYTICS-RFC.md §2.7) —
    # every other preset leaves these None. Estimates, not billing-grade.
    co2e_grams: float | None = None
    kwh: float | None = None
    cost_eur: float | None = None


class LabelValueResponse(BaseModel):
    rows: list[LabelValuePoint]
    since: AwareDatetime
    until: AwareDatetime


class SkillUsageRow(BaseModel):
    skill_name: str
    user_count: int
    model_count: int
    total: int


class SkillUsageResponse(BaseModel):
    rows: list[SkillUsageRow]
    since: AwareDatetime
    until: AwareDatetime
    truncated: bool = False


class TeamStorageRow(BaseModel):
    team_id: str
    label: str
    used_bytes: int
    # None only when neither a per-team override nor a platform default is
    # configured — an unlimited team, not a data gap.
    quota_bytes: int | None = None


class TeamStorageResponse(BaseModel):
    """Current resource-storage usage vs. quota, per team (a state gauge, not
    a time-bucketed metric — `since`/`until` are echoed for API consistency
    with every other preset, not used to filter this query)."""

    rows: list[TeamStorageRow]
    since: AwareDatetime
    until: AwareDatetime
