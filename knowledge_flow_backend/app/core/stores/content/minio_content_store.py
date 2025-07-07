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

from io import BytesIO
import io
import logging
from pathlib import Path
from typing import BinaryIO
from minio import Minio
from minio.error import S3Error
import pandas as pd
from app.core.stores.base_content_store import BaseContentStore

logger = logging.getLogger(__name__)


class MinioContentStore(BaseContentStore):
    """
    MinIO content store for uploading files to a MinIO bucket.
    This class implements the BaseContentStore interface.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket_name: str, secure: bool):
        """
        Initializes the MinIO client and ensures the bucket exists.
        """
        self.bucket_name = bucket_name
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

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

    def delete_content(self, document_uid: str) -> None:
        """
        Deletes all objects in the bucket under the given document UID prefix.
        """
        try:
            objects_to_delete = self.client.list_objects(self.bucket_name, prefix=f"{document_uid}/", recursive=True)
            deleted_any = False

            for obj in objects_to_delete:
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
