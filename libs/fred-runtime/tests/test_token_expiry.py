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
Offline unit tests for fred_runtime.common.token_expiry.

All tests are pure — no network, no external services.
httpx objects are constructed directly; no mocking framework needed.
"""

from __future__ import annotations

import httpx

from fred_runtime.common.token_expiry import (
    _is_expired_body,
    _is_expired_www_authenticate,
    is_expired_httpx_response,
    is_expired_httpx_status_error,
    unwrap_httpx_status_error,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int,
    *,
    body: str = "",
    www_authenticate: str | None = None,
) -> httpx.Response:
    headers: dict[str, str] = {}
    if www_authenticate is not None:
        headers["www-authenticate"] = www_authenticate
    return httpx.Response(
        status_code=status_code,
        text=body,
        headers=headers,
    )


def _make_status_error(
    status_code: int,
    *,
    body: str = "",
    www_authenticate: str | None = None,
) -> httpx.HTTPStatusError:
    response = _make_response(status_code, body=body, www_authenticate=www_authenticate)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=httpx.Request("GET", "http://example.com"),
        response=response,
    )


# ---------------------------------------------------------------------------
# _is_expired_www_authenticate
# ---------------------------------------------------------------------------


class TestIsExpiredWwwAuthenticate:
    def test_none_returns_false(self) -> None:
        assert _is_expired_www_authenticate(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert _is_expired_www_authenticate("") is False

    def test_exact_token_expired(self) -> None:
        assert _is_expired_www_authenticate("Bearer token expired") is True

    def test_case_insensitive(self) -> None:
        assert _is_expired_www_authenticate("Bearer TOKEN EXPIRED") is True

    def test_expired_and_token_keywords(self) -> None:
        assert (
            _is_expired_www_authenticate("error=invalid_token, token has expired")
            is True
        )

    def test_expired_without_token_returns_false(self) -> None:
        assert _is_expired_www_authenticate("session expired") is False

    def test_token_without_expired_returns_false(self) -> None:
        assert _is_expired_www_authenticate("Bearer token realm=example") is False

    def test_unrelated_header_returns_false(self) -> None:
        assert _is_expired_www_authenticate("Basic realm=example") is False


# ---------------------------------------------------------------------------
# _is_expired_body
# ---------------------------------------------------------------------------


class TestIsExpiredBody:
    def test_none_returns_false(self) -> None:
        assert _is_expired_body(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert _is_expired_body("") is False

    def test_token_has_expired(self) -> None:
        assert _is_expired_body('{"error": "token has expired"}') is True

    def test_token_expired_phrase(self) -> None:
        assert _is_expired_body("token expired, please re-authenticate") is True

    def test_case_insensitive(self) -> None:
        assert _is_expired_body("TOKEN HAS EXPIRED") is True

    def test_expired_and_token_keywords(self) -> None:
        assert _is_expired_body("your access token is expired") is True

    def test_expired_without_token_returns_false(self) -> None:
        assert _is_expired_body("session expired") is False

    def test_unrelated_body_returns_false(self) -> None:
        assert _is_expired_body('{"error": "unauthorized"}') is False


# ---------------------------------------------------------------------------
# unwrap_httpx_status_error
# ---------------------------------------------------------------------------


class TestUnwrapHttpxStatusError:
    def test_direct_status_error(self) -> None:
        err = _make_status_error(401)
        assert unwrap_httpx_status_error(err) is err

    def test_returns_none_for_generic_exception(self) -> None:
        assert unwrap_httpx_status_error(ValueError("nope")) is None

    def test_finds_cause(self) -> None:
        http_err = _make_status_error(401)
        wrapper = RuntimeError("wrapper")
        wrapper.__cause__ = http_err
        assert unwrap_httpx_status_error(wrapper) is http_err

    def test_finds_context(self) -> None:
        http_err = _make_status_error(401)
        wrapper = RuntimeError("wrapper")
        wrapper.__context__ = http_err
        assert unwrap_httpx_status_error(wrapper) is http_err

    def test_finds_nested_in_exception_group(self) -> None:
        http_err = _make_status_error(401)
        group = ExceptionGroup("group", [ValueError("other"), http_err])
        assert unwrap_httpx_status_error(group) is http_err

    def test_does_not_loop_on_circular_cause(self) -> None:
        err_a = ValueError("a")
        err_b = ValueError("b")
        err_a.__cause__ = err_b  # type: ignore[assignment]
        err_b.__cause__ = err_a  # type: ignore[assignment]
        assert unwrap_httpx_status_error(err_a) is None

    def test_deeply_nested_cause(self) -> None:
        http_err = _make_status_error(401)
        level3 = RuntimeError("l3")
        level3.__cause__ = http_err
        level2 = RuntimeError("l2")
        level2.__cause__ = level3
        level1 = RuntimeError("l1")
        level1.__cause__ = level2
        assert unwrap_httpx_status_error(level1) is http_err


# ---------------------------------------------------------------------------
# is_expired_httpx_status_error
# ---------------------------------------------------------------------------


class TestIsExpiredHttpxStatusError:
    def test_401_with_expired_body(self) -> None:
        err = _make_status_error(401, body='{"error": "token expired"}')
        assert is_expired_httpx_status_error(err) is True

    def test_401_with_expired_www_authenticate(self) -> None:
        err = _make_status_error(401, www_authenticate="Bearer token expired")
        assert is_expired_httpx_status_error(err) is True

    def test_401_without_expiry_signal(self) -> None:
        err = _make_status_error(401, body='{"error": "unauthorized"}')
        assert is_expired_httpx_status_error(err) is False

    def test_403_with_expired_body_returns_false(self) -> None:
        err = _make_status_error(403, body="token expired")
        assert is_expired_httpx_status_error(err) is False

    def test_200_returns_false(self) -> None:
        err = _make_status_error(200)
        assert is_expired_httpx_status_error(err) is False


# ---------------------------------------------------------------------------
# is_expired_httpx_response
# ---------------------------------------------------------------------------


class TestIsExpiredHttpxResponse:
    def test_none_returns_false(self) -> None:
        assert is_expired_httpx_response(None) is False

    def test_401_with_expired_body(self) -> None:
        resp = _make_response(401, body="token has expired")
        assert is_expired_httpx_response(resp) is True

    def test_401_with_expired_www_authenticate(self) -> None:
        resp = _make_response(401, www_authenticate="token expired")
        assert is_expired_httpx_response(resp) is True

    def test_401_no_expiry_signal(self) -> None:
        resp = _make_response(401, body='{"detail": "bad credentials"}')
        assert is_expired_httpx_response(resp) is False

    def test_500_returns_false(self) -> None:
        resp = _make_response(500, body="token expired")
        assert is_expired_httpx_response(resp) is False
