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

"""Which local days the analytics count: weekends and French public holidays can
be left out. Excluded days become `must_not` time ranges, so every search drops
them without a script and without an extra round trip."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, Query

DEFAULT_TZ = "Europe/Paris"
# Keeps the `must_not` list well under OpenSearch's bool clause limit (1024).
MAX_PERIOD = timedelta(days=4 * 366)

_FIXED_HOLIDAYS = (
    (1, 1),
    (5, 1),
    (5, 8),
    (7, 14),
    (8, 15),
    (11, 1),
    (11, 11),
    (12, 25),
)


def easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 - the algorithm's own name
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def french_holidays(year: int) -> frozenset[date]:
    """The eleven French public holidays: eight fixed dates, Easter Monday,
    Ascension and Whit Monday."""
    easter = easter_sunday(year)
    movable = (easter + timedelta(days=n) for n in (1, 39, 50))
    return frozenset([*(date(year, m, d) for m, d in _FIXED_HOLIDAYS), *movable])


@dataclass(frozen=True)
class CountedDays:
    exclude_weekends: bool = False
    exclude_holidays: bool = False
    tz: str = DEFAULT_TZ

    @property
    def active(self) -> bool:
        return self.exclude_weekends or self.exclude_holidays

    def counts(self, day: date) -> bool:
        if self.exclude_weekends and day.weekday() >= 5:
            return False
        return not (self.exclude_holidays and day in french_holidays(day.year))

    def _local_days(self, start: datetime, end: datetime) -> list[date]:
        zone = ZoneInfo(self.tz)
        first = start.astimezone(zone).date()
        last = (end - timedelta(microseconds=1)).astimezone(zone).date()
        return [first + timedelta(days=i) for i in range((last - first).days + 1)]

    def days(self, start: datetime, end: datetime) -> list[date]:
        """Counted local dates touched by [start, end)."""
        return [d for d in self._local_days(start, end) if self.counts(d)]

    def excluded_ranges(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """[from, to) instants of the excluded local days within [start, end],
        consecutive days merged (a weekend is one range)."""
        if not self.active or end <= start:
            return []
        zone = ZoneInfo(self.tz)
        ranges: list[tuple[datetime, datetime]] = []
        for day in self._local_days(start, end):
            if self.counts(day):
                continue
            # Midnight to midnight in local time: a DST day lasts 23 or 25 hours.
            low = datetime.combine(day, time(), zone)
            high = datetime.combine(day + timedelta(days=1), time(), zone)
            if ranges and ranges[-1][1] == low:
                ranges[-1] = (ranges[-1][0], high)
            else:
                ranges.append((low, high))
        return [(max(low, start), min(high, end)) for low, high in ranges]

    def query_filter(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """A `bool.filter` clause leaving the excluded days out; empty when none."""
        ranges = self.excluded_ranges(start, end)
        if not ranges:
            return []
        return [
            {
                "bool": {
                    "must_not": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": low.isoformat(),
                                    "lt": high.isoformat(),
                                }
                            }
                        }
                        for low, high in ranges
                    ]
                }
            }
        ]


ALL_DAYS = CountedDays()

# Query parameters shared by the presets router and the export.
EXCLUDE_WEEKENDS_QUERY: Any = Query(
    default=False,
    description="Leave Saturdays and Sundays (local days in `tz`) out of every indicator.",
)
EXCLUDE_HOLIDAYS_QUERY: Any = Query(
    default=False,
    description="Leave French public holidays (local days in `tz`) out of every indicator.",
)


def check_time_zone(tz: str) -> None:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise HTTPException(
            status_code=400, detail=f"unknown time zone {tz!r}"
        ) from None


def counted_days(
    exclude_weekends: bool, exclude_holidays: bool, tz: str, period: timedelta
) -> CountedDays:
    days = CountedDays(
        exclude_weekends=exclude_weekends, exclude_holidays=exclude_holidays, tz=tz
    )
    if days.active and period > MAX_PERIOD:
        raise HTTPException(
            status_code=400,
            detail="excluding days needs a period of at most four years",
        )
    return days
