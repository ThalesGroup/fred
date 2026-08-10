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

"""Offline tests for the shared HMAC capability token (CONTENT-URL-STRATEGY)."""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from fred_core.store.signed_token import (
    MissingSigningSecretError,
    make_signed_token,
    read_signing_secret,
    token_expiry,
    verify_signed_token,
)

# Fake key: no real signing material is involved in these tests.
SECRET = "unit-test-signing-key"  # nosec B105  # pragma: allowlist secret
KEY = "doc-1/output/media/diagram.png"
T0 = 1_000_000  # fixed "now" so tests never depend on the wall clock


def test_round_trip_valid_within_ttl():
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    assert verify_signed_token(token, [KEY], secret=SECRET, now=T0 + 59) is True


def test_expired_token_is_rejected():
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    assert verify_signed_token(token, [KEY], secret=SECRET, now=T0 + 61) is False


def test_token_for_another_key_is_rejected():
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    assert verify_signed_token(token, ["other/key.png"], secret=SECRET, now=T0) is False


def test_extended_expiry_is_rejected():
    """The expiry is inside the signed payload, so stretching it breaks the signature."""
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    _expiry, signature = token.split(".", 1)
    forged = f"{T0 + 86400}.{signature}"
    assert verify_signed_token(forged, [KEY], secret=SECRET, now=T0) is False


def test_tampered_signature_is_rejected():
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    expiry, _signature = token.split(".", 1)
    assert (
        verify_signed_token(f"{expiry}.deadbeef", [KEY], secret=SECRET, now=T0) is False
    )


def test_token_minted_with_another_secret_is_rejected():
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    assert verify_signed_token(token, [KEY], secret="another-key", now=T0) is False  # nosec B106  # pragma: allowlist secret


@pytest.mark.parametrize("bad", ["", "garbage", "no-dot-here", "x.y", "999"])
def test_malformed_tokens_are_rejected(bad: str):
    assert verify_signed_token(bad, [KEY], secret=SECRET, now=T0) is False


def test_wire_format_is_expiry_dot_signature_over_pipe_joined_payload():
    """Pin the format: `/fs/download` links minted before this helper existed still verify."""
    token = make_signed_token(
        ["some/path.xlsx", "alice"], secret=SECRET, ttl_seconds=600, now=T0
    )
    expiry_str, signature = token.split(".", 1)
    expected_payload = f"some/path.xlsx|alice|{T0 + 600}"
    expected = (
        base64.urlsafe_b64encode(
            hmac.new(
                SECRET.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256
            ).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    assert expiry_str == str(T0 + 600)
    assert signature == expected


def test_token_expiry_reads_the_expiry_component():
    token = make_signed_token([KEY], secret=SECRET, ttl_seconds=60, now=T0)
    assert token_expiry(token) == T0 + 60
    assert token_expiry("garbage") is None


def test_read_signing_secret_returns_the_configured_value(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FRED_TEST_SIGNING_SECRET", "from-env")
    assert read_signing_secret("FRED_TEST_SIGNING_SECRET") == "from-env"


def test_read_signing_secret_raises_naming_the_variable_and_the_file(
    monkeypatch: pytest.MonkeyPatch,
):
    """No development fallback key (RFC §6.2): the error must be actionable."""
    monkeypatch.delenv("FRED_TEST_SIGNING_SECRET", raising=False)
    with pytest.raises(MissingSigningSecretError) as excinfo:
        read_signing_secret("FRED_TEST_SIGNING_SECRET")
    message = str(excinfo.value)
    assert "FRED_TEST_SIGNING_SECRET" in message
    assert "config/.env" in message
    assert "config/.env.template" in message
