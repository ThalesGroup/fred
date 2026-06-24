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

"""Unit tests for GcsContentStore using an in-memory fake GCS client (no network)."""

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest


class _FakeBlob:
    def __init__(self, bucket_store: dict, name: str):
        self._bucket = bucket_store
        self.name = name
        self._content_type = None

    @property
    def size(self):
        entry = self._bucket.get(self.name)
        return None if entry is None else len(entry[0])

    @property
    def updated(self):
        return datetime(2026, 1, 1, tzinfo=timezone.utc) if self.name in self._bucket else None

    @property
    def etag(self):
        return "etag" if self.name in self._bucket else None

    @property
    def content_type(self):
        entry = self._bucket.get(self.name)
        return entry[1] if entry else self._content_type

    def upload_from_string(self, data, content_type=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._bucket[self.name] = (data, content_type)

    def upload_from_file(self, stream, content_type=None):
        self._bucket[self.name] = (stream.read(), content_type)

    def upload_from_filename(self, path, content_type=None):
        with open(path, "rb") as f:
            self._bucket[self.name] = (f.read(), content_type)

    def download_as_bytes(self, start=None, end=None):
        from google.cloud.exceptions import NotFound

        if self.name not in self._bucket:
            raise NotFound(self.name)
        data = self._bucket[self.name][0]
        if start is None and end is None:
            return data
        return data[start : (end + 1) if end is not None else None]

    def download_to_filename(self, path):
        with open(path, "wb") as f:
            f.write(self._bucket[self.name][0])

    def reload(self):
        pass

    def delete(self):
        from google.cloud.exceptions import NotFound

        if self.name not in self._bucket:
            raise NotFound(self.name)
        del self._bucket[self.name]


class _FakeBucket:
    def __init__(self, bucket_store: dict):
        self._bucket = bucket_store

    def blob(self, name):
        return _FakeBlob(self._bucket, name)

    def get_blob(self, name):
        return _FakeBlob(self._bucket, name) if name in self._bucket else None


class _FakeClient:
    def __init__(self, buckets: dict):
        self._buckets = buckets

    def bucket(self, name):
        return _FakeBucket(self._buckets.setdefault(name, {}))

    def list_blobs(self, bucket_name, prefix=""):
        store = self._buckets.setdefault(bucket_name, {})
        names = sorted(k for k in store if k.startswith(prefix or ""))
        return [_FakeBlob(store, n) for n in names]


@pytest.fixture
def gcs_store(monkeypatch):
    from knowledge_flow_backend.core.stores.content import gcs_content_store

    buckets: dict[str, dict] = {}
    monkeypatch.setattr(gcs_content_store.storage, "Client", lambda *a, **k: _FakeClient(buckets))
    store = gcs_content_store.GcsContentStore(document_bucket="kf-documents", object_bucket="kf-objects")
    store._buckets = buckets
    return store


def _make_doc(tmp_path):
    doc_dir = tmp_path / "source"
    input_dir = doc_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "test.txt").write_bytes(b"Hello GCS")
    return doc_dir


def test_save_input_and_get_content(gcs_store, tmp_path):
    doc_dir = _make_doc(tmp_path)
    gcs_store.save_input("doc1", doc_dir / "input")

    assert gcs_store.get_content("doc1").read() == b"Hello GCS"
    meta = gcs_store.get_file_metadata("doc1")
    assert meta.size == len(b"Hello GCS")
    assert meta.file_name == "test.txt"


def test_get_content_range(gcs_store, tmp_path):
    gcs_store.save_input("doc1", _make_doc(tmp_path) / "input")
    assert gcs_store.get_content_range("doc1", 0, 5).read() == b"Hello"


def test_get_local_copy_and_list_uids(gcs_store, tmp_path):
    gcs_store.save_input("doc1", _make_doc(tmp_path) / "input")
    dest = tmp_path / "restored"
    dest.mkdir()
    gcs_store.get_local_copy("doc1", dest)
    assert (dest / "input" / "test.txt").read_bytes() == b"Hello GCS"
    assert gcs_store.list_document_uids() == ["doc1"]


def test_delete_content(gcs_store, tmp_path):
    gcs_store.save_input("doc1", _make_doc(tmp_path) / "input")
    gcs_store.delete_content("doc1")
    with pytest.raises(FileNotFoundError):
        gcs_store.get_content("doc1")


def test_object_api_roundtrip(gcs_store):
    info = gcs_store.put_object("teams/abc/banner.jpg", BytesIO(b"imgdata"), content_type="image/jpeg")
    assert info.key == "teams/abc/banner.jpg"
    assert info.size == len(b"imgdata")
    assert info.content_type == "image/jpeg"

    assert gcs_store.get_object_stream("teams/abc/banner.jpg").read() == b"imgdata"
    assert gcs_store.get_object_stream("teams/abc/banner.jpg", start=0, length=3).read() == b"img"

    stat = gcs_store.stat_object("teams/abc/banner.jpg")
    assert stat.size == len(b"imgdata")

    listed = gcs_store.list_objects("teams/")
    assert [o.key for o in listed] == ["teams/abc/banner.jpg"]

    gcs_store.delete_object("teams/abc/banner.jpg")
    with pytest.raises(FileNotFoundError):
        gcs_store.stat_object("teams/abc/banner.jpg")


def test_put_file(gcs_store, tmp_path):
    p = tmp_path / "data.parquet"
    p.write_bytes(b"PARQUET")
    info = gcs_store.put_file("tabular/data.parquet", p, content_type="application/vnd.apache.parquet")
    assert info.size == len(b"PARQUET")
    assert gcs_store.get_object_stream("tabular/data.parquet").read() == b"PARQUET"


def test_missing_object_raises(gcs_store):
    with pytest.raises(FileNotFoundError):
        gcs_store.get_object_stream("nope")
    with pytest.raises(FileNotFoundError):
        gcs_store.delete_object("nope")


def test_clear_empties_both_buckets(gcs_store, tmp_path):
    gcs_store.save_input("doc1", _make_doc(tmp_path) / "input")
    gcs_store.put_object("k", BytesIO(b"x"), content_type="text/plain")
    gcs_store.clear()
    assert gcs_store.list_document_uids() == []
    assert gcs_store.list_objects("k") == []


def test_presigned_url_not_supported(gcs_store):
    with pytest.raises(NotImplementedError, match="signBlob"):
        gcs_store.get_presigned_url("teams/abc/banner.jpg")


def test_constructor_stores_signing_service_account_email(monkeypatch):
    """The signing SA email is retained for later V4 signed-URL generation.

    Why this exists:
    - get_presigned_url_internal (added next) signs with this account; the
      constructor must carry it through unchanged so the factory's fail-fast
      guarantee actually reaches the signer.
    """
    from knowledge_flow_backend.core.stores.content import gcs_content_store

    monkeypatch.setattr(gcs_content_store.storage, "Client", lambda *a, **k: _FakeClient({}))
    store = gcs_content_store.GcsContentStore(
        document_bucket="kf-documents",
        object_bucket="kf-objects",
        signing_service_account_email="signer@project.iam.gserviceaccount.com",
    )

    assert store.signing_service_account_email == "signer@project.iam.gserviceaccount.com"


def test_constructor_defaults_signing_email_to_none(monkeypatch):
    """Construction without a signing email is allowed; the factory enforces it."""
    from knowledge_flow_backend.core.stores.content import gcs_content_store

    monkeypatch.setattr(gcs_content_store.storage, "Client", lambda *a, **k: _FakeClient({}))
    store = gcs_content_store.GcsContentStore(document_bucket="kf-documents", object_bucket="kf-objects")

    assert store.signing_service_account_email is None


# --- internal V4 signed URL (IAM signBlob, keyless) -------------------------


class _RecordingSignBlob:
    """Object-bucket blob that records the generate_signed_url call."""

    def __init__(self, name: str, captured: dict):
        self.name = name
        self._captured = captured

    def generate_signed_url(self, **kwargs):
        self._captured.update(kwargs)
        self._captured["object_name"] = self.name
        return "https://storage.googleapis.com/kf-objects/x?X-Goog-Signature=deadbeef"


class _RecordingSignBucket:
    def __init__(self, captured: dict):
        self._captured = captured

    def blob(self, name):
        return _RecordingSignBlob(name, self._captured)


def _signing_store(monkeypatch, captured: dict, *, email="signer@project.iam.gserviceaccount.com"):
    from knowledge_flow_backend.core.stores.content import gcs_content_store

    monkeypatch.setattr(gcs_content_store.storage, "Client", lambda *a, **k: _FakeClient({}))
    store = gcs_content_store.GcsContentStore(
        document_bucket="kf-documents",
        object_bucket="kf-objects",
        signing_service_account_email=email,
    )
    # Replace ADC token minting and the object bucket with test doubles so no
    # network or real credentials are required.
    monkeypatch.setattr(store, "_mint_access_token", lambda: "fake-access-token")
    store.object_bucket = _RecordingSignBucket(captured)
    return store


def test_get_presigned_url_internal_mints_v4_signed_url(monkeypatch):
    """The internal URL is a keyless V4 GET signature for the right object."""
    captured: dict = {}
    store = _signing_store(monkeypatch, captured)

    url = store.get_presigned_url_internal("tabular/datasets/doc/rev/data.parquet", expires=timedelta(seconds=120))

    assert url.startswith("https://storage.googleapis.com/")
    assert captured["version"] == "v4"
    assert captured["method"] == "GET"
    assert captured["service_account_email"] == "signer@project.iam.gserviceaccount.com"
    assert captured["access_token"] == "fake-access-token"
    assert captured["expiration"] == timedelta(seconds=120)
    assert captured["object_name"] == "tabular/datasets/doc/rev/data.parquet"


def test_get_presigned_url_internal_requires_signing_email(monkeypatch):
    """Signing without a configured SA email fails clearly (defensive guard)."""
    captured: dict = {}
    store = _signing_store(monkeypatch, captured, email=None)

    with pytest.raises(RuntimeError, match="signing_service_account_email"):
        store.get_presigned_url_internal("tabular/datasets/doc/rev/data.parquet")


def test_get_presigned_url_internal_never_logs_the_url(monkeypatch, caplog):
    """The signed URL is a secret and must not appear in logs."""
    import logging

    captured: dict = {}
    store = _signing_store(monkeypatch, captured)

    with caplog.at_level(logging.DEBUG):
        url = store.get_presigned_url_internal("tabular/datasets/doc/rev/data.parquet")

    assert url not in caplog.text
    assert "X-Goog-Signature" not in caplog.text


def test_mint_access_token_uses_adc_and_refreshes(monkeypatch):
    """The token is sourced from ADC and refreshed when not yet valid."""
    from knowledge_flow_backend.core.stores.content import gcs_content_store

    class _FakeCreds:
        def __init__(self):
            self.valid = False
            self.token = None

        def refresh(self, _request):
            self.valid = True
            self.token = "minted-token"

    fake_creds = _FakeCreds()
    monkeypatch.setattr(gcs_content_store.storage, "Client", lambda *a, **k: _FakeClient({}))
    monkeypatch.setattr(gcs_content_store, "_load_adc_credentials", lambda: fake_creds)

    store = gcs_content_store.GcsContentStore(
        document_bucket="kf-documents",
        object_bucket="kf-objects",
        signing_service_account_email="signer@project.iam.gserviceaccount.com",
    )

    assert store._mint_access_token() == "minted-token"
    # Cached credentials are reused without a second ADC load on the next call.
    assert store._mint_access_token() == "minted-token"
