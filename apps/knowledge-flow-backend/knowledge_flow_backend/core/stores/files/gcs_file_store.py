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

import hashlib
import logging
from typing import Optional

from fred_core.common.gcs_client import build_gcs_client
from google.cloud.exceptions import NotFound

from knowledge_flow_backend.core.stores.files.base_file_store import BaseFileStore, FileInfo

logger = logging.getLogger(__name__)


class GcsFileStore(BaseFileStore):
    """
    GCS-backed namespace file store (templates, prompts, model artifacts, ...).

    Bytes in, bytes out. Objects are stored under ``{namespace}/{key}``. Uses
    Application Default Credentials / Workload Identity — no JSON key required.
    The bucket must already exist (referenced lazily, no buckets.create needed).
    """

    def __init__(self, bucket_name: str, project_id: Optional[str] = None):
        self.bucket_name = bucket_name
        self.client = build_gcs_client(project_id)
        self.bucket = self.client.bucket(bucket_name)

    def put(self, namespace: str, key: str, content: bytes, content_type: str = "application/octet-stream") -> FileInfo:
        object_name = _object_name(namespace, key)
        sha256 = hashlib.sha256(content).hexdigest()
        blob = self.bucket.blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        logger.info("📤 Uploaded '%s' to bucket '%s'", object_name, self.bucket_name)
        return FileInfo(
            uri=f"gs://{self.bucket_name}/{object_name}",
            size_bytes=len(content),
            content_type=content_type,
            checksum_sha256=sha256,
        )

    def get(self, namespace: str, key: str) -> bytes:
        object_name = _object_name(namespace, key)
        try:
            return self.bucket.blob(object_name).download_as_bytes()
        except NotFound as e:
            raise FileNotFoundError(f"Object not found: {object_name}") from e

    def list(self, namespace: str, prefix: str = "") -> list[str]:
        full_prefix = f"{namespace.strip('/')}/{prefix.lstrip('/')}" if prefix else namespace.strip("/")
        base = namespace.strip("/") + "/"
        out: list[str] = []
        for blob in self.client.list_blobs(self.bucket_name, prefix=full_prefix):
            if blob.name.startswith(base):
                out.append(blob.name[len(base) :])
        return out


def _object_name(namespace: str, key: str) -> str:
    ns = namespace.strip("/")
    k = key.lstrip("/")
    return f"{ns}/{k}" if ns else k
