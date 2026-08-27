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

"""Offline tests for `ContentUrlResolver` (CONTENT-URL-STRATEGY)."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fred_core.store.content_url_resolver import ContentUrlResolver
from fred_core.store.signed_token import verify_signed_token

# Fake key: no real signing material is involved in these tests.
SECRET = "unit-test-signing-key"  # nosec B105  # pragma: allowlist secret
KEY = "teams/t1/banner.png"


class _FakeStore:
    """Records the presigned call so the `presigned` branch can be asserted exactly."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, timedelta]] = []

    def get_presigned_url(
        self, key: str, expires: timedelta = timedelta(hours=1)
    ) -> str:
        self.calls.append((key, expires))
        return f"https://minio.example/{key}?X-Amz-Signature=abc"


def test_presigned_strategy_delegates_to_the_store():
    store = _FakeStore()
    resolver = ContentUrlResolver(
        strategy="presigned", store=store, base_url="/control-plane/v1"
    )

    url = resolver.url_for(KEY, expires=timedelta(seconds=60))

    assert url == f"https://minio.example/{KEY}?X-Amz-Signature=abc"
    assert store.calls == [(KEY, timedelta(seconds=60))]


def test_proxy_strategy_mints_a_same_origin_signed_url():
    store = _FakeStore()
    resolver = ContentUrlResolver(
        strategy="proxy", store=store, base_url="/control-plane/v1/", secret=SECRET
    )

    url = resolver.url_for(KEY, expires=timedelta(seconds=60))

    parsed = urlparse(url)
    assert parsed.path == f"/control-plane/v1/objects/{KEY}"
    token = parse_qs(parsed.query)["token"][0]
    assert verify_signed_token(token, [KEY], secret=SECRET) is True
    # The store is never asked to sign anything in this mode.
    assert store.calls == []


def test_proxy_token_is_bound_to_the_key():
    resolver = ContentUrlResolver(
        strategy="proxy",
        store=_FakeStore(),
        base_url="/knowledge-flow/v1",
        secret=SECRET,
    )
    token = parse_qs(
        urlparse(resolver.url_for(KEY, expires=timedelta(seconds=60))).query
    )["token"][0]

    assert verify_signed_token(token, ["teams/t1/other.png"], secret=SECRET) is False


def test_proxy_strategy_requires_a_secret():
    with pytest.raises(ValueError, match="signing secret"):
        ContentUrlResolver(strategy="proxy", store=_FakeStore(), base_url="/x")
