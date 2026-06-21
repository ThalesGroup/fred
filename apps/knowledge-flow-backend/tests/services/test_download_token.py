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

"""Offline tests for the signed `/fs/download` token (FILES-04, RFC §7.3)."""

import pytest

from knowledge_flow_backend.features.filesystem.download_token import (
    make_download_token,
    verify_download_token,
)

PATH = "teams/fredlab/users/alice/uploads/report.xlsx"
UID = "alice"
T0 = 1_000_000  # fixed "now" so tests never depend on the wall clock


def test_round_trip_valid_within_ttl():
    token = make_download_token(PATH, UID, ttl_seconds=600, now=T0)
    assert verify_download_token(token, PATH, UID, now=T0 + 599) is True


def test_expired_token_is_rejected():
    token = make_download_token(PATH, UID, ttl_seconds=600, now=T0)
    assert verify_download_token(token, PATH, UID, now=T0 + 601) is False


def test_wrong_path_is_rejected():
    token = make_download_token(PATH, UID, ttl_seconds=600, now=T0)
    assert verify_download_token(token, PATH + ".other", UID, now=T0) is False


def test_wrong_uid_is_rejected():
    token = make_download_token(PATH, UID, ttl_seconds=600, now=T0)
    assert verify_download_token(token, PATH, "bob", now=T0) is False


def test_tampered_signature_is_rejected():
    token = make_download_token(PATH, UID, ttl_seconds=600, now=T0)
    expiry, _signature = token.split(".", 1)
    assert verify_download_token(f"{expiry}.deadbeef", PATH, UID, now=T0) is False


@pytest.mark.parametrize("bad", ["", "garbage", "no-dot-here", "x.y", "999"])
def test_malformed_tokens_are_rejected(bad: str):
    assert verify_download_token(bad, PATH, UID, now=T0) is False


def test_signing_key_is_honoured(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_FLOW_DOWNLOAD_SECRET", "key-one")
    token = make_download_token(PATH, UID, ttl_seconds=600, now=T0)
    assert verify_download_token(token, PATH, UID, now=T0) is True
    # A different signing key must invalidate a token minted under the previous one.
    monkeypatch.setenv("KNOWLEDGE_FLOW_DOWNLOAD_SECRET", "key-two")
    assert verify_download_token(token, PATH, UID, now=T0) is False
