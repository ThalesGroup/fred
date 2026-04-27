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

import json
import logging

import pytest

from fred_core.kpi.kpi_writer_structures import KPIEvent, Metric, Quantities
from fred_core.kpi.log_kpi_store import KpiLogStore


@pytest.fixture()
def store() -> KpiLogStore:
    return KpiLogStore(level="debug")


def _make_event(name: str, **quantities_kwargs: int) -> KPIEvent:
    return KPIEvent(
        metric=Metric(name=name, type="timer", value=1.0),
        quantities=Quantities(**quantities_kwargs) if quantities_kwargs else None,
    )


def test_index_event_logs_structured_json_for_turn_completed(
    store: KpiLogStore, caplog: pytest.LogCaptureFixture
) -> None:
    """index_event must emit a structured JSON line for agent.turn_completed."""
    with caplog.at_level(logging.INFO, logger="KPI"):
        store.index_event(
            _make_event(
                "agent.turn_completed", tool_count=3, input_tokens=120, output_tokens=40
            )
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message.removeprefix("[KPI] "))
    assert payload["event"] == "agent.turn_completed"
    assert payload["quantities"]["tool_count"] == 3
    assert payload["quantities"]["input_tokens"] == 120
    assert payload["quantities"]["output_tokens"] == 40


def test_index_event_logs_structured_json_for_turn_error(
    store: KpiLogStore, caplog: pytest.LogCaptureFixture
) -> None:
    """index_event must emit a structured JSON line for agent.turn_error_total."""
    with caplog.at_level(logging.INFO, logger="KPI"):
        store.index_event(_make_event("agent.turn_error_total"))

    assert len(caplog.records) == 1
    assert (
        json.loads(caplog.records[0].message.removeprefix("[KPI] "))["event"]
        == "agent.turn_error_total"
    )


def test_index_event_ignores_unknown_event_names(
    store: KpiLogStore, caplog: pytest.LogCaptureFixture
) -> None:
    """index_event must not log for unrecognised event names (avoids log spam)."""
    with caplog.at_level(logging.INFO, logger="KPI"):
        store.index_event(_make_event("agent.some_other_metric"))

    assert len(caplog.records) == 0
