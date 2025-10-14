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

import logging
from pathlib import Path
from typing import List

from minio import Minio
from minio.error import S3Error

from app.common.document_structures import DocumentMetadata
from app.common.structures import MinioPullSource
from app.core.stores.catalog.base_catalog_store import PullFileEntry
from app.core.stores.content.base_content_loader import BaseContentLoader

logger = logging.getLogger(__name__)


class MinioContentLoader(BaseContentLoader):
    def __init__(self, source: MinioPullSource, source_tag: str):
        super().__init__(source, source_tag)

        self.bucket_name = source.bucket_name
        self.prefix = source.prefix or ""

        try:
            self.client = Minio(
                endpoint=source.endpoint_url,
                access_key=source.access_key,
                secret_key=source.secret_key,
                secure=source.secure,
            )
        except S3Error as e:
            raise RuntimeError(f"Failed to connect to MinIO: {e}")

    def fetch_from_pull_entry(self, entry: PullFileEntry, destination_dir: Path) -> Path:
        """
        Download a file from MinIO to the destination folder.

        The file will be saved under:
            destination_dir / source_relative_path

        If intermediate folders are required, they will be created.
        """
        destination_dir.mkdir(parents=True, exist_ok=True)
        local_path = destination_dir / entry.path
        local_path.parent.mkdir(parents=True, exist_ok=True)

        remote_key = self.prefix + entry.path

        try:
            self.client.fget_object(self.bucket_name, remote_key, str(local_path))
        except S3Error as e:
            raise RuntimeError(f"Failed to fetch {remote_key} from bucket {self.bucket_name}: {e}")

        return local_path

    def fetch_from_metadata(self, metadata: DocumentMetadata, destination_dir: Path) -> Path:
        if not metadata.source_tag or not metadata.pull_location:
            raise ValueError("Missing `source_tag` or `pull_location` in metadata.")

        entry = PullFileEntry(
            path=metadata.pull_location,
            size=0,
            modified_time=metadata.modified.timestamp() if metadata.modified else 0,
            hash="na",
        )
        return self.fetch_from_pull_entry(entry, destination_dir)

    def scan(self) -> List[PullFileEntry]:
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=self.prefix, recursive=True)
            entries: List[PullFileEntry] = []

            for obj in objects:
                if obj.is_dir:
                    continue
                if obj.object_name:
                    relative_path = obj.object_name[len(self.prefix) :]
                    entries.append(
                        PullFileEntry(
                            path=relative_path,
                            size=obj.size if obj.size else 0,
                            modified_time=obj.last_modified.timestamp() if obj.last_modified else 0,
                            hash=obj.etag or "",
                        )
                    )
            return entries
        except S3Error as e:
            logger.error(f"Failed to list objects in bucket {self.bucket_name}: {e}")
            raise RuntimeError(f"Failed to list objects in bucket {self.bucket_name}: {e}")

    def fetch_by_relative_path(self, relative_path: str, destination_dir: Path) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        local_path = destination_dir / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)

        remote_key = self.prefix + relative_path

        try:
            self.client.fget_object(self.bucket_name, remote_key, str(local_path))
            return local_path
        except S3Error as e:
            raise RuntimeError(f"Failed to fetch {remote_key} from bucket {self.bucket_name}: {e}")
