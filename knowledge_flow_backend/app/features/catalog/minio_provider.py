from pathlib import Path
from typing import List
from app.common.document_structures import DocumentMetadata
from app.features.catalog.base_pull_provider import BaseContentProvider
from minio import Minio
from minio.error import S3Error
import hashlib
from app.common.structures import DocumentSourceConfig
from app.core.stores.metadata.base_catalog_store import PullFileEntry


class MinioProvider(BaseContentProvider):
    def __init__(self, source: DocumentSourceConfig, source_tag: str):
        super().__init__(source, source_tag)

        self.bucket_name = source.bucket_name
        self.prefix = source.prefix or ""

        self.client = Minio(
            endpoint=source.endpoint_url,
            access_key=source.access_key,
            secret_key=source.secret_key,
            secure=source.secure,
        )

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
            self.client.fget_object(self.bucket, remote_key, str(local_path))
        except S3Error as e:
            raise RuntimeError(f"Failed to fetch {remote_key} from bucket {self.bucket}: {e}")

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
                key = obj.object_name
                size = obj.size
                modified = obj.last_modified.timestamp()
                hash_id = hashlib.sha256(f"{key}:{size}".encode()).hexdigest()

                relative_path = key[len(self.prefix) :] if key.startswith(self.prefix) else key

                entries.append(
                    PullFileEntry(
                        path=relative_path,
                        size=size,
                        modified_time=modified,
                        hash=hash_id,
                    )
                )

            return entries
        except S3Error as e:
            raise RuntimeError(f"Error accessing MinIO bucket: {e}")
