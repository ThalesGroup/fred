# Copyright Thales 2025
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

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fred_runtime.runtime_support.user_token_refresher import (
    refresh_user_access_token_from_keycloak,
)


def _make_httpx_status_error(
    status_code: int, body: str = "error"
) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://keycloak/token")
    response = httpx.Response(status_code, text=body, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


def _make_success_response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json = MagicMock(return_value=payload)
    return mock


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_returns_new_token_on_success():
    payload = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 300,
    }
    with patch("httpx.post", return_value=_make_success_response(payload)):
        result = refresh_user_access_token_from_keycloak(
            "http://keycloak/realms/test", "client-id", "old-refresh"
        )
    assert result["access_token"] == "new-access"
    assert result["refresh_token"] == "new-refresh"


def test_adds_expires_at_timestamp():
    payload = {"access_token": "tok", "expires_in": 60}
    before = time.time()
    with patch("httpx.post", return_value=_make_success_response(payload)):
        result = refresh_user_access_token_from_keycloak(
            "http://keycloak/realms/test", "client-id", "old-refresh"
        )
    after = time.time()
    expires_at = result["expires_at_timestamp"]
    assert isinstance(expires_at, float)
    # Should be ~55s from now (expires_in=60, minus 5s safety buffer)
    assert before + 50 <= expires_at <= after + 60


def test_expires_at_never_negative_when_expires_in_is_zero():
    payload = {"access_token": "tok", "expires_in": 0}
    with patch("httpx.post", return_value=_make_success_response(payload)):
        result = refresh_user_access_token_from_keycloak(
            "http://keycloak/realms/test", "client-id", "old-refresh"
        )
    expires_at = result["expires_at_timestamp"]
    assert isinstance(expires_at, float)
    assert expires_at >= time.time() - 1


def test_token_url_built_correctly():
    payload = {"access_token": "tok", "expires_in": 300}
    with patch("httpx.post", return_value=_make_success_response(payload)) as mock_post:
        refresh_user_access_token_from_keycloak(
            "http://keycloak/realms/test/",  # trailing slash must be stripped
            "my-client",
            "old-refresh",
        )
    called_url = mock_post.call_args[0][0]
    assert called_url == "http://keycloak/realms/test/protocol/openid-connect/token"
    form = mock_post.call_args[1]["data"]
    assert form["grant_type"] == "refresh_token"
    assert form["client_id"] == "my-client"
    assert form["refresh_token"] == "old-refresh"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_runtime_error_on_401():
    err = _make_httpx_status_error(401, "invalid_grant")
    with patch("httpx.post", side_effect=err):
        with pytest.raises(RuntimeError, match="Token refresh failed"):
            refresh_user_access_token_from_keycloak(
                "http://keycloak/realms/test", "client-id", "expired-refresh"
            )


def test_raises_runtime_error_on_500():
    err = _make_httpx_status_error(500, "Internal Server Error")
    with patch("httpx.post", side_effect=err):
        with pytest.raises(RuntimeError, match="Token refresh failed"):
            refresh_user_access_token_from_keycloak(
                "http://keycloak/realms/test", "client-id", "tok"
            )


def test_error_message_includes_response_body():
    err = _make_httpx_status_error(400, "session_not_active")
    with patch("httpx.post", side_effect=err):
        with pytest.raises(RuntimeError) as exc_info:
            refresh_user_access_token_from_keycloak(
                "http://keycloak/realms/test", "client-id", "tok"
            )
    assert "session_not_active" in str(exc_info.value)
