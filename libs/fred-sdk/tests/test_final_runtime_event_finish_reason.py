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
Offline unit test: `FinalRuntimeEvent.finish_reason` — the live SSE contract
must normalize a raw provider finish-reason value the same way `ChatMetadata`
(fred-core, persisted history) does, and — being a frozen, `extra="forbid"`
model — must never fail construction over a value this build doesn't
recognize.
"""

from __future__ import annotations

from fred_core.history.history_schema import FinishReason
from fred_sdk.contracts.runtime import FinalRuntimeEvent


def test_final_runtime_event_normalizes_a_raw_provider_value() -> None:
    event = FinalRuntimeEvent.model_validate({"kind": "final", "finish_reason": "STOP"})
    assert event.finish_reason is FinishReason.stop


def test_final_runtime_event_coerces_an_unrecognized_value_to_other() -> None:
    event = FinalRuntimeEvent.model_validate(
        {"kind": "final", "finish_reason": "UNKNOWN_7"}
    )
    assert event.finish_reason is FinishReason.other


def test_final_runtime_event_finish_reason_defaults_to_none() -> None:
    event = FinalRuntimeEvent.model_validate({"kind": "final"})
    assert event.finish_reason is None
