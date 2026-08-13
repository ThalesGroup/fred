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
"""Chat-input limit semantics independent of the HTTP route wiring."""

from __future__ import annotations

import pytest
from fred_runtime.app.chat_input_limit import (
    runtime_request_chat_char_count,
    validate_chat_text,
    validate_runtime_request,
)
from fred_sdk.contracts.execution import RuntimeExecuteRequest


@pytest.mark.parametrize("text", ["abcde", "界界界界界", "🙂🙂🙂🙂🙂"])
def test_validate_chat_text_counts_unicode_code_points(text: str) -> None:
    """ASCII, CJK, and non-BMP emoji share the same five-code-point boundary."""

    assert validate_chat_text(text, 5) is None
    violation = validate_chat_text(f"{text}x", 5)
    assert violation is not None
    assert violation.actual_chars == 6


@pytest.mark.parametrize(
    ("resume_payload", "expected"),
    [
        ("hello", 5),
        ({"choice_id": "ab"}, 2),
        ({"answer": "界界界"}, 3),
        ({"text": "🙂🙂🙂🙂"}, 4),
        ({"choice_id": "a", "answer": "bc", "text": "def"}, 6),
        ({"notes": "ignored", "nested": {"text": "ignored"}}, 0),
    ],
)
def test_runtime_request_counts_supported_hitl_text(
    resume_payload: object, expected: int
) -> None:
    """HITL counting covers canonical fields without traversing arbitrary JSON."""

    request = RuntimeExecuteRequest(agent_id="test", resume_payload=resume_payload)

    assert runtime_request_chat_char_count(request) == expected


def test_runtime_request_uses_input_only_for_ordinary_turns() -> None:
    request = RuntimeExecuteRequest(agent_id="test", input="🙂界abc")

    assert runtime_request_chat_char_count(request) == 5
    assert validate_runtime_request(request, 5) is None
    assert validate_runtime_request(request, 4) is not None


@pytest.mark.parametrize(
    "resume_payload",
    [
        "🙂" * 6,
        {"choice_id": "界" * 6},
        {"answer": "a" * 6},
        {"text": "🙂" * 6},
        {"choice_id": "ab", "answer": "界界", "text": "🙂🙂"},
    ],
)
def test_runtime_request_rejects_each_supported_hitl_shape(
    resume_payload: object,
) -> None:
    request = RuntimeExecuteRequest(agent_id="test", resume_payload=resume_payload)

    violation = validate_runtime_request(request, 5)

    assert violation is not None
    assert violation.actual_chars == 6
