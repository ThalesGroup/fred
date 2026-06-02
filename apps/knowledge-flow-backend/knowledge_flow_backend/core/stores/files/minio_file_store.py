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


import hashlib
import logging
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from knowledge_flow_backend.core.stores.files.base_file_store import BaseFileStore, FileInfo

logger = logging.getLogger(__name__)


class MinioFileStore(BaseFileStore):
    """
    Minimal MinIO-backed file store for PoC usage.
    Bytes in, bytes out. Stores objects under `{namespace}/{key}`.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket_name: str, secure: bool):
        self.bucket_name = bucket_name

        parsed = urlparse(endpoint)
        if parsed.path and parsed.path != "/":
            raise RuntimeError(
                f"❌ Invalid MinIO endpoint: '{endpoint}'.\n"
                "👉 The endpoint must not include a path. Use only scheme://host:port.\n"
                "   Example: 'http://localhost:9000', NOT 'http://localhost:9000/minio'"
            )

        clean_endpoint = endpoint.replace("https://", "").replace("http://", "")

        try:
            self.client = Minio(clean_endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        except ValueError as e:
            logger.error(f"❌ Failed to initialize MinIO client: {e}")
            raise

        # Ensure bucket exists (create if missing)
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(f"✅ Bucket '{bucket_name}' created.")

    # -------- BaseFileStore interface --------

    def put(self, namespace: str, key: str, content: bytes, content_type: str = "application/octet-stream") -> FileInfo:
        object_name = _object_name(namespace, key)
        sha256 = hashlib.sha256(content).hexdigest()

        try:
            self.client.put_object(
                self.bucket_name,
                object_name,
                data=BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
            logger.info(f"📤 Uploaded '{object_name}' to bucket '{self.bucket_name}'")
        except S3Error as e:
            logger.error(f"❌ Failed to upload '{object_name}': {e}")
            raise ValueError(f"Upload failed for '{object_name}': {e}")

        return FileInfo(
            uri=f"s3://{self.bucket_name}/{object_name}",
            size_bytes=len(content),
            content_type=content_type,
            checksum_sha256=sha256,
        )

    def get(self, namespace: str, key: str) -> bytes:
        object_name = _object_name(namespace, key)
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            return data
        except S3Error as e:
            logger.error(f"❌ Failed to download '{object_name}': {e}")
            raise FileNotFoundError(f"Object not found: {object_name}") from e

    def list(self, namespace: str, prefix: str = "") -> list[str]:
        full_prefix = f"{namespace.strip('/')}/{prefix.lstrip('/')}" if prefix else namespace.strip("/")
        try:
            objs = self.client.list_objects(self.bucket_name, prefix=full_prefix, recursive=True)
            out = []
            base = namespace.strip("/") + "/"
            for o in objs:
                if o.object_name and o.object_name.startswith(base):
                    out.append(o.object_name[len(base) :])
            return out
        except S3Error as e:
            logger.error(f"❌ Failed to list '{full_prefix}': {e}")
            raise


def _object_name(namespace: str, key: str) -> str:
    ns = namespace.strip("/")
    k = key.lstrip("/")
    return f"{ns}/{k}" if ns else k
