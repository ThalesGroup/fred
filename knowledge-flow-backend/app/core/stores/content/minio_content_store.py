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

import io
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, List, Optional, cast
from urllib.parse import urlparse

import pandas as pd
from minio import Minio
from minio.error import S3Error

from app.core.stores.content.base_content_store import BaseContentStore, FileMetadata, StoredObjectInfo

logger = logging.getLogger(__name__)


class _ResponseRaw(io.RawIOBase):
    """Raw readable wrapper over MinIO/urllib3 response (no buffering)."""

    def __init__(self, resp):
        self._resp = resp
        self._closed = False

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # <-- no type annotation; accepts any writable buffer
        if self._closed:
            return 0
        mv = memoryview(b).cast("B")  # write into the caller-provided buffer
        data = self._resp.read(len(mv))
        if not data:
            return 0
        n = len(data)
        mv[:n] = data
        return n

    def close(self) -> None:
        if not self._closed:
            if hasattr(self._resp, "close") and callable(self._resp.close):
                self._resp.close()
            if hasattr(self._resp, "release_conn") and callable(self._resp.release_conn):
                self._resp.release_conn()
            self._closed = True
        super().close()

    @property
    def closed(self) -> bool:
        return self._closed


class MinioStorageBackend(BaseContentStore):
    """
    MinIO content store for uploading files to two distinct MinIO buckets:
    one for documents and one for generic objects/assets.
    """

    # 🚨 NOTE: The factory function must be updated to pass both bucket names.
    # The new expected signature in __init__ is:
    # def __init__(self, endpoint: str, access_key: str, secret_key: str, document_bucket: str, object_bucket: str, secure: bool):

    def __init__(self, endpoint: str, access_key: str, secret_key: str, document_bucket: str, object_bucket: str, secure: bool):
        """
        Initializes the MinIO client and ensures both buckets exist.
        """
        self.document_bucket = document_bucket
        self.object_bucket = object_bucket
        self.buckets = {
            self.document_bucket,
            self.object_bucket,
        }

        parsed = urlparse(endpoint)
        if parsed.path and parsed.path != "/":
            raise RuntimeError(
                f"❌ Invalid MinIO endpoint: '{endpoint}'.\n"
                "👉 The endpoint must not include a path. Use only scheme://host:port.\n"
                "   Example: 'http://localhost:9000', NOT 'http://localhost:9000/minio'"
            )

        # Strip scheme if needed
        clean_endpoint = endpoint.replace("https://", "").replace("http://", "")
        try:
            self.client = Minio(clean_endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        except ValueError as e:
            logger.error(f"❌ Failed to initialize MinIO client: {e}")
            raise

        # Ensure both buckets exist or create them
        for bucket_name in self.buckets:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Bucket '{bucket_name}' created successfully.")

    # ----------------------------------------------------------------------
    # DOCUMENT-RELATED METHODS (Use self.document_bucket)
    # ----------------------------------------------------------------------

    def save_content(self, document_uid: str, document_dir: Path):
        """
        Uploads all files in the given directory to the document bucket.
        """
        for file_path in document_dir.rglob("*"):
            if file_path.is_file():
                object_name = f"{document_uid}/{file_path.relative_to(document_dir)}"
                try:
                    # MODIFIED: Use document_bucket
                    self.client.fput_object(self.document_bucket, object_name, str(file_path))
                    logger.info(f"Uploaded '{object_name}' to document bucket '{self.document_bucket}'.")
                except S3Error as e:
                    logger.error(f"Failed to upload '{file_path}': {e}")
                    raise ValueError(f"Failed to upload '{file_path}': {e}")

    def _upload_folder(self, document_uid: str, local_path: Path, subfolder: str):
        """
        Uploads all files inside `local_path` to the document bucket.
        """
        if not local_path.exists() or not local_path.is_dir():
            raise ValueError(f"Path {local_path} does not exist or is not a directory")

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_path)
                object_name = f"{document_uid}/{subfolder}/{relative_path}"

                try:
                    # MODIFIED: Use document_bucket
                    self.client.fput_object(self.document_bucket, object_name, str(file_path))
                    logger.info(f"📤 Uploaded '{object_name}' to document bucket '{self.document_bucket}'")
                except S3Error as e:
                    logger.error(f"❌ Failed to upload '{file_path}' as '{object_name}': {e}")
                    raise ValueError(f"Upload failed for '{object_name}': {e}")

    def save_input(self, document_uid: str, input_dir: Path) -> None:
        self._upload_folder(document_uid, input_dir, subfolder="input")

    def save_output(self, document_uid: str, output_dir: Path) -> None:
        self._upload_folder(document_uid, output_dir, subfolder="output")

    def delete_content(self, document_uid: str) -> None:
        """
        Deletes all objects in the document bucket under the given document UID prefix.
        """
        try:
            # MODIFIED: Use document_bucket
            objects_to_delete = self.client.list_objects(self.document_bucket, prefix=f"{document_uid}/", recursive=True)
            deleted_any = False

            for obj in objects_to_delete:
                if obj.object_name is None:
                    raise RuntimeError(f"MinIO object has no name: {obj}")
                self.client.remove_object(self.document_bucket, obj.object_name)
                logger.info(f"🗑️ Deleted '{obj.object_name}' from document bucket '{self.document_bucket}'.")
                deleted_any = True

            if not deleted_any:
                logger.warning(f"⚠️ No objects found to delete for document {document_uid}.")

        except S3Error as e:
            logger.error(f"❌ Failed to delete objects for document {document_uid}: {e}")
            raise ValueError(f"Failed to delete document content from MinIO: {e}")

    def get_markdown(self, document_uid: str) -> str:
        """
        Fetches the markdown content from 'output/output.md' in the document directory.
        """
        md_object = f"{document_uid}/output/output.md"
        csv_object = f"{document_uid}/output/table.csv"

        try:
            # MODIFIED: Use document_bucket
            response = self.client.get_object(self.document_bucket, md_object)
            return response.read().decode("utf-8")
        except S3Error as e_md:
            logger.warning(f"Markdown not found for {document_uid}: {e_md}")

        # Try CSV fallback
        try:
            # MODIFIED: Use document_bucket
            response = self.client.get_object(self.document_bucket, csv_object)
            csv_bytes = response.read()
            df = pd.read_csv(io.BytesIO(csv_bytes))
            return df.to_markdown(index=False, tablefmt="github")
        except S3Error as e_csv:
            logger.error(f"CSV also not found for {document_uid}: {e_csv}")
        except Exception as e:
            logger.error(f"Error reading or converting CSV for {document_uid}: {e}")

        raise FileNotFoundError(f"Neither markdown nor CSV preview found for document: {document_uid}")

    def get_media(self, document_uid: str, media_id: str) -> BinaryIO:
        media_object = f"{document_uid}/output/media/{media_id}"
        try:
            # MODIFIED: Use document_bucket
            resp = self.client.get_object(self.document_bucket, media_object)
            return io.BufferedReader(_ResponseRaw(resp))  # ← stream, not BytesIO
        except S3Error as e:
            logger.error(f"Error fetching media {media_id} for document {document_uid}: {e}")
            raise FileNotFoundError(f"Failed to retrieve media: {e}")

    def clear(self) -> None:
        """
        Deletes all objects in BOTH the document and object buckets.
        """
        for bucket_name in self.buckets:
            try:
                objects_to_delete = self.client.list_objects(bucket_name, recursive=True)
                deleted_any = False

                for obj in objects_to_delete:
                    if obj.object_name is None:
                        raise RuntimeError(f"MinIO object has no name: {obj}")
                    self.client.remove_object(bucket_name, obj.object_name)
                    logger.info(f"🗑️ Deleted '{obj.object_name}' from bucket '{bucket_name}'.")
                    deleted_any = True

                if not deleted_any:
                    logger.warning(f"⚠️ No objects found to delete in bucket '{bucket_name}'.")

            except S3Error as e:
                logger.error(f"❌ Failed to delete objects from bucket '{bucket_name}': {e}")
                raise ValueError(f"Failed to clear content from MinIO bucket '{bucket_name}': {e}")

    def get_local_copy(self, document_uid: str, destination_dir: Path) -> Path:
        """
        Downloads all files of the given document_uid from the document bucket.
        """
        try:
            # MODIFIED: Use document_bucket
            objects = list(self.client.list_objects(self.document_bucket, prefix=f"{document_uid}/", recursive=True))
            if not objects:
                raise FileNotFoundError(f"No content found for document: {document_uid}")

            for obj in objects:
                if obj.object_name is None:
                    raise RuntimeError(f"MinIO object has no name: {obj}")
                relative_path = Path(obj.object_name).relative_to(document_uid)
                target_path = destination_dir / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                # MODIFIED: Use document_bucket
                self.client.fget_object(self.document_bucket, obj.object_name, str(target_path))

            logger.info(f"✅ Restored document {document_uid} to {destination_dir}")
            return destination_dir

        except S3Error as e:
            logger.error(f"Failed to restore document {document_uid}: {e}")
            raise

    def _get_primary_object_name(self, document_uid: str) -> str:
        """Helper to find the object_name of the primary input file in the document bucket."""
        prefix = f"{document_uid}/input/"
        # MODIFIED: Use document_bucket
        objects = list(self.client.list_objects(self.document_bucket, prefix=prefix, recursive=True))
        if not objects:
            raise FileNotFoundError(f"No input content found for document: {document_uid}")

        # Assume the first object in the input folder is the primary file
        if objects[0].object_name is None:
            raise RuntimeError(f"MinIO object has no name: {objects[0]}")

        return objects[0].object_name

    def get_file_metadata(self, document_uid: str) -> FileMetadata:
        """
        Retrieves metadata (size, file_name, content_type) from the document bucket.
        """
        object_name = self._get_primary_object_name(document_uid)

        try:
            # MODIFIED: Use document_bucket
            stat = self.client.stat_object(self.document_bucket, object_name)

            file_name = Path(object_name).name

            if stat.size is None:
                logger.error(f"File size is None for {object_name}")
                raise ValueError(f"File size is None for {object_name}")

            return FileMetadata(
                size=stat.size,
                file_name=file_name,
                content_type=stat.content_type,
            )
        except S3Error as e:
            logger.error(f"Error fetching metadata for {object_name}: {e}")
            raise FileNotFoundError(f"Failed to retrieve file metadata: {e}")

    def get_content_range(self, document_uid: str, start: int, length: int) -> BinaryIO:
        object_name = self._get_primary_object_name(document_uid)
        try:
            # MODIFIED: Use document_bucket
            resp = self.client.get_object(
                bucket_name=self.document_bucket,
                object_name=object_name,
                offset=start,
                length=length,
            )
            return io.BufferedReader(_ResponseRaw(resp))
        except S3Error as e:
            logger.error(f"Error fetching range for {object_name} ({start}-{start + length - 1}): {e}")
            raise FileNotFoundError(f"Failed to retrieve content range: {e}")

    def get_content(self, document_uid: str) -> BinaryIO:
        object_name = self._get_primary_object_name(document_uid)
        try:
            # MODIFIED: Use document_bucket
            resp = self.client.get_object(self.document_bucket, object_name)
            return io.BufferedReader(_ResponseRaw(resp))
        except S3Error as e:
            logger.error(f"Error fetching content for {document_uid}: {e}")
            raise FileNotFoundError(f"Failed to retrieve original content: {e}")

    # ----------------------------------------------------------------------
    # GENERIC OBJECT-RELATED METHODS (Use self.object_bucket)
    # ----------------------------------------------------------------------

    @staticmethod
    def _now_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _basename(key: str) -> str:
        return os.path.basename(key.rstrip("/"))

    @staticmethod
    def _normalize_key(key: str) -> str:
        k = (key or "").lstrip("/")
        if not k:
            raise ValueError("Empty object key")
        return k

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> StoredObjectInfo:
        """
        Store/replace arbitrary binary 'key' in the object bucket.
        """
        object_name = self._normalize_key(key)

        # MinIO requires known length → spool to temp
        with tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024, mode="w+b") as tmp:
            size = 0
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
                size += len(chunk)
            tmp.seek(0)

            try:
                ct = content_type or "application/octet-stream"
                # MODIFIED: Use object_bucket
                self.client.put_object(self.object_bucket, object_name, data=cast(BinaryIO, tmp), length=size, content_type=ct)
            except S3Error as e:
                logger.error(f"put_object failed for '{object_name}' in object bucket: {e}")
                raise

        # Return strong, typed metadata after upload
        # MODIFIED: Use object_bucket
        st = self.client.stat_object(self.object_bucket, object_name)
        file_name = self._basename(object_name)

        return StoredObjectInfo(
            key=key,
            size=st.size if st.size is not None else size,
            file_name=file_name,
            content_type=st.content_type,
            modified=self._now_utc(st.last_modified),
            etag=st.etag,
        )

    def get_object_stream(self, key: str, *, start: Optional[int] = None, length: Optional[int] = None) -> BinaryIO:
        object_name = self._normalize_key(key)
        try:
            # MODIFIED: Use object_bucket
            if start is None and length is None:
                resp = self.client.get_object(self.object_bucket, object_name)
            elif length is not None:
                resp = self.client.get_object(self.object_bucket, object_name, offset=start or 0, length=length)
            else:
                resp = self.client.get_object(self.object_bucket, object_name, offset=start or 0)
            return io.BufferedReader(_ResponseRaw(resp))
        except S3Error as e:
            if getattr(e, "code", "") in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise FileNotFoundError(f"Object not found: {key}") from e
            raise

    def stat_object(self, key: str) -> StoredObjectInfo:
        object_name = self._normalize_key(key)
        try:
            # MODIFIED: Use object_bucket
            st = self.client.stat_object(self.object_bucket, object_name)
        except S3Error as e:
            if getattr(e, "code", "") in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise FileNotFoundError(f"Object not found: {key}") from e
            raise

        file_name = self._basename(object_name)
        if st.size is None:
            raise RuntimeError(f"MinIO stat returned no size for '{object_name}'")

        return StoredObjectInfo(
            key=key,
            size=st.size,
            file_name=file_name,
            content_type=st.content_type,
            modified=self._now_utc(st.last_modified),
            etag=st.etag,
        )

    def list_objects(self, prefix: str) -> List[StoredObjectInfo]:
        prefix = self._normalize_key(prefix)
        try:
            # MODIFIED: Use object_bucket
            it = self.client.list_objects(self.object_bucket, prefix=prefix, recursive=True)
        except S3Error as e:
            raise RuntimeError(f"list_objects failed for prefix '{prefix}': {e}") from e

        items: List[StoredObjectInfo] = []
        for obj in it:
            if obj.object_name is None:
                continue
            items.append(
                StoredObjectInfo(
                    key=obj.object_name,
                    size=obj.size or 0,
                    file_name=self._basename(obj.object_name),
                    content_type=None,
                    modified=self._now_utc(obj.last_modified),
                    etag=None,
                )
            )
        return items

    def delete_object(self, key: str) -> None:
        object_name = self._normalize_key(key)
        try:
            # MODIFIED: Use object_bucket
            self.client.remove_object(self.object_bucket, object_name)
        except S3Error as e:
            if getattr(e, "code", "") in {"NoSuchKey", "NoSuchObject"}:
                raise FileNotFoundError(f"Object not found: {key}") from e
            raise
