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

import io
import logging
import os
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, List, Optional

from google.cloud import storage
from google.cloud.exceptions import NotFound

from knowledge_flow_backend.core.stores.content.base_content_store import BaseContentStore, FileMetadata, StoredObjectInfo

logger = logging.getLogger(__name__)


class GcsContentStore(BaseContentStore):
    """
    Google Cloud Storage content store.

    Mirrors :class:`MinioStorageBackend`: document content (ingestion input /
    output trees) lives in one bucket, generic objects/assets in another. Buckets
    must already exist — they are referenced lazily so the app boots under a
    least-privilege Workload Identity service account (no buckets.create needed).

    Authentication uses Application Default Credentials (ADC) / Workload Identity;
    no service-account JSON key is required.

    Signed URLs: :meth:`get_presigned_url` is intentionally unsupported on the
    pure Workload Identity path (V4 signing needs an SA key or the
    ``iam.serviceAccounts.signBlob`` permission). The VFS share flow uses
    application-level HMAC tokens, which are backend-agnostic and work over GCS
    as-is. See ``docs/swift/platform/DEPLOYMENT_GUIDE_GKE.md``.
    """

    def __init__(
        self,
        document_bucket: str,
        object_bucket: str,
        project_id: Optional[str] = None,
    ):
        self.document_bucket_name = document_bucket
        self.object_bucket_name = object_bucket

        self.client = storage.Client(project=project_id) if project_id else storage.Client()
        self.document_bucket = self.client.bucket(document_bucket)
        self.object_bucket = self.client.bucket(object_bucket)
        logger.info(
            "[CONTENT][GCS] Initialized GcsContentStore documents='%s' objects='%s'",
            document_bucket,
            object_bucket,
        )

    @staticmethod
    def _normalize_key(key: str) -> str:
        k = (key or "").lstrip("/")
        if not k:
            raise ValueError("Empty object key")
        return k

    @staticmethod
    def _basename(key: str) -> str:
        return os.path.basename(key.rstrip("/"))

    # ----------------------------------------------------------------------
    # DOCUMENT-RELATED METHODS (use the document bucket)
    # ----------------------------------------------------------------------

    def save_content(self, document_uid: str, document_dir: Path) -> None:
        for file_path in document_dir.rglob("*"):
            if file_path.is_file():
                object_name = f"{document_uid}/{file_path.relative_to(document_dir)}"
                self.document_bucket.blob(object_name).upload_from_filename(str(file_path))
                logger.info("[CONTENT][GCS] object=%s to document bucket='%s'", object_name, self.document_bucket_name)

    def _upload_folder(self, document_uid: str, local_path: Path, subfolder: str) -> None:
        if not local_path.exists() or not local_path.is_dir():
            raise ValueError(f"Path {local_path} does not exist or is not a directory")

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_path)
                object_name = f"{document_uid}/{subfolder}/{relative_path}"
                self.document_bucket.blob(object_name).upload_from_filename(str(file_path))
                logger.info("[CONTENT][GCS] object=%s to document bucket='%s'", object_name, self.document_bucket_name)

    def save_input(self, document_uid: str, input_dir: Path) -> None:
        self._upload_folder(document_uid, input_dir, subfolder="input")

    def save_output(self, document_uid: str, output_dir: Path) -> None:
        self._upload_folder(document_uid, output_dir, subfolder="output")

    def delete_content(self, document_uid: str) -> None:
        blobs = list(self.client.list_blobs(self.document_bucket_name, prefix=f"{document_uid}/"))
        if not blobs:
            logger.warning("[CONTENT][GCS] No objects found to delete for document_uid=%s", document_uid)
            return
        for blob in blobs:
            blob.delete()
            logger.info("[CONTENT][GCS] Deleted object='%s' from document bucket='%s'", blob.name, self.document_bucket_name)

    def list_document_uids(self) -> List[str]:
        doc_uids: set[str] = set()
        for blob in self.client.list_blobs(self.document_bucket_name):
            prefix = blob.name.split("/", 1)[0]
            if prefix:
                doc_uids.add(prefix)
        return sorted(doc_uids)

    def get_preview_bytes(self, doc_path: str) -> bytes:
        blob = self.document_bucket.blob(doc_path)
        try:
            return blob.download_as_bytes()
        except NotFound as e:
            raise FileNotFoundError(f"Preview image not found for document {doc_path}") from e

    def get_media(self, document_uid: str, media_id: str) -> BinaryIO:
        media_object = f"{document_uid}/output/media/{media_id}"
        blob = self.document_bucket.blob(media_object)
        try:
            return io.BytesIO(blob.download_as_bytes())
        except NotFound as e:
            raise FileNotFoundError(f"Failed to retrieve media: {media_id}") from e

    def clear(self) -> None:
        """Delete every object in BOTH the document and object buckets (test-friendly)."""
        for bucket_name in (self.document_bucket_name, self.object_bucket_name):
            blobs = list(self.client.list_blobs(bucket_name))
            if not blobs:
                logger.warning("[CONTENT][GCS] No objects found to delete in bucket '%s'", bucket_name)
                continue
            for blob in blobs:
                blob.delete()
                logger.info("[CONTENT][GCS] Deleted '%s' from bucket '%s'", blob.name, bucket_name)

    def get_local_copy(self, document_uid: str, destination_dir: Path) -> Path:
        blobs = list(self.client.list_blobs(self.document_bucket_name, prefix=f"{document_uid}/"))
        if not blobs:
            raise FileNotFoundError(f"[CONTENT][GCS] No content found for document: {document_uid}")

        for blob in blobs:
            relative_path = Path(blob.name).relative_to(document_uid)
            target_path = destination_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(target_path))

        logger.info("[CONTENT][GCS] Restored document %s to %s", document_uid, destination_dir)
        return destination_dir

    def _get_primary_blob(self, document_uid: str):
        prefix = f"{document_uid}/input/"
        blobs = list(self.client.list_blobs(self.document_bucket_name, prefix=prefix))
        if not blobs:
            raise FileNotFoundError(f"[CONTENT][GCS] No input content found for document: {document_uid}")
        return blobs[0]

    def get_file_metadata(self, document_uid: str) -> FileMetadata:
        blob = self._get_primary_blob(document_uid)
        blob.reload()
        if blob.size is None:
            raise ValueError(f"[CONTENT][GCS] File size is None for {blob.name}")
        return FileMetadata(
            size=blob.size,
            file_name=Path(blob.name).name,
            content_type=blob.content_type,
        )

    def get_content_range(self, document_uid: str, start: int, length: int) -> BinaryIO:
        blob = self._get_primary_blob(document_uid)
        data = blob.download_as_bytes(start=start, end=start + length - 1)
        return io.BytesIO(data)

    def get_content(self, document_uid: str) -> BinaryIO:
        blob = self._get_primary_blob(document_uid)
        return io.BytesIO(blob.download_as_bytes())

    # ----------------------------------------------------------------------
    # GENERIC OBJECT-RELATED METHODS (use the object bucket)
    # ----------------------------------------------------------------------

    def _stored_object_info(self, blob, key: str, *, fallback_size: Optional[int] = None) -> StoredObjectInfo:
        size = blob.size if blob.size is not None else fallback_size
        if size is None:
            raise RuntimeError(f"GCS blob has no size for '{key}'")
        return StoredObjectInfo(
            key=key,
            size=size,
            file_name=self._basename(blob.name),
            content_type=blob.content_type,
            modified=blob.updated,
            etag=blob.etag,
        )

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> StoredObjectInfo:
        object_name = self._normalize_key(key)
        ct = content_type or "application/octet-stream"
        blob = self.object_bucket.blob(object_name)
        blob.upload_from_file(stream, content_type=ct)
        return self._stored_object_info(blob, key)

    def put_file(self, key: str, file_path: Path, *, content_type: str) -> StoredObjectInfo:
        object_name = self._normalize_key(key)
        ct = content_type or "application/octet-stream"
        blob = self.object_bucket.blob(object_name)
        blob.upload_from_filename(str(file_path), content_type=ct)
        return self._stored_object_info(blob, key, fallback_size=file_path.stat().st_size)

    def get_object_stream(self, key: str, *, start: Optional[int] = None, length: Optional[int] = None) -> BinaryIO:
        object_name = self._normalize_key(key)
        blob = self.object_bucket.blob(object_name)
        try:
            if start is None and length is None:
                data = blob.download_as_bytes()
            else:
                s = start or 0
                end = s + length - 1 if length is not None else None
                data = blob.download_as_bytes(start=s, end=end)
        except NotFound as e:
            raise FileNotFoundError(f"Object not found: {key}") from e
        return io.BytesIO(data)

    def stat_object(self, key: str) -> StoredObjectInfo:
        object_name = self._normalize_key(key)
        blob = self.object_bucket.get_blob(object_name)
        if blob is None:
            raise FileNotFoundError(f"Object not found: {key}")
        return self._stored_object_info(blob, key)

    def list_objects(self, prefix: str) -> List[StoredObjectInfo]:
        prefix = self._normalize_key(prefix)
        items: List[StoredObjectInfo] = []
        for blob in self.client.list_blobs(self.object_bucket_name, prefix=prefix):
            items.append(
                StoredObjectInfo(
                    key=blob.name,
                    size=blob.size or 0,
                    file_name=self._basename(blob.name),
                    content_type=blob.content_type,
                    modified=blob.updated,
                    etag=blob.etag,
                )
            )
        return items

    def delete_object(self, key: str) -> None:
        object_name = self._normalize_key(key)
        try:
            self.object_bucket.blob(object_name).delete()
        except NotFound as e:
            raise FileNotFoundError(f"Object not found: {key}") from e

    def get_presigned_url(self, key: str, expires: timedelta = timedelta(hours=1)) -> str:
        """
        Not supported on the pure Workload Identity path.

        GCS V4 signed URLs require an SA private key or the
        ``iam.serviceAccounts.signBlob`` permission on the workload SA. The
        deployment default relies on application-level HMAC download tokens
        (backend-agnostic), so this raises like the local filesystem backend.
        """
        raise NotImplementedError(
            "Presigned URLs are not supported by the GCS content store on the default "
            "Workload Identity path. Use application-level share tokens, or grant "
            "iam.serviceAccounts.signBlob to enable GCS V4 signed URLs."
        )
