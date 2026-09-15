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

"""
How often something recurs, said the way the engine that runs it says it.

Deliberately not a vocabulary of Fred's own. A closed list of named cadences —
hourly, daily, weekly — is a translation table that has to grow every time
somebody needs a value nobody anticipated, and it says less than the engine
underneath already understands. This carries a duration instead, and hands it
to Temporal unchanged.

One arm today, `interval`, because that is what anything has asked for. The
discriminated union is what lets `cron` and `calendar` arrive later without a
stored value changing shape — the same pattern `RebacConfiguration` uses for
the same reason.

Nothing here is about Knowledge Bases. A recurring administration task wants
exactly this.
"""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field
from temporalio.client import ScheduleIntervalSpec, ScheduleSpec

# A second is the floor the engine itself can express. What is *reasonable* for
# a given source is not this model's business: it belongs to whoever configures
# a schedule, and a number invented here would be one nobody could change.
MIN_EVERY_SECONDS = 1


class IntervalSchedule(BaseModel):
    """Every N seconds, measured from the epoch.

    Temporal's own semantics, unchanged: `epoch + (n * every) + offset`.
    """

    type: Literal["interval"] = "interval"
    every_seconds: int = Field(
        ge=MIN_EVERY_SECONDS,
        description="Seconds between two occurrences.",
    )

    @property
    def every(self) -> timedelta:
        return timedelta(seconds=self.every_seconds)


# One arm, and a discriminator, so that adding `cron` or `calendar` is adding a
# class rather than reshaping everything that stores a schedule.
Schedule = Annotated[Union[IntervalSchedule], Field(discriminator="type")]


def to_temporal_spec(
    schedule: Schedule, *, spread_over: str | None = None
) -> ScheduleSpec:
    """Translate a schedule into what Temporal accepts.

    `spread_over` is the reason this is a function and not an attribute. An
    interval with no offset is anchored on the epoch, so every schedule of the
    same period in a deployment fires on the very same second — a hundred
    hourly ones would hit their sources, and this platform's ingestion, all at
    once. Deriving the offset from a caller's own stable identity gives each
    one its own slot inside the period, keeps that slot across restarts, and
    stores nothing to remember it.

    Pass nothing and the schedule stays anchored on the epoch, which is what a
    single deployment-wide task wants.
    """
    if not isinstance(schedule, IntervalSchedule):  # pragma: no cover - one arm today
        raise TypeError(f"Unsupported schedule: {schedule!r}")

    every = schedule.every
    offset = None
    if spread_over:
        slot = int(sha256(spread_over.encode()).hexdigest(), 16)
        offset = timedelta(seconds=slot % int(every.total_seconds()))
    return ScheduleSpec(intervals=[ScheduleIntervalSpec(every=every, offset=offset)])


__all__ = [
    "MIN_EVERY_SECONDS",
    "IntervalSchedule",
    "Schedule",
    "to_temporal_spec",
]
