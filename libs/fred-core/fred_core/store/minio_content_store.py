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

from __future__ import annotations

import io
import logging
from datetime import timedelta
from typing import BinaryIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


def _clean_endpoint(endpoint: str) -> str:
    """Normalize endpoint format before creating a MinIO client.

    Why this exists:
    - MinIO clients expect only host[:port].
    - Paths in endpoint values are configuration mistakes and would route to
      wrong URLs.

    Example:
    ```python
    _clean_endpoint("http://localhost:9000")  # "localhost:9000"
    ```
    """

    parsed = urlparse(endpoint)
    if parsed.path not in ("", "/"):
        raise RuntimeError(
            f"Invalid MinIO endpoint '{endpoint}'. Paths are not allowed."
        )
    return parsed.netloc or endpoint.replace("https://", "").replace("http://", "")


class MinioContentStore:
    """Content store backed by MinIO / S3-compatible object storage.

    Why this exists:
    - Production mode needs durable object storage.
    - Services can upload files and later return temporary download URLs.

    Basic usage:
    ```python
    from io import BytesIO
    from fred_core.store import MinioContentStore

    store = MinioContentStore(
        endpoint="localhost:9000",
        access_key="minio",
        secret_key="<MINIO_SECRET_KEY>",
        bucket_name="fred-objects",
        secure=False,
    )
    store.put_object("teams/t1/banner.png", BytesIO(b"..."), content_type="image/png")
    url = store.get_presigned_url("teams/t1/banner.png")
    ```
    """

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool,
        public_endpoint: str | None = None,
        public_secure: bool | None = None,
    ) -> None:
        """Create clients for write operations and public presigned URLs.

        Why there are two clients:
        - Internal backend endpoint can differ from frontend-visible endpoint.
        - `client` writes objects.
        - `public_client` builds URLs users can actually reach.
        """

        clean_endpoint = _clean_endpoint(endpoint)
        self.object_bucket = bucket_name

        self.client = Minio(
            clean_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        if not self.client.bucket_exists(self.object_bucket):
            self.client.make_bucket(self.object_bucket)

        effective_public_endpoint = public_endpoint or endpoint
        parsed_public = urlparse(effective_public_endpoint)
        clean_public_endpoint = _clean_endpoint(effective_public_endpoint)
        if public_secure is not None:
            resolved_public_secure = public_secure
        elif parsed_public.scheme:
            resolved_public_secure = parsed_public.scheme == "https"
        else:
            resolved_public_secure = secure

        self.public_client = Minio(
            clean_public_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=resolved_public_secure,
        )

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Remove a leading slash so MinIO object names stay consistent.

        Example:
        ```python
        MinioContentStore._normalize_key("/a/b.txt")  # "a/b.txt"
        ```
        """

        return key.lstrip("/")

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        """Upload bytes to MinIO under `key`.

        Use this for any binary payload (image, pdf, json export, etc.).

        Example:
        ```python
        from io import BytesIO
        store.put_object("exports/run-42.json", BytesIO(b"{}"), content_type="application/json")
        ```
        """

        object_name = self._normalize_key(key)
        payload = stream.read()
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self.client.put_object(
            self.object_bucket,
            object_name,
            data=io.BytesIO(payload),
            length=len(payload),
            content_type=content_type or "application/octet-stream",
        )

    def get_presigned_url(
        self, key: str, expires: timedelta = timedelta(hours=1)
    ) -> str:
        """Create a temporary download URL for object `key`.

        Use this when the API should return a direct file link to the UI.

        Example:
        ```python
        from datetime import timedelta
        url = store.get_presigned_url("exports/run-42.json", expires=timedelta(minutes=30))
        ```

        Raises:
            FileNotFoundError: object or bucket does not exist.
            S3Error: unexpected MinIO error.
        """

        object_name = self._normalize_key(key)
        try:
            return self.public_client.presigned_get_object(
                self.object_bucket,
                object_name,
                expires=expires,
            )
        except S3Error as exc:
            if getattr(exc, "code", "") in {
                "NoSuchKey",
                "NoSuchObject",
                "NoSuchBucket",
            }:
                raise FileNotFoundError(f"Object not found: {key}") from exc
            logger.error("Failed to generate presigned URL for key=%s: %s", key, exc)
            raise
