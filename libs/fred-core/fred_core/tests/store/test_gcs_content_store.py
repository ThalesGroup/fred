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

# pylint: disable=redefined-outer-name

"""Unit tests for GcsContentStore using fake GCS client/blob doubles (no network)."""

from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO

import pytest
from fred_core.store import gcs_content_store
from fred_core.store.gcs_content_store import GcsContentStore


class _FakeBlob:
    def __init__(self, bucket_store: dict, name: str):
        self._bucket = bucket_store
        self.name = name

    def upload_from_file(self, stream, content_type=None):
        self._bucket[self.name] = (stream.read(), content_type)

    def exists(self, _client=None):
        return self.name in self._bucket


class _FakeBucket:
    def __init__(self, bucket_store: dict):
        self._bucket = bucket_store

    def blob(self, name):
        return _FakeBlob(self._bucket, name)


class _FakeClient:
    def __init__(self, buckets: dict):
        self._buckets = buckets

    def bucket(self, name):
        return _FakeBucket(self._buckets.setdefault(name, {}))


@pytest.fixture
def store_and_buckets(monkeypatch) -> tuple[GcsContentStore, dict]:
    buckets: dict[str, dict] = {}
    monkeypatch.setattr(
        gcs_content_store,
        "build_gcs_client",
        lambda project_id=None: _FakeClient(buckets),
    )
    return GcsContentStore(bucket_name="fred-objects"), buckets


def test_put_object_writes_bytes(store_and_buckets):
    store, buckets = store_and_buckets
    store.put_object(
        "teams/t1/banner.png", BytesIO(b"image-bytes"), content_type="image/png"
    )

    assert buckets["fred-objects"]["teams/t1/banner.png"] == (
        b"image-bytes",
        "image/png",
    )


def test_put_object_normalizes_leading_slash(store_and_buckets):
    store, buckets = store_and_buckets
    store.put_object("/teams/t1/banner.png", BytesIO(b"x"), content_type="image/png")

    assert "teams/t1/banner.png" in buckets["fred-objects"]


def test_get_presigned_url_requires_signing_email(store_and_buckets):
    store, _buckets = store_and_buckets
    with pytest.raises(RuntimeError, match="signing_service_account_email"):
        store.get_presigned_url("teams/t1/banner.png")


class _RecordingSignBlob:
    def __init__(self, name: str, captured: dict, exists: bool = True):
        self.name = name
        self._captured = captured
        self._exists = exists

    def exists(self, _client=None):
        return self._exists

    def generate_signed_url(self, **kwargs):
        self._captured.update(kwargs)
        self._captured["object_name"] = self.name
        return "https://storage.googleapis.com/fred-objects/x?X-Goog-Signature=deadbeef"


class _RecordingSignBucket:
    def __init__(self, captured: dict, exists: bool = True):
        self._captured = captured
        self._exists = exists

    def blob(self, name):
        return _RecordingSignBlob(name, self._captured, exists=self._exists)


def _signing_store(monkeypatch, captured: dict, *, exists: bool = True):
    monkeypatch.setattr(
        gcs_content_store, "build_gcs_client", lambda project_id=None: _FakeClient({})
    )
    s = GcsContentStore(
        bucket_name="fred-objects",
        signing_service_account_email="signer@project.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(s, "_mint_access_token", lambda: "fake-access-token")
    s.bucket = _RecordingSignBucket(captured, exists=exists)  # type: ignore[assignment]
    return s


def test_get_presigned_url_mints_v4_signed_url(monkeypatch):
    captured: dict = {}
    store = _signing_store(monkeypatch, captured)

    url = store.get_presigned_url("teams/t1/banner.png", expires=timedelta(seconds=120))

    assert url.startswith("https://storage.googleapis.com/")
    assert captured["version"] == "v4"
    assert captured["method"] == "GET"
    assert captured["service_account_email"] == "signer@project.iam.gserviceaccount.com"
    assert captured["access_token"] == "fake-access-token"
    assert captured["expiration"] == timedelta(seconds=120)
    assert captured["object_name"] == "teams/t1/banner.png"


def test_get_presigned_url_missing_object_raises(monkeypatch):
    captured: dict = {}
    store = _signing_store(monkeypatch, captured, exists=False)

    with pytest.raises(FileNotFoundError):
        store.get_presigned_url("teams/t1/missing.png")


def test_get_presigned_url_never_logs_the_url(monkeypatch, caplog):
    captured: dict = {}
    store = _signing_store(monkeypatch, captured)

    with caplog.at_level(logging.DEBUG):
        url = store.get_presigned_url("teams/t1/banner.png")

    assert url not in caplog.text
    assert "X-Goog-Signature" not in caplog.text


def test_mint_access_token_uses_adc_and_refreshes(monkeypatch):
    class _FakeCreds:
        def __init__(self):
            self.valid = False
            self.token = None

        def refresh(self, _request):
            self.valid = True
            self.token = "minted-token"  # nosec B105  # pragma: allowlist secret

    fake_creds = _FakeCreds()
    monkeypatch.setattr(
        gcs_content_store, "build_gcs_client", lambda project_id=None: _FakeClient({})
    )
    monkeypatch.setattr(gcs_content_store, "_load_adc_credentials", lambda: fake_creds)

    store = GcsContentStore(
        bucket_name="fred-objects",
        signing_service_account_email="signer@project.iam.gserviceaccount.com",
    )

    assert store._mint_access_token() == "minted-token"
    assert store._mint_access_token() == "minted-token"
