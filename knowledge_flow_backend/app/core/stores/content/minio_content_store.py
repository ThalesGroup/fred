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
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse

import pandas as pd
from minio import Minio
from minio.error import S3Error

from app.core.stores.content.base_content_store import BaseContentStore

logger = logging.getLogger(__name__)


class MinioStorageBackend(BaseContentStore):
    """
    MinIO content store for uploading files to a MinIO bucket.
    This class implements the BaseContentStore interface.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket_name: str, secure: bool):
        """
        Initializes the MinIO client and ensures the bucket exists.
        """
        self.bucket_name = bucket_name
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

        # Ensure bucket exists or create it
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(f"Bucket '{bucket_name}' created successfully.")

    def save_content(self, document_uid: str, document_dir: Path):
        """
        Uploads all files in the given directory to MinIO,
        preserving the document UID as the root prefix.
        """
        for file_path in document_dir.rglob("*"):
            if file_path.is_file():
                object_name = f"{document_uid}/{file_path.relative_to(document_dir)}"
                try:
                    self.client.fput_object(self.bucket_name, object_name, str(file_path))
                    logger.info(f"Uploaded '{object_name}' to bucket '{self.bucket_name}'.")
                except S3Error as e:
                    logger.error(f"Failed to upload '{file_path}': {e}")
                    raise ValueError(f"Failed to upload '{file_path}': {e}")

    def _upload_folder(self, document_uid: str, local_path: Path, subfolder: str):
        """
        Uploads all files inside `local_path` to MinIO under the given subfolder
        (e.g. input/ or output/) using the structure:
            {document_uid}/{subfolder}/<relative_path>

        Example:
            If local_path contains:
                /tmp/output/output.md
                /tmp/output/media/image1.png

            It uploads to:
                {document_uid}/output/output.md
                {document_uid}/output/media/image1.png
        """
        if not local_path.exists() or not local_path.is_dir():
            raise ValueError(f"Path {local_path} does not exist or is not a directory")

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_path)
                object_name = f"{document_uid}/{subfolder}/{relative_path}"

                try:
                    self.client.fput_object(self.bucket_name, object_name, str(file_path))
                    logger.info(f"📤 Uploaded '{object_name}' to bucket '{self.bucket_name}'")
                except S3Error as e:
                    logger.error(f"❌ Failed to upload '{file_path}' as '{object_name}': {e}")
                    raise ValueError(f"Upload failed for '{object_name}': {e}")

    def save_input(self, document_uid: str, input_dir: Path) -> None:
        self._upload_folder(document_uid, input_dir, subfolder="input")

    def save_output(self, document_uid: str, output_dir: Path) -> None:
        self._upload_folder(document_uid, output_dir, subfolder="output")

    def delete_content(self, document_uid: str) -> None:
        """
        Deletes all objects in the bucket under the given document UID prefix.
        """
        try:
            objects_to_delete = self.client.list_objects(self.bucket_name, prefix=f"{document_uid}/", recursive=True)
            deleted_any = False

            for obj in objects_to_delete:
                if obj.object_name is None:
                    raise RuntimeError(f"MinIO object has no name: {obj}")
                self.client.remove_object(self.bucket_name, obj.object_name)
                logger.info(f"🗑️ Deleted '{obj.object_name}' from bucket '{self.bucket_name}'.")
                deleted_any = True

            if not deleted_any:
                logger.warning(f"⚠️ No objects found to delete for document {document_uid}.")

        except S3Error as e:
            logger.error(f"❌ Failed to delete objects for document {document_uid}: {e}")
            raise ValueError(f"Failed to delete document content from MinIO: {e}")

    def get_content(self, document_uid: str) -> BinaryIO:
        """
        Returns a binary stream of the first file found in the input/ folder for the document.
        """
        prefix = f"{document_uid}/input/"
        try:
            objects = list(self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True))
            if not objects:
                raise FileNotFoundError(f"No input content found for document: {document_uid}")

            obj = objects[0]
            if obj.object_name is None:
                raise RuntimeError(f"MinIO object has no name: {obj}")
            response = self.client.get_object(self.bucket_name, obj.object_name)
            return BytesIO(response.read())
        except S3Error as e:
            logger.error(f"Error fetching content for {document_uid}: {e}")
            raise FileNotFoundError(f"Failed to retrieve original content: {e}")

    def get_markdown(self, document_uid: str) -> str:
        """
        Fetches the markdown content from 'output/output.md' in the document directory.
        If not found, attempts to convert 'output/table.csv' to Markdown.
        """
        md_object = f"{document_uid}/output/output.md"
        csv_object = f"{document_uid}/output/table.csv"

        try:
            response = self.client.get_object(self.bucket_name, md_object)
            return response.read().decode("utf-8")
        except S3Error as e_md:
            logger.warning(f"Markdown not found for {document_uid}: {e_md}")

        # Try CSV fallback
        try:
            response = self.client.get_object(self.bucket_name, csv_object)
            csv_bytes = response.read()
            df = pd.read_csv(io.BytesIO(csv_bytes))
            return df.to_markdown(index=False, tablefmt="github")
        except S3Error as e_csv:
            logger.error(f"CSV also not found for {document_uid}: {e_csv}")
        except Exception as e:
            logger.error(f"Error reading or converting CSV for {document_uid}: {e}")

        raise FileNotFoundError(f"Neither markdown nor CSV preview found for document: {document_uid}")

    def get_media(self, document_uid: str, media_id: str) -> BinaryIO:
        """
        Returns a binary stream for the specified media file.
        """
        media_object = f"{document_uid}/output/media/{media_id}"
        try:
            response = self.client.get_object(self.bucket_name, media_object)
            media_bytes = response.read()
            return io.BytesIO(media_bytes)
        except S3Error as e:
            logger.error(f"Error fetching media {media_id} for document {document_uid}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching media {media_id} for document {document_uid}: {e}")
            raise

    def clear(self) -> None:
        """
        Deletes all objects in the MinIO bucket.
        """
        try:
            objects_to_delete = self.client.list_objects(self.bucket_name, recursive=True)
            deleted_any = False

            for obj in objects_to_delete:
                if obj.object_name is None:
                    raise RuntimeError(f"MinIO object has no name: {obj}")
                self.client.remove_object(self.bucket_name, obj.object_name)
                logger.info(f"🗑️ Deleted '{obj.object_name}' from bucket '{self.bucket_name}'.")
                deleted_any = True

            if not deleted_any:
                logger.warning("⚠️ No objects found to delete.")

        except S3Error as e:
            logger.error(f"❌ Failed to delete objects from bucket{self.bucket_name}: {e}")
            raise ValueError(f"Failed to delete document content from MinIO: {e}")

    def get_local_copy(self, document_uid: str, destination_dir: Path) -> Path:
        """
        Downloads the first input file of the given document_uid to a temporary file,
        and returns the local filesystem Path to it.
        """
        try:
            objects = list(self.client.list_objects(self.bucket_name, prefix=f"{document_uid}/", recursive=True))
            if not objects:
                raise FileNotFoundError(f"No content found for document: {document_uid}")

            for obj in objects:
                if obj.object_name is None:
                    raise RuntimeError(f"MinIO object has no name: {obj}")
                relative_path = Path(obj.object_name).relative_to(document_uid)
                target_path = destination_dir / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                self.client.fget_object(self.bucket_name, obj.object_name, str(target_path))

            logger.info(f"✅ Restored document {document_uid} to {destination_dir}")
            return destination_dir

        except S3Error as e:
            logger.error(f"Failed to restore document {document_uid}: {e}")
            raise
