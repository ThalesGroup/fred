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

"""The one translation of a downstream HTTP status into a tool failure code."""

from __future__ import annotations

import pytest
from fred_core.history.history_schema import (
    ToolFailure,
    ToolFailureCode,
    ToolResultPart,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, ToolFailureCode.invalid_arguments),
        (422, ToolFailureCode.invalid_arguments),
        (409, ToolFailureCode.invalid_arguments),
        (401, ToolFailureCode.authentication_required),
        (403, ToolFailureCode.resource_unavailable),
        (404, ToolFailureCode.resource_unavailable),
        (408, ToolFailureCode.timeout),
        (429, ToolFailureCode.rate_limited),
        (500, ToolFailureCode.service_error),
        (502, ToolFailureCode.service_error),
        (599, ToolFailureCode.service_error),
        (503, ToolFailureCode.service_busy),
        (504, ToolFailureCode.timeout),
        (302, ToolFailureCode.unexpected),
        (None, ToolFailureCode.unexpected),
    ],
)
def test_status_maps_to_one_code_and_keeps_the_status(
    status: int | None, code: ToolFailureCode
) -> None:
    assert ToolFailure.from_http_status(status) == ToolFailure(code=code, status=status)


@pytest.mark.parametrize("status", [None, 500])
def test_a_timeout_wins_over_the_status(status: int | None) -> None:
    failure = ToolFailure.from_http_status(status, timed_out=True)
    assert failure == ToolFailure(code=ToolFailureCode.timeout, status=status)


def test_the_vocabulary_is_closed_on_the_wire() -> None:
    with pytest.raises(ValidationError):
        ToolFailure.model_validate({"code": "SERVICE_ERROR: something"})


def test_a_tool_result_part_carries_its_failure_and_none_on_success() -> None:
    failed = ToolResultPart(
        call_id="c1", content="", failure=ToolFailure.from_http_status(500)
    )
    assert failed.model_dump(mode="json")["failure"] == {
        "code": "service_error",
        "status": 500,
        "origin": None,
        "setting": None,
    }
    assert ToolResultPart(call_id="c2", content="ok").failure is None
