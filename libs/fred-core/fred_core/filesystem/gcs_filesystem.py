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

import logging
import re
import time
from typing import List, Optional, Set

from fred_core.common.gcs_client import build_gcs_client
from fred_core.filesystem.structures import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)


class GcsFilesystem(BaseFilesystem):
    """
    Async-compatible Google Cloud Storage filesystem with Unix-style utilities.

    Semantics mirror :class:`MinioFilesystem` so that the unified virtual
    filesystem behaves identically across backends:
    - One instance is bound to a single GCS bucket.
    - "Directories" are virtual: they are inferred from object key prefixes and
      can be materialized with a zero-byte ``<dir>/`` marker via :meth:`mkdir`.
    - An optional ``prefix`` lets several logical roots share one bucket.

    Authentication uses Application Default Credentials (ADC): on GKE this is
    Workload Identity, locally it is ``gcloud auth application-default login`` or
    the ``GOOGLE_APPLICATION_CREDENTIALS`` escape hatch. No JSON key is required
    in source or config.
    """

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "",
        project_id: Optional[str] = None,
    ):
        """
        Bind to a GCS bucket using ADC. The bucket is referenced lazily; no
        network call (and therefore no extra IAM permission) is required at
        construction time, so the app boots even with least-privilege SAs.

        Args:
            bucket_name (str): Target GCS bucket (must already exist).
            prefix (str): Optional base key prefix shared by every operation.
            project_id (str | None): GCP project; inferred from ADC when empty.
        """
        self.bucket_name = bucket_name
        # Configured base prefix (e.g. "vfs"). Normalized without surrounding slashes.
        self.base_prefix = (prefix or "").strip("/")
        # Prefix injected externally by the app if needed (mirrors MinioFilesystem).
        self.prefix: str | None = None

        self.client = build_gcs_client(project_id)
        self.bucket = self.client.bucket(bucket_name)

    def health_check(self) -> dict:
        """Verify object-level access to the bucket via ADC / Workload Identity.

        Lists a single object (``storage.objects.list``) — the exact access path
        the app uses — rather than ``bucket.exists()`` (``storage.buckets.get``),
        which the least-privilege ``roles/storage.objectAdmin`` does NOT grant.
        Raises (403/404) if credentials, network, or object access are broken, so
        the readiness probe fails fast with a clear signal.
        """
        started = time.monotonic()
        # Force one objects.list page; confirms credentials + network + object access.
        next(iter(self.client.list_blobs(self.bucket_name, max_results=1)), None)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "[GCS_HEALTH] filesystem bucket=%s object access ok in %dms",
            self.bucket_name,
            elapsed_ms,
        )
        return {"backend": "gcs", "bucket": self.bucket_name, "elapsed_ms": elapsed_ms}

    def _effective_prefix(self) -> str:
        """Return the combined base + externally-injected prefix, slash-free."""
        parts = [
            p.strip("/")
            for p in (self.base_prefix, (self.prefix or ""))
            if p and p.strip("/")
        ]
        return "/".join(parts)

    def _resolve_path(self, path: str) -> str:
        """
        Normalize a user path into a bucket key, applying the effective prefix
        and preventing it from being applied twice (keys returned by ``list``
        already carry the prefix and may be passed straight back in).
        """
        path = path.lstrip("/")
        eff = self._effective_prefix()
        if not eff:
            return path
        if path == eff or path.startswith(eff + "/"):
            return path
        return f"{eff}/{path}" if path else eff

    # --- Core FS API ---

    async def read(self, path: str) -> bytes:
        """Read the full contents of an object as raw bytes."""
        resolved = self._resolve_path(path)
        logger.info("[GCS_READ] bucket=%s path=%s", self.bucket_name, resolved)
        blob = self.bucket.blob(resolved)
        try:
            return blob.download_as_bytes()
        except NotFound as e:
            raise FileNotFoundError(f"Object not found: {path}") from e

    async def write(self, path: str, data: bytes | str) -> None:
        """
        Write data to an object. Accepts bytes or a UTF-8 string.

        Mirrors the MinIO backend: the parent "directory" must exist (i.e. at
        least one object lives under the parent prefix), so callers must
        ``mkdir`` first. This keeps VFS behaviour identical across backends.
        """
        full = self._resolve_path(path)
        data_bytes = data.encode("utf-8") if isinstance(data, str) else data

        logger.info(
            "[GCS_WRITE] bucket=%s path=%s bytes=%d",
            self.bucket_name,
            full,
            len(data_bytes),
        )

        parent = "/".join(full.rstrip("/").split("/")[:-1])
        if parent:
            children = list(
                self.client.list_blobs(
                    self.bucket_name, prefix=parent + "/", max_results=1
                )
            )
            if not children:
                raise FileNotFoundError(
                    f"Parent path '{parent}' does not exist. Cannot write '{full}'."
                )

        blob = self.bucket.blob(full)
        blob.upload_from_string(data_bytes)

    async def list(self, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        """List files and inferred virtual directories under a prefix."""
        full_prefix = self._resolve_path(prefix)
        # GCS prefixes are raw string matches, so a configured root like "team-a"
        # would also return "team-alpha/..." objects. Terminate the prefix with a
        # slash so listings stay inside the directory boundary; an empty prefix
        # (whole-bucket listing) is preserved as-is.
        list_prefix = f"{full_prefix.rstrip('/')}/" if full_prefix else ""
        logger.info("[GCS_LIST] bucket=%s prefix=%s", self.bucket_name, list_prefix)

        all_blobs = list(self.client.list_blobs(self.bucket_name, prefix=list_prefix))
        results: List[FilesystemResourceInfoResult] = []

        for blob in all_blobs:
            # Skip the zero-byte directory markers themselves; their presence is
            # reflected through the inferred-directory pass below.
            if blob.name.endswith("/"):
                continue
            results.append(
                FilesystemResourceInfoResult(
                    path=blob.name,
                    size=blob.size,
                    type=FilesystemResourceInfo.FILE,
                    modified=blob.updated,
                )
            )

        dirs: Set[str] = set()
        for blob in all_blobs:
            parts = blob.name.rstrip("/").split("/")
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))

        for d in dirs:
            if not any(r.path == d and r.is_dir() for r in results):
                results.append(
                    FilesystemResourceInfoResult(
                        path=d,
                        size=None,
                        type=FilesystemResourceInfo.DIRECTORY,
                        modified=None,
                    )
                )

        results.sort(key=lambda x: x.path)
        return results

    async def delete(self, path: str) -> None:
        """
        Delete an object, or recursively delete a virtual directory and its
        contents (including the zero-byte marker), matching the MinIO backend.
        """
        resolved = self._resolve_path(path)
        logger.info("[GCS_DELETE] bucket=%s path=%s", self.bucket_name, resolved)

        prefix = resolved.rstrip("/") + "/"
        for blob in list(self.client.list_blobs(self.bucket_name, prefix=prefix)):
            try:
                blob.delete()
            except NotFound:
                logger.warning("[GCS_DELETE] already gone: %s", blob.name)

        # Delete the object itself and a possible directory marker.
        for key in (resolved, prefix):
            try:
                self.bucket.blob(key).delete()
            except NotFound:
                logger.warning("[GCS_DELETE] already gone: %s", key)

    async def print_root_dir(self) -> str:
        """Return the logical root URI in ``gs://bucket/prefix`` form."""
        eff = self._effective_prefix()
        return f"gs://{self.bucket_name}/{eff}" if eff else f"gs://{self.bucket_name}"

    async def mkdir(self, path: str) -> None:
        """
        Materialize a virtual directory as a zero-byte ``<dir>/`` marker object
        so it appears in listings and satisfies the parent-exists check in
        :meth:`write` (same convention as the MinIO backend).
        """
        dir_path = self._resolve_path(path).rstrip("/") + "/"
        logger.info("[GCS_MKDIR] bucket=%s path=%s", self.bucket_name, dir_path)
        self.bucket.blob(dir_path).upload_from_string(b"")

    async def exists(self, path: str) -> bool:
        """Return True if the object exists or any object shares its prefix."""
        full = self._resolve_path(path)
        if self.bucket.blob(full).exists():
            return True
        children = list(
            self.client.list_blobs(
                self.bucket_name, prefix=full.rstrip("/") + "/", max_results=1
            )
        )
        return len(children) > 0

    async def cat(self, path: str) -> str:
        """Read an object and decode it as UTF-8."""
        data = await self.read(path)
        return data.decode("utf-8")

    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        """
        Return metadata for a file, or report a virtual directory when no object
        exists at the exact key (directories are virtual, as in MinIO).
        """
        full = self._resolve_path(path)
        blob = self.bucket.get_blob(full)
        if blob is not None:
            return FilesystemResourceInfoResult(
                path=full,
                size=blob.size,
                type=FilesystemResourceInfo.FILE,
                modified=blob.updated,
            )
        return FilesystemResourceInfoResult(
            path=full,
            size=None,
            type=FilesystemResourceInfo.DIRECTORY,
            modified=None,
        )

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        """Search for a regex pattern across files under a prefix."""
        regex = re.compile(pattern)
        full_prefix = self._resolve_path(prefix)
        matches: List[str] = []

        for entry in await self.list(full_prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)

        return matches
