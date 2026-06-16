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


class ScalarWithDeltaResponse(BaseModel):
    """Current scalar value plus net change over the requested time range."""

    value: int
    delta: int
    since: AwareDatetime
    until: AwareDatetime


class LabelValuePoint(BaseModel):
    label: str
    value: int


class LabelValueResponse(BaseModel):
    rows: list[LabelValuePoint]
    since: AwareDatetime
    until: AwareDatetime
