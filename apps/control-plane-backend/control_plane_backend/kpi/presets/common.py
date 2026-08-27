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

from pydantic import AwareDatetime, BaseModel


class TimeSeriesPoint(BaseModel):
    date: str  # display-formatted label produced by strftime (e.g. "Jan 15")
    value: float
    # Populated only by the token-usage presets (KPI-ANALYTICS-RFC.md §2.7) —
    # every other preset leaves these None. Estimates, not billing-grade.
    co2e_grams: float | None = None
    kwh: float | None = None
    cost_usd: float | None = None


class TimeSeriesResponse(BaseModel):
    rows: list[TimeSeriesPoint]
    since: AwareDatetime
    until: AwareDatetime
    interval: str
    # Set only by the trailing-window trend presets (issue #2428) — the window
    # each point pools before taking its median, in the same compact form as
    # `interval` ("7d" for 7 daily buckets). None everywhere else, and the
    # routes serialize with `response_model_exclude_none=True`, so a plain
    # time-series preset's payload is unchanged on the wire. The frontend
    # localizes the unit letter rather than hardcoding "7-day".
    window: str | None = None


class ScalarResponse(BaseModel):
    """Single integer metric for the requested time range."""

    value: int
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
    cost_usd: float | None = None


class LabelValueResponse(BaseModel):
    rows: list[LabelValuePoint]
    since: AwareDatetime
    until: AwareDatetime


class DistributionResponse(BaseModel):
    """Histogram of a per-entity count, plus the median of the raw counts.

    `rows` always holds every bucket (value 0 when empty) so the chart has no
    gaps. `median` is None when the range contains no entity at all — an empty
    distribution, not a zero one.
    """

    rows: list[LabelValuePoint]
    median: float | None = None
    since: AwareDatetime
    until: AwareDatetime


class MultiSeriesPoint(BaseModel):
    date: str
    values: dict[str, float]


class MultiSeriesTimeSeriesResponse(BaseModel):
    """Multi-series time-bucketed metric — one named series per tracked entity."""

    rows: list[MultiSeriesPoint]
    series: list[str]
    since: AwareDatetime
    until: AwareDatetime
    interval: str


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
