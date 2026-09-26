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
Contract tests for the terminal error event's `reason`.

The field is additive: a client that has never heard of it keeps working, and a
payload written before it existed still validates.
"""

from __future__ import annotations

import pytest
from fred_sdk.contracts.runtime import (
    RuntimeErrorEvent,
    RuntimeEventKind,
    RuntimeStopReason,
)
from pydantic import TypeAdapter, ValidationError


def test_reason_is_optional_and_absent_by_default() -> None:
    event = RuntimeErrorEvent(message="boom")

    assert event.reason is None
    assert event.kind is RuntimeEventKind.EXECUTION_ERROR


def test_payload_without_reason_still_validates() -> None:
    # The shape every consumer wrote against before the field existed.
    event = RuntimeErrorEvent.model_validate(
        {"kind": "execution_error", "sequence": 3, "message": "boom"}
    )

    assert event.reason is None


@pytest.mark.parametrize(
    "value",
    [
        "authority_lost",
        "cancelled",
        "delegation_unavailable",
    ],
)
def test_every_declared_reason_round_trips(value: str) -> None:
    event = RuntimeErrorEvent.model_validate(
        {"kind": "execution_error", "message": "stopped", "reason": value}
    )

    assert event.reason is RuntimeStopReason(value)
    assert event.model_dump(mode="json")["reason"] == value


def test_reason_enum_covers_exactly_the_declared_values() -> None:
    assert {reason.value for reason in RuntimeStopReason} == {
        "authority_lost",
        "cancelled",
        "delegation_unavailable",
    }


def test_unknown_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RuntimeErrorEvent.model_validate(
            {"kind": "execution_error", "message": "stopped", "reason": "whatever"}
        )


def test_reason_travels_through_the_discriminated_event_union() -> None:
    from fred_sdk.contracts.runtime import RuntimeEvent

    adapter = TypeAdapter(RuntimeEvent)
    event = adapter.validate_python(
        {
            "kind": "execution_error",
            "message": "stopped",
            "reason": "authority_lost",
        }
    )

    assert isinstance(event, RuntimeErrorEvent)
    assert event.reason is RuntimeStopReason.AUTHORITY_LOST
