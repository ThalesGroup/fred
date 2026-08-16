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
"""Field-aware chat-input length validation shared by runtime HTTP surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fred_sdk.contracts.execution import RuntimeExecuteRequest

CHAT_INPUT_TOO_LONG_CODE = "chat_input_too_long"
_HITL_TEXT_FIELDS = ("choice_id", "answer", "text")


@dataclass(frozen=True, slots=True)
class ChatInputTooLong:
    """Safe error data for an oversized submitted message.

    The rejected text is deliberately not retained on this object, so logging
    or serializing the validation result cannot accidentally echo user content.
    """

    limit_chars: int
    actual_chars: int

    @property
    def message(self) -> str:
        return f"Your message exceeds the {self.limit_chars:,}-character limit."

    def native_detail(self) -> dict[str, str | int]:
        """Return the Fred-native ``HTTPException.detail`` payload."""

        return {
            "code": CHAT_INPUT_TOO_LONG_CODE,
            "message": self.message,
            "limit_chars": self.limit_chars,
            "actual_chars": self.actual_chars,
        }

    def openai_error(self) -> dict[str, str | int]:
        """Return the OpenAI-compatible ``error`` object."""

        return {
            "message": self.message,
            "type": "invalid_request_error",
            "param": "messages",
            "code": CHAT_INPUT_TOO_LONG_CODE,
            "limit_chars": self.limit_chars,
            "actual_chars": self.actual_chars,
        }


def validate_chat_text(text: str, max_chars: int) -> ChatInputTooLong | None:
    """Validate one string using Python's Unicode-code-point semantics."""

    actual_chars = len(text)
    if actual_chars <= max_chars:
        return None
    return ChatInputTooLong(limit_chars=max_chars, actual_chars=actual_chars)


def runtime_request_chat_char_count(request: RuntimeExecuteRequest) -> int:
    """Count the user-authored chat text that this runtime request submits.

    Ordinary turns count ``input``. A HITL resume counts a bare string or the
    combined string values of the canonical ``choice_id``, ``answer``, and
    ``text`` fields. Values are summed per field without deduplication: callers
    may use either ``choice_id`` or ``answer`` for a selection, and managed chat
    currently mirrors the identifier in both. Arbitrary JSON keys are
    intentionally not traversed.
    """

    resume_payload: Any = request.resume_payload
    if resume_payload is None:
        return len(request.input)
    if isinstance(resume_payload, str):
        return len(resume_payload)
    if isinstance(resume_payload, Mapping):
        return sum(
            len(value)
            for key in _HITL_TEXT_FIELDS
            if isinstance((value := resume_payload.get(key)), str)
        )
    return 0


def validate_runtime_request(
    request: RuntimeExecuteRequest,
    max_chars: int,
) -> ChatInputTooLong | None:
    """Validate the effective ordinary-turn or HITL text in one request."""

    actual_chars = runtime_request_chat_char_count(request)
    if actual_chars <= max_chars:
        return None
    return ChatInputTooLong(limit_chars=max_chars, actual_chars=actual_chars)
