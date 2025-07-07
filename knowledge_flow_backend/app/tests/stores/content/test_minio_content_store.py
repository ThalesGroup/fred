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

# pylint: disable=redefined-outer-name

"""
Test suite for the MinioContentStore class in minio_content_store.py.

Covers:
- Nominal cases: saving, retrieving, and deleting content successfully.
- Error cases: MinIO errors during operations.
- Edge cases: deleting when no objects exist, missing input content.

All tests use pytest monkeypatching for mocking MinIO client behavior.
"""

from io import BytesIO
from pathlib import Path
import pytest
from minio.error import S3Error

from app.core.stores.content.minio_content_store import MinioContentStore


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def minio_store(monkeypatch):
    """Provides a MinioContentStore with a mocked MinIO client, patched in the correct module."""

    class MockMinioClient:
        """
        A lightweight mock implementation of the MinIO client used for testing MinioContentStore.

        This mock simulates:
        - Bucket existence checks and creation
        - File uploads and storage via `fput_object`
        - Object listing and deletion under a prefix
        - Object retrieval via `get_object`
        """

        def __init__(self):
            self.objects = {}
            self.bucket_created = False

        def bucket_exists(self, bucket_name):
            return self.bucket_created

        def make_bucket(self, bucket_name):
            self.bucket_created = True

        def fput_object(self, bucket, object_name, file_path):
            self.objects[object_name] = Path(file_path).read_bytes()

        def list_objects(self, bucket, prefix, recursive):
            return [type("Obj", (), {"object_name": name}) for name in self.objects if name.startswith(prefix)]

        def remove_object(self, bucket, object_name):
            self.objects.pop(object_name, None)

        def get_object(self, bucket, object_name):
            if object_name not in self.objects:
                raise S3Error("NoSuchKey", "Object not found", "", "", 404, "", "")
            return BytesIO(self.objects[object_name])

    client = MockMinioClient()
    monkeypatch.setattr("app.stores.content.minio_content_store.Minio", lambda *args, **kwargs: client)
    store = MinioContentStore("localhost:9000", "access", "secret", "bucket", secure=False)
    return store, client


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_save_content_nominal(tmp_path, minio_store):
    """Successfully saves content files to MinIO."""
    store, client = minio_store
    doc_id = "doc1"
    doc_dir = tmp_path / "input"
    doc_dir.mkdir()
    file = doc_dir / "example.txt"
    file.write_text("sample content")

    store.save_content(doc_id, doc_dir)

    key = f"{doc_id}/example.txt"
    assert key in client.objects


def test_get_content_nominal(minio_store):
    """Successfully retrieves binary content from MinIO."""
    store, client = minio_store
    doc_id = "doc2"
    key = f"{doc_id}/input/file.txt"
    client.objects[key] = b"data"

    content = store.get_content(doc_id)
    assert content.read() == b"data"


def test_get_markdown_nominal(minio_store):
    """Successfully retrieves markdown from MinIO."""
    store, client = minio_store
    doc_id = "doc3"
    key = f"{doc_id}/output/output.md"
    client.objects[key] = b"# Title"

    result = store.get_markdown(doc_id)
    assert result == "# Title"


def test_delete_content_nominal(minio_store):
    """Successfully deletes all content under a document UID."""
    store, client = minio_store
    doc_id = "doc4"
    client.objects[f"{doc_id}/file1.txt"] = b"data"
    client.objects[f"{doc_id}/file2.txt"] = b"data"

    store.delete_content(doc_id)

    assert all(not key.startswith(f"{doc_id}/") for key in client.objects)


# ----------------------------
# ❌ Failure Cases
# ----------------------------


def test_save_content_error(monkeypatch, minio_store, tmp_path):
    """Raises ValueError if MinIO upload fails during save_content."""
    store, _ = minio_store

    def failing_put_object(bucket, object_name, file_path):
        raise S3Error("AccessDenied", "Access Denied", "", "", 403, "", "")

    monkeypatch.setattr(store.client, "fput_object", failing_put_object)
    doc_id = "doc5"
    doc_dir = tmp_path / "failing_upload"
    doc_dir.mkdir()
    (doc_dir / "fail.txt").write_text("will trigger failure")
    with pytest.raises(ValueError, match="Failed to upload"):
        store.save_content(doc_id, doc_dir)


def test_get_content_s3_error(monkeypatch, minio_store):
    """Raises FileNotFoundError if MinIO raises error while fetching content."""
    store, _ = minio_store

    def failing_list(*args, **kwargs):
        raise S3Error("NoSuchKey", "Object not found", "", "", 404, "", "")

    monkeypatch.setattr(store.client, "list_objects", failing_list)
    with pytest.raises(FileNotFoundError, match="Failed to retrieve original content"):
        store.get_content("doc6")


def test_delete_content_minio_error(monkeypatch, minio_store):
    """delete_content raises ValueError if MinIO fails internally."""
    store, _ = minio_store

    def failing_list_objects(*args, **kwargs):
        raise S3Error("AccessDenied", "Cannot list", "", "", 403, "", "")

    monkeypatch.setattr(store.client, "list_objects", failing_list_objects)
    with pytest.raises(ValueError, match="Failed to delete document content from MinIO"):
        store.delete_content("doc_with_error")


def test_get_content_no_files_found(monkeypatch, minio_store):
    """Raises FileNotFoundError when no input files are found."""
    store, _ = minio_store
    monkeypatch.setattr(store.client, "list_objects", lambda *args, **kwargs: [])
    with pytest.raises(FileNotFoundError, match="No input content found"):
        store.get_content("doc_no_files")


def test_get_markdown_not_found(minio_store):
    """Raises FileNotFoundError if markdown object does not exist."""
    store, _ = minio_store
    with pytest.raises(FileNotFoundError, match="Markdown not found for document"):
        store.get_markdown("doc7")


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_delete_content_no_objects(minio_store):
    """Deletion logs a warning if no objects exist for UID (no crash)."""
    store, _ = minio_store
    doc_id = "doc_empty"
    store.delete_content(doc_id)
