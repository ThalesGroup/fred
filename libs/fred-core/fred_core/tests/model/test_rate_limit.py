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
Tests for `is_rate_limit` — the one 429 detector both retry sites share.

Providers surface throttling in different shapes, so each shape that has been
seen in production gets a case here.
"""

from __future__ import annotations

from fred_core import is_rate_limit


class _Response:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _WithStatusAttr(Exception):
    status_code = 429


class _WithResponse(Exception):
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        super().__init__("throttled")
        self.response = _Response(429, headers)


class RateLimitError(Exception):
    """Named like the provider SDK classes — detection falls back to the name."""


def test_a_status_code_attribute_is_detected() -> None:
    assert is_rate_limit(_WithStatusAttr())[0] is True


def test_a_status_code_on_the_response_is_detected() -> None:
    assert is_rate_limit(_WithResponse())[0] is True


def test_the_exception_type_name_is_detected() -> None:
    assert is_rate_limit(RateLimitError("slow down"))[0] is True


def test_the_mistral_message_shape_is_detected() -> None:
    """The live incident: Mistral through the OpenAI-compatible client."""

    exc = Exception(
        "Error code: 429 - {'object': 'error', 'message': 'Rate limit exceeded', "
        "'type': 'rate_limited', 'code': '1300', 'raw_status_code': 429}"
    )
    assert is_rate_limit(exc)[0] is True


def test_an_unrelated_failure_is_not_a_rate_limit() -> None:
    assert is_rate_limit(ValueError("boom"))[0] is False
    assert is_rate_limit(Exception("connection reset by peer"))[0] is False


def test_a_retry_after_header_is_returned_in_seconds() -> None:
    assert is_rate_limit(_WithResponse({"Retry-After": "12"}))[1] == 12.0
    assert is_rate_limit(_WithResponse({"retry-after": "0.5"}))[1] == 0.5


def test_an_unusable_retry_after_is_ignored() -> None:
    """A date-format `Retry-After` is valid HTTP but not a float; the caller
    falls back to its own backoff rather than crashing on it."""

    assert (
        is_rate_limit(_WithResponse({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}))[
            1
        ]
        is None
    )
    assert is_rate_limit(_WithResponse())[1] is None
