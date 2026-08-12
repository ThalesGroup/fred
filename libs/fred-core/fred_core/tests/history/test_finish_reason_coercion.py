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
Offline unit test: FinishReason normalization (ChatMetadata.finish_reason).

Providers report why a model call ended under different keys and vocabularies
(OpenAI: "stop"/"length"; Anthropic: response_metadata["stop_reason"] =
"end_turn"/"tool_use"; Gemini/Vertex: "STOP"/"MAX_TOKENS", or "UNKNOWN_<n>" for
an enum value the installed SDK doesn't recognize). This pins two things:
- every known provider value maps to the right Fred-owned FinishReason
- an unrecognized value (a new provider, a new SDK enum, or a row persisted
  before this normalization existed) coerces to `other` instead of raising —
  this is what keeps old history rows loadable.
"""

from __future__ import annotations

import pytest
from fred_core.history.history_schema import (
    ChatMetadata,
    FinishReason,
    coerce_finish_reason,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        # OpenAI
        ("stop", FinishReason.stop),
        ("length", FinishReason.length),
        ("content_filter", FinishReason.content_filter),
        ("tool_calls", FinishReason.tool_calls),
        ("function_call", FinishReason.tool_calls),  # OpenAI legacy
        # Anthropic (response_metadata["stop_reason"])
        ("end_turn", FinishReason.stop),
        ("stop_sequence", FinishReason.stop),
        ("max_tokens", FinishReason.length),
        ("tool_use", FinishReason.tool_calls),
        # Gemini / Vertex — uppercase, different vocabulary
        ("STOP", FinishReason.stop),
        ("MAX_TOKENS", FinishReason.length),
        ("SAFETY", FinishReason.content_filter),
        ("RECITATION", FinishReason.content_filter),
        # Fred's own synthetic value (agent_app.py, execution_error path)
        ("error", FinishReason.error),
        # Already-canonical value round-trips unchanged
        (FinishReason.tool_calls, FinishReason.tool_calls),
    ],
)
def test_coerce_finish_reason_maps_known_provider_values(
    raw: object, expected: FinishReason
) -> None:
    assert coerce_finish_reason(raw) is expected


def test_coerce_finish_reason_falls_back_to_other_for_unknown_values() -> None:
    # A Gemini/Vertex SDK's own fallback for an enum value it doesn't recognize.
    assert coerce_finish_reason("UNKNOWN_7") is FinishReason.other
    # Any other unrecognized provider string.
    assert coerce_finish_reason("some_future_provider_value") is FinishReason.other


def test_coerce_finish_reason_passes_none_through() -> None:
    assert coerce_finish_reason(None) is None


def test_chat_metadata_normalizes_finish_reason_on_construction() -> None:
    metadata = ChatMetadata(finish_reason="STOP")  # type: ignore[arg-type]
    assert metadata.finish_reason is FinishReason.stop


def test_chat_metadata_coerces_a_legacy_raw_value_instead_of_raising() -> None:
    # Simulates a row persisted before this normalization existed, with a raw
    # provider string straight in the JSON column — must load, never crash.
    metadata = ChatMetadata.model_validate({"finish_reason": "tool_use"})
    assert metadata.finish_reason is FinishReason.tool_calls

    metadata = ChatMetadata.model_validate(
        {"finish_reason": "some_totally_unknown_value"}
    )
    assert metadata.finish_reason is FinishReason.other
