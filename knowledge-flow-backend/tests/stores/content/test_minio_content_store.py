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
from pathlib import Path
from types import SimpleNamespace

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
