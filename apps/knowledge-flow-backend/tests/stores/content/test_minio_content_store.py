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

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from minio.error import S3Error

from knowledge_flow_backend.core.stores.content.minio_content_store import MinioStorageBackend


class _FakeMinio:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self.fput_calls: list[tuple[str, str, str, str | None]] = []
        self.presigned_calls: list[tuple[str, str]] = []
        self._objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return True

    def make_bucket(self, bucket_name: str) -> None:
        del bucket_name

    def fput_object(self, bucket_name: str, object_name: str, file_path: str, content_type: str | None = None) -> None:
        payload = Path(file_path).read_bytes()
        self._objects[(bucket_name, object_name)] = payload
        self.fput_calls.append((bucket_name, object_name, file_path, content_type))

    def put_object(self, bucket_name: str, object_name: str, data, length: int = -1, content_type: str | None = None, **kwargs) -> None:
        del content_type, kwargs
        self._objects[(bucket_name, object_name)] = data.read() if length < 0 else data.read(length)

    def list_objects(self, bucket_name: str, prefix: str = "", recursive: bool = False):
        del recursive
        for (bucket, name), payload in sorted(self._objects.items()):
            if bucket == bucket_name and name.startswith(prefix):
                yield SimpleNamespace(object_name=name, size=len(payload), last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc), etag="etag-value")

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self._objects.pop((bucket_name, object_name), None)

    def stat_object(self, bucket_name: str, object_name: str) -> SimpleNamespace:
        payload = self._objects[(bucket_name, object_name)]
        return SimpleNamespace(
            size=len(payload),
            content_type="application/vnd.apache.parquet",
            last_modified=datetime.now(timezone.utc),
            etag="etag-value",
        )

    def presigned_get_object(self, bucket_name: str, object_name: str, expires) -> str:
        del expires
        self.presigned_calls.append((bucket_name, object_name))
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.endpoint}/{bucket_name}/{object_name}"


def test_put_file_uses_direct_minio_file_upload(monkeypatch, tmp_path):
    monkeypatch.setattr("knowledge_flow_backend.core.stores.content.minio_content_store.Minio", _FakeMinio)

    store = MinioStorageBackend(
        endpoint="http://internal-minio:9000",
        access_key="minio",
        secret_key="minio-secret",  # pragma: allowlist secret
        document_bucket="documents",
        object_bucket="objects",
        secure=False,
    )
    parquet_file = tmp_path / "data.parquet"
    parquet_file.write_bytes(b"parquet-data")

    stored = store.put_file(
        "tabular/doc-1/rev/data.parquet",
        parquet_file,
        content_type="application/vnd.apache.parquet",
    )

    assert store.client.fput_calls == [("objects", "tabular/doc-1/rev/data.parquet", str(parquet_file), "application/vnd.apache.parquet")]
    assert stored.size == len(b"parquet-data")
    assert stored.file_name == "data.parquet"


def test_get_output_artifact_releases_connection(monkeypatch):
    # get_object returns a urllib3 response that must be released back to the pool;
    # without it every preview fetch leaks a connection and the pool is exhausted.
    monkeypatch.setattr("knowledge_flow_backend.core.stores.content.minio_content_store.Minio", _FakeMinio)
    store = MinioStorageBackend(
        endpoint="http://internal-minio:9000",
        access_key="minio",
        secret_key="minio-secret",  # pragma: allowlist secret
        document_bucket="documents",
        object_bucket="objects",
        secure=False,
    )
    resp = MagicMock()
    resp.read.return_value = b"image-bytes"
    store.client.get_object = MagicMock(return_value=resp)

    data = store.get_output_artifact("doc-1/preview.png")

    assert data == b"image-bytes"
    resp.close.assert_called_once()
    resp.release_conn.assert_called_once()


def test_internal_presigned_url_uses_internal_minio_client(monkeypatch):
    monkeypatch.setattr("knowledge_flow_backend.core.stores.content.minio_content_store.Minio", _FakeMinio)

    store = MinioStorageBackend(
        endpoint="http://internal-minio:9000",
        access_key="minio",
        secret_key="minio-secret",  # pragma: allowlist secret
        document_bucket="documents",
        object_bucket="objects",
        secure=False,
        public_endpoint="https://public-minio.example",
    )

    public_url = store.get_presigned_url("tabular/doc-1/rev/data.parquet")
    internal_url = store.get_presigned_url_internal("tabular/doc-1/rev/data.parquet")

    assert public_url.startswith("https://public-minio.example/")
    assert internal_url.startswith("http://internal-minio:9000/")


def _make_store(monkeypatch) -> MinioStorageBackend:
    monkeypatch.setattr("knowledge_flow_backend.core.stores.content.minio_content_store.Minio", _FakeMinio)
    return MinioStorageBackend(
        endpoint="http://internal-minio:9000",
        access_key="minio",
        secret_key="minio-secret",  # pragma: allowlist secret
        document_bucket="documents",
        object_bucket="objects",
        secure=False,
    )


def test_list_output_artifacts_filters_the_document_bucket_by_suffix(monkeypatch):
    store = _make_store(monkeypatch)
    store.put_output_artifact("doc-a/output/render.pdf", b"a", content_type="application/pdf")
    store.put_output_artifact("doc-b/output/render.pdf", b"bb", content_type="application/pdf")
    store.put_output_artifact("doc-b/output/output.md", b"# md", content_type="text/markdown")
    store.put_output_artifact("doc-c/output/nested/render.pdf", b"c", content_type="application/pdf")
    store.put_object("agents/render.pdf", BytesIO(b"other bucket"), content_type="application/pdf")

    found = store.list_output_artifacts("render.pdf")

    assert [(o.key, o.document_uid, o.size) for o in found] == [
        ("doc-a/output/render.pdf", "doc-a", 1),
        ("doc-b/output/render.pdf", "doc-b", 2),
    ]
    assert all(o.modified == datetime(2026, 1, 1, tzinfo=timezone.utc) for o in found)


def test_delete_output_artifact_is_idempotent_and_scoped(monkeypatch):
    store = _make_store(monkeypatch)
    store.put_output_artifact("doc-a/output/render.pdf", b"a", content_type="application/pdf")
    store.put_output_artifact("doc-a/output/output.md", b"# md", content_type="text/markdown")

    store.delete_output_artifact("doc-a/output/render.pdf")
    store.delete_output_artifact("doc-a/output/render.pdf")

    assert store.list_output_artifacts("render.pdf") == []
    assert [o.key for o in store.list_output_artifacts("output.md")] == ["doc-a/output/output.md"]


def test_list_output_artifacts_wraps_a_listing_failure(monkeypatch):
    store = _make_store(monkeypatch)

    def _boom(*args, **kwargs):
        raise S3Error(MagicMock(), "AccessDenied", "denied", "documents", "req", "host")
        yield  # keep it a generator like the real client

    store.client.list_objects = _boom

    with pytest.raises(RuntimeError, match="list_output_artifacts failed"):
        store.list_output_artifacts("render.pdf")
