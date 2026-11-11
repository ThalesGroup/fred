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

"""Fake KPI store and helpers for the analytics section preset tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fred_core import KeycloakUser

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 10, 8, tzinfo=timezone.utc)
PREVIOUS_SINCE = datetime(2026, 9, 24, tzinfo=timezone.utc)
USER = KeycloakUser(uid="alice", username="alice", roles=[], email=None)
TEAM_TERMS = {"terms": {"dims.team_id": ["a", "b"]}}


class FakeKpiStore:
    """Records every search body. Answers by the body's top-level agg name, which
    stays right when a preset runs its searches concurrently; else `{}`."""

    index = "kpi"

    def __init__(self, **responses: dict[str, Any]) -> None:
        self.bodies: list[dict[str, Any]] = []
        self._responses = responses
        self.client = self

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        del index
        self.bodies.append(body)
        return self._responses.get(next(iter(body.get("aggs", {})), ""), {})

    def body(self, agg: str = "periods") -> dict[str, Any]:
        return next(b for b in self.bodies if agg in b.get("aggs", {}))

    def filters(self, agg: str = "periods") -> list[dict[str, Any]]:
        return self.body(agg)["query"]["bool"]["filter"]


def periods(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """A response of a two-period body."""
    return {
        "aggregations": {
            "periods": {"buckets": {"current": current, "previous": previous}}
        }
    }


def value(v: float) -> dict[str, Any]:
    return {"value": v}


def model(
    name: str, input_tokens: float, output_tokens: float, **extra: Any
) -> dict[str, Any]:
    return {
        "key": name,
        "input": value(input_tokens),
        "output": value(output_tokens),
        "cached": value(0),
        **extra,
    }
