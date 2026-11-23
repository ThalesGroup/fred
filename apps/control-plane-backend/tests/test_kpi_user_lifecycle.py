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

"""New users, activation and cohorts from per-user first events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from control_plane_backend.kpi.presets import user_lifecycle as lifecycle
from control_plane_backend.kpi.presets.analytics_common import Windows

UTC = timezone.utc
PARIS = ZoneInfo("Europe/Paris")
# October 2026, against September.
WINDOWS = Windows.of(
    datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 31, tzinfo=UTC)
)


def ms(moment: datetime) -> float:
    return moment.timestamp() * 1000


def user_bucket(
    user: str,
    first_seen: datetime,
    *,
    first_turn: datetime | None = None,
    current: int = 1,
    previous: int = 0,
    months: tuple[str, ...] = (),
    turn_months: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "key": {"user": user},
        "first_seen": {"value": ms(first_seen)},
        "first_turn": {"at": {"value": ms(first_turn) if first_turn else None}},
        "scoped": {
            "periods": {
                "buckets": {
                    "current": {"doc_count": current},
                    "previous": {"doc_count": previous},
                }
            },
            "recent": {
                "months": {
                    "buckets": [{"key_as_string": m, "doc_count": 1} for m in months]
                },
                "turns": {
                    "months": {
                        "buckets": [
                            {"key_as_string": m, "doc_count": 1} for m in turn_months
                        ]
                    }
                },
            },
        },
    }


class ScanStore:
    """Answers composite pages in order, the earliest-event probe and prior batches."""

    index = "kpi"

    def __init__(
        self,
        pages: list[list[dict[str, Any]]],
        *,
        earliest: datetime | None = None,
        prior: set[str] = frozenset(),  # type: ignore[assignment]
    ) -> None:
        self.client = self
        self.pages, self.earliest, self.prior = pages, earliest, prior
        self.bodies: list[dict[str, Any]] = []

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        del index
        self.bodies.append(body)
        if "sort" in body:
            hits = [{"sort": [ms(self.earliest)]}] if self.earliest else []
            return {"hits": {"hits": hits}}
        if "prior" in body.get("aggs", {}):
            ids = next(
                f["terms"]["dims.user_id"]
                for f in body["query"]["bool"]["filter"]
                if "terms" in f
            )
            keys = [{"key": i, "doc_count": 1} for i in ids if i in self.prior]
            return {"aggregations": {"prior": {"buckets": keys}}}
        composite = body["aggs"]["users"]["composite"]
        index_ = int(composite.get("after", {}).get("user", "0"))
        page = self.pages[index_] if index_ < len(self.pages) else []
        return {
            "aggregations": {
                "users": {
                    "buckets": page,
                    **({"after_key": {"user": str(index_ + 1)}} if page else {}),
                }
            }
        }

    def composite_bodies(self) -> list[dict[str, Any]]:
        return [b for b in self.bodies if "users" in b.get("aggs", {})]


async def run(store: ScanStore, team_ids: tuple[str, ...] = (), tz: str = "UTC"):
    return await lifecycle.user_lifecycle(cast(Any, store), WINDOWS, team_ids, tz)


def oct_(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


def test_cohort_months_follow_the_period_end_in_the_time_zone() -> None:
    assert lifecycle.cohort_months(WINDOWS.until, PARIS) == [
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    # 23:30 UTC on 31 December is already January in Paris.
    end = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
    assert lifecycle.cohort_months(end, PARIS)[-1] == "2027-01"
    assert lifecycle.cohort_months(end, ZoneInfo("UTC"))[-1] == "2026-12"
    assert lifecycle.shift_month("2026-11", 3) == "2027-02"


@pytest.mark.asyncio
async def test_no_data() -> None:
    result = await run(ScanStore([]))
    assert result.new_users.current == 0 and result.new_users.previous == 0
    assert result.first_message_within_7_days_rate.current is None
    assert result.median_days_to_first_message.current is None
    assert result.next_month_return.current is None
    assert [row.size for row in result.cohorts] == [0, 0, 0, 0, 0]
    assert all(r is None for row in result.cohorts for r in row.returns)


@pytest.mark.asyncio
async def test_single_new_user_activation() -> None:
    store = ScanStore([[user_bucket("u1", oct_(2), first_turn=oct_(3, 21))]])
    result = await run(store)

    assert result.new_users.current == 1
    assert result.first_message_within_7_days_rate.current == 1.0
    assert result.median_days_to_first_message.current == pytest.approx(1.5)
    # The window starts at the earliest event: no prior check needed.
    assert len(store.bodies) == 2


@pytest.mark.asyncio
async def test_follows_pages_and_marks_users_seen_before() -> None:
    page_one = [user_bucket(f"u{i}", oct_(5), first_turn=oct_(20)) for i in range(1000)]
    page_two = [user_bucket("late", oct_(30))]
    store = ScanStore(
        [page_one, page_two], earliest=datetime(2025, 1, 1, tzinfo=UTC), prior={"u0"}
    )
    result = await run(store)

    composites = store.composite_bodies()
    assert len(composites) == 2
    assert composites[1]["aggs"]["users"]["composite"]["after"] == {"user": "1"}
    # u0 came before the window: not new.
    assert result.new_users.current == 1000
    # 999 wrote after 15 days, "late" never did.
    assert result.first_message_within_7_days_rate.current == 0
    assert result.median_days_to_first_message.current == pytest.approx(15)
    prior_bodies = [b for b in store.bodies if "prior" in b.get("aggs", {})]
    assert [b["aggs"]["prior"]["terms"]["size"] for b in prior_bodies] == [1000, 1]


@pytest.mark.asyncio
async def test_period_boundaries() -> None:
    store = ScanStore(
        [
            [
                user_bucket("at-start", WINDOWS.since),
                user_bucket("at-end", WINDOWS.until),
                user_bucket("previous", WINDOWS.since - timedelta(seconds=1)),
            ]
        ]
    )
    result = await run(store)
    assert result.new_users.current == 2
    assert result.new_users.previous == 1


@pytest.mark.asyncio
async def test_cohorts_returns_and_next_month() -> None:
    store = ScanStore(
        [
            [
                # August cohort: one back in September and October, one never.
                user_bucket(
                    "a1",
                    datetime(2026, 8, 3, tzinfo=UTC),
                    turn_months=("2026-08", "2026-09", "2026-10"),
                ),
                user_bucket("a2", datetime(2026, 8, 9, tzinfo=UTC)),
                # September cohort: both back in October.
                user_bucket(
                    "s1", datetime(2026, 9, 2, tzinfo=UTC), turn_months=("2026-10",)
                ),
                user_bucket(
                    "s2", datetime(2026, 9, 9, tzinfo=UTC), turn_months=("2026-10",)
                ),
            ]
        ]
    )
    result = await run(store)
    rows = {row.month: row for row in result.cohorts}

    assert rows["2026-08"].size == 2
    assert rows["2026-08"].returns == [0.5, 0.5, None]
    assert rows["2026-09"].returns == [1.0, None, None]
    assert rows["2026-10"].returns == [None, None, None]
    assert rows["2026-06"].size == 0
    assert result.next_month_return.current == 1.0
    assert result.next_month_return.previous == 0.5


@pytest.mark.asyncio
async def test_team_scope_needs_an_event_in_the_selected_teams() -> None:
    store = ScanStore(
        [
            [
                user_bucket("in", oct_(2), current=3, months=("2026-10",)),
                user_bucket("out", oct_(2), current=0),
            ]
        ]
    )
    result = await run(store, team_ids=("a", "b"))

    assert result.new_users.current == 1
    assert result.cohorts[-1].size == 1
    scoped = store.composite_bodies()[0]["aggs"]["users"]["aggs"]["scoped"]
    assert scoped["filter"] == {
        "bool": {"filter": [{"terms": {"dims.team_id": ["a", "b"]}}]}
    }


@pytest.mark.asyncio
async def test_query_shape() -> None:
    store = ScanStore([])
    await run(store, tz="Europe/Paris")
    body = store.composite_bodies()[0]
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"dims.actor_type": "human"}} in filters
    window = next(f for f in filters if "range" in f)["range"]["@timestamp"]
    # Five cohort months back from October: the window opens on 1 June in Paris.
    assert window["gte"] == datetime(2026, 6, 1, tzinfo=PARIS).isoformat()
    assert body["aggs"]["users"]["composite"]["size"] == lifecycle.PAGE_SIZE
    months = body["aggs"]["users"]["aggs"]["scoped"]["aggs"]["recent"]["aggs"][
        "months"
    ]["date_histogram"]
    assert months["time_zone"] == "Europe/Paris" and months["calendar_interval"] == "1M"
    assert body["aggs"]["users"]["aggs"]["scoped"]["filter"] == {"match_all": {}}


@pytest.mark.asyncio
async def test_arrival_month_follows_the_time_zone() -> None:
    late_september_utc = datetime(2026, 9, 30, 22, 30, tzinfo=UTC)
    store = ScanStore([[user_bucket("u1", late_september_utc)]])
    paris = {
        row.month: row.size for row in (await run(store, tz="Europe/Paris")).cohorts
    }
    utc = {row.month: row.size for row in (await run(store)).cohorts}
    assert paris["2026-10"] == 1 and paris["2026-09"] == 0
    assert utc["2026-09"] == 1 and utc["2026-10"] == 0
