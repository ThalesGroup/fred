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
"""A recurrence carried as a duration, and handed to Temporal unchanged."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import BaseModel, ValidationError

from fred_core.scheduler import IntervalSchedule, Schedule, to_temporal_spec


class _Holder(BaseModel):
    """A stored schedule, as a caller would declare one."""

    schedule: Schedule


def test_any_duration_is_expressible_without_a_named_cadence() -> None:
    """The point of the change: no closed list to grow every time."""
    for seconds in (60, 300, 3600, 86_400, 604_800):
        assert IntervalSchedule(every_seconds=seconds).every == timedelta(
            seconds=seconds
        )


def test_a_duration_reaches_temporal_unchanged() -> None:
    spec = to_temporal_spec(IntervalSchedule(every_seconds=300))

    assert len(spec.intervals) == 1
    assert spec.intervals[0].every == timedelta(minutes=5)
    assert spec.intervals[0].offset is None


def test_two_callers_of_one_period_get_different_slots() -> None:
    """An interval is anchored on the epoch — `epoch + n*every + offset`.

    Without an offset every schedule of the same period in a deployment fires
    on the very same second, so a hundred of them hit their sources, and this
    platform's ingestion, at once.
    """
    schedule = IntervalSchedule(every_seconds=300)

    first = to_temporal_spec(schedule, spread_over="instance-a").intervals[0].offset
    second = to_temporal_spec(schedule, spread_over="instance-b").intervals[0].offset

    assert first != second
    assert first is not None and first < timedelta(minutes=5)
    assert second is not None and second < timedelta(minutes=5)


def test_a_slot_is_stable_so_nothing_has_to_store_it() -> None:
    schedule = IntervalSchedule(every_seconds=3600)

    assert (
        to_temporal_spec(schedule, spread_over="instance-a").intervals[0].offset
        == to_temporal_spec(schedule, spread_over="instance-a").intervals[0].offset
    )


def test_a_period_of_zero_or_less_is_refused() -> None:
    for seconds in (0, -1):
        with pytest.raises(ValidationError):
            IntervalSchedule(every_seconds=seconds)


def test_a_stored_schedule_round_trips_through_its_discriminator() -> None:
    """What lets `cron` and `calendar` arrive without reshaping stored values."""
    stored = _Holder(schedule=IntervalSchedule(every_seconds=900)).model_dump()

    assert stored["schedule"] == {"type": "interval", "every_seconds": 900}
    assert _Holder.model_validate(stored).schedule.every_seconds == 900


def test_an_unknown_kind_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValidationError):
        _Holder.model_validate(
            {"schedule": {"type": "cron", "expressions": ["* * * * *"]}}
        )
