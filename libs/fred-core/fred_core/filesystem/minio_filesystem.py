# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
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
from io import BytesIO
from typing import List, Set
from urllib.parse import urlparse

from minio import Minio

from fred_core.filesystem.structures import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)

logger = logging.getLogger(__name__)


class MinioFilesystem(BaseFilesystem):
    """
    Async MinIO/S3 filesystem with Unix-style utilities.

    Each instance is tied to a single bucket.
    Dossiers sont simulés via préfixe.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool,
    ):
        """
        Initialize a MinIO client and create the bucket if it does not exist.

        Args:
            endpoint (str): MinIO endpoint in the format scheme://host:port, without a path.
            access_key (str): Access key.
            secret_key (str): Secret key.
            bucket_name (str): Name of the bucket to use.
            secure (bool): Whether to use TLS.
        """
        parsed = urlparse(endpoint)
        if parsed.path not in (None, "") and parsed.path != "/":
            raise RuntimeError(
                f"Invalid MinIO endpoint: '{endpoint}'. Must not include path."
            )

        self._clean_endpoint = parsed.netloc or endpoint.replace(
            "https://", ""
        ).replace("http://", "")
        self.secure = secure
        self.bucket_name = bucket_name

        self.client = Minio(
            self._clean_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

        # Prefix injected externally by the app if needed (ex: user_id/)
        self.prefix: str | None = None

        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(f"Bucket '{bucket_name}' created.")

    def _resolve_path(self, path: str) -> str:
        """
        Normalize a MinIO path and prevent escaping the assigned namespace.
        Removes redundant slashes and automatically applies the prefix if defined.

        Args:
            path (str): User-provided path.

        Returns:
            str: Normalized and safe path.
        """

        path = path.lstrip("/")

        if not self.prefix:
            resolved = path
        else:
            # Remove existing prefix if present
            stripped = path
            if stripped.startswith(self.prefix):
                stripped = stripped[len(self.prefix) :]
            resolved = f"{self.prefix}{stripped}"

        logger.debug(
            "[MINIO_RESOLVE] bucket=%s prefix=%s input=%s resolved=%s",
            self.bucket_name,
            self.prefix,
            path,
            resolved,
        )
        return resolved

    # --- Core FS API ---

    async def read(self, path: str) -> bytes:
        """
        Read the contents of a file from MinIO as raw bytes.

        This method retrieves the object at the specified path and returns its
        complete content as a bytes object.

        Args:
            path (str): The path of the object to read.

        Returns:
            bytes: The full content of the object.
        """
        resolved = self._resolve_path(path)
        logger.info("[MINIO_READ] bucket=%s path=%s", self.bucket_name, resolved)
        obj = self.client.get_object(self.bucket_name, resolved)
        data = obj.read()
        obj.close()
        return data

    async def write(self, path: str, data: bytes | str) -> None:
        """
        Write data to a MinIO file. Accepts bytes or a string.
        Raises an error if the parent directory does not exist.

        Args:
            path (str): Target path.
            data (bytes | str): Content to write.
        """
        full = self._resolve_path(path)

        if isinstance(data, str):
            data_bytes = data.encode("utf-8")
        else:
            data_bytes = data

        logger.info(
            "[MINIO_WRITE] bucket=%s path=%s bytes=%d",
            self.bucket_name,
            full,
            len(data_bytes),
        )

        parent = "/".join(full.rstrip("/").split("/")[:-1])
        if parent:
            # list_objects with recursive=False checks direct children only
            objs = list(
                self.client.list_objects(
                    self.bucket_name, prefix=parent + "/", recursive=False
                )
            )
            if not objs:
                raise FileNotFoundError(
                    f"Parent path '{parent}' does not exist. Cannot write '{full}'."
                )

        self.client.put_object(
            self.bucket_name, full, data=BytesIO(data_bytes), length=len(data_bytes)
        )

    async def list(self, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        """
        List files and virtual directories under a given prefix.
        Returns a list of FilesystemResourceInfoResult objects.

        Args:
            prefix (str): Object key prefix, like a folder path.

        Returns:
            List[FilesystemResourceInfoResult]: List of files and directories.
        """
        full_prefix = self._resolve_path(prefix)
        logger.info("[MINIO_LIST] bucket=%s prefix=%s", self.bucket_name, full_prefix)

        all_objects = list(
            self.client.list_objects(
                self.bucket_name, prefix=full_prefix, recursive=True
            )
        )
        results: List[FilesystemResourceInfoResult] = []

        # Files
        for obj in all_objects:
            if obj.object_name is not None:
                results.append(
                    FilesystemResourceInfoResult(
                        path=obj.object_name,
                        size=obj.size,
                        type=FilesystemResourceInfo.FILE,
                        modified=obj.last_modified,
                    )
                )

        # Infer directories from prefixes
        dirs: Set[str] = set()
        for obj in all_objects:
            if obj.object_name is not None:
                parts = obj.object_name.split("/")
                for i in range(1, len(parts)):
                    dirs.add("/".join(parts[:i]))

        for d in dirs:
            if not any(
                r.path == d and r.type == FilesystemResourceInfo.DIRECTORY
                for r in results
            ):
                results.append(
                    FilesystemResourceInfoResult(
                        path=d,
                        size=None,
                        type=FilesystemResourceInfo.DIRECTORY,
                        modified=None,
                    )
                )

        # Sort by path to emulate 'ls -alh'
        results.sort(key=lambda x: x.path)
        return results

    async def delete(self, path: str) -> None:
        """
        Delete a file or object from the bucket.

        Args:
            path (str): Path of the object to delete.
        """

        resolved = self._resolve_path(path)
        logger.info("[MINIO_DELETE] bucket=%s path=%s", self.bucket_name, resolved)
        self.client.remove_object(self.bucket_name, resolved)

    async def print_root_dir(self) -> str:
        """
        Return the logical root URI of the filesystem.

        Returns:
            str: Root URI in the format scheme://host/bucket.
        """
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self._clean_endpoint}/{self.bucket_name}"

    async def mkdir(self, path: str) -> None:
        """
        Simulate a directory in MinIO by creating a zero-byte object
        with a trailing slash. This ensures the directory appears in listings.

        Args:
            path (str): Directory path to create.
        """

        # Ensure path ends with a slash
        dir_path = self._resolve_path(path).rstrip("/") + "/"
        logger.info("[MINIO_MKDIR] bucket=%s path=%s", self.bucket_name, dir_path)

        # Put empty object to represent the directory
        from io import BytesIO

        self.client.put_object(self.bucket_name, dir_path, data=BytesIO(b""), length=0)

    async def exists(self, path: str) -> bool:
        """
        Check if a file or "directory" exists.
        Returns True if the object exists or at least one object has this prefix.

        Args:
            path (str): Path to check.

        Returns:
            bool: True if the file or directory exists.
        """

        full = self._resolve_path(path)
        try:
            logger.info("[MINIO_EXISTS] stat bucket=%s path=%s", self.bucket_name, full)
            self.client.stat_object(self.bucket_name, full)
            return True
        except Exception:
            objs = list(
                self.client.list_objects(
                    self.bucket_name, prefix=full.rstrip("/") + "/", recursive=False
                )
            )
            logger.info(
                "[MINIO_EXISTS] list bucket=%s prefix=%s count=%d",
                self.bucket_name,
                full.rstrip("/") + "/",
                len(objs),
            )
            return len(objs) > 0

    async def cat(self, path: str) -> str:
        """
        Read the contents of a file from MinIO and decode it as UTF-8.

        This method retrieves the object at the specified path, reads its content,
        and returns it as a string. Use this for text files.

        Args:
            path (str): The path of the file to read.

        Returns:
            str: The content of the file decoded as UTF-8.
        """
        data = await self.read(path)
        return data.decode("utf-8")

    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        """
        Return metadata about a file or "directory" as a FilesystemResourceInfoResult.
        In MinIO, directories are virtual: even empty prefixes are reported as directories.

        Args:
            path (str): Object key or directory prefix.

        Returns:
            FilesystemResourceInfoResult: Metadata including type, size, and modification date.
        """
        full = self._resolve_path(path)
        try:
            logger.info("[MINIO_STAT] file bucket=%s path=%s", self.bucket_name, full)
            # Try as a file
            obj = self.client.stat_object(self.bucket_name, full)
            return FilesystemResourceInfoResult(
                path=full,
                size=obj.size,
                type=FilesystemResourceInfo.FILE,
                modified=obj.last_modified,
            )
        except Exception:
            logger.info(
                "[MINIO_STAT] treat-as-dir bucket=%s path=%s", self.bucket_name, full
            )
            # File not found, treat as directory (even if empty)
            # cd freprefix = full.rstrip("/") + "/"
            # objs = list(self.client.list_objects(self.bucket_name, prefix=prefix, recursive=False))
            return FilesystemResourceInfoResult(
                path=full,
                size=None,
                type=FilesystemResourceInfo.DIRECTORY,
                modified=None,
            )

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        """
        Search for a regex pattern in files under a given prefix.
        Returns a list of paths where the pattern matches.

        Args:
            pattern (str): Regular expression pattern to search for.
            prefix (str): Object key prefix to limit the search.

        Returns:
            List[str]: Paths of files matching the pattern.
        """
        regex = re.compile(pattern)
        full_prefix = self._resolve_path(prefix)
        matches = []

        for entry in await self.list(full_prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)

        return matches
