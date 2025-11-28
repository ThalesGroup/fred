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

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket_name: str, secure: bool):
        """
        Initialize MinIO client and ensure bucket exists.

        Args:
            endpoint (str): MinIO/S3 endpoint (scheme://host:port, no path)
            access_key (str): Access key
            secret_key (str): Secret key
            bucket_name (str): Bucket to use
            secure (bool): Whether to use TLS (https)
        """
        parsed = urlparse(endpoint)
        if parsed.path not in (None, "") and parsed.path != "/":
            raise RuntimeError(f"Invalid MinIO endpoint: '{endpoint}'. Must not include path.")
        
        self._clean_endpoint = parsed.netloc or endpoint.replace("https://", "").replace("http://", "")
        self.secure = secure
        self.bucket_name = bucket_name

        self.client = Minio(
            self._clean_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )

        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(f"Bucket '{bucket_name}' created.")

    # --- Core FS API ---

    async def read(self, path: str) -> bytes:
        obj = self.client.get_object(self.bucket_name, path)
        data = obj.read()
        obj.close()
        return data

    async def write(self, path: str, data: bytes | str) -> None:
        """
        Write data to a file in MinIO. Accepts both bytes and str.
        Will raise an error if the parent "directory" does not exist.
        """
        if isinstance(data, str):
            data_bytes = data.encode("utf-8")
        else:
            data_bytes = data

        # Check that parent prefix exists
        parent = "/".join(path.rstrip("/").split("/")[:-1])
        if parent:
            # list_objects with recursive=False checks direct children only
            objs = list(self.client.list_objects(self.bucket_name, prefix=parent + "/", recursive=False))
            if not objs:
                raise FileNotFoundError(f"Parent path '{parent}' does not exist. Cannot write '{path}'.")

        self.client.put_object(
            self.bucket_name,
            path,
            data=BytesIO(data_bytes),
            length=len(data_bytes)
        )

    async def list(self, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        """
        List all files and "directories" in the bucket under the given prefix,
        returning FilesystemResourceInfoResult objects for each.

        Args:
            prefix (str): Object key prefix (like a folder path).

        Returns:
            List[FilesystemResourceInfoResult]: List of files and directories.
        """
        all_objects = list(self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True))
        results: List[FilesystemResourceInfoResult] = []

        # Files
        for obj in all_objects:
            results.append(FilesystemResourceInfoResult(
                path=obj.object_name,
                size=obj.size,
                type=FilesystemResourceInfo.FILE,
                modified=obj.last_modified
            ))

        # Infer directories from prefixes
        dirs: Set[str] = set()
        for obj in all_objects:
            parts = obj.object_name.split("/")
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))

        for d in dirs:
            if not any(r.path == d and r.type == FilesystemResourceInfo.DIRECTORY for r in results):
                results.append(FilesystemResourceInfoResult(
                    path=d,
                    size=None,
                    type=FilesystemResourceInfo.DIRECTORY,
                    modified=None
                ))

        # Sort by path to emulate 'ls -alh'
        results.sort(key=lambda x: x.path)
        return results

    async def delete(self, path: str) -> None:
        self.client.remove_object(self.bucket_name, path)

    async def pwd(self) -> str:
        """Return the logical root URI of the filesystem."""
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self._clean_endpoint}/{self.bucket_name}"

    async def mkdir(self, path: str) -> None:
        """
        Simulate a directory in MinIO by creating a zero-byte object
        with a trailing slash. This ensures the directory appears in listings.
        """
        # Ensure path ends with a slash
        dir_path = path.rstrip("/") + "/"
        
        # Put empty object to represent the directory
        from io import BytesIO
        self.client.put_object(
            self.bucket_name,
            dir_path,
            data=BytesIO(b""),
            length=0
        )
    async def exists(self, path: str) -> bool:
        """
        Check if a file or "directory" exists.

        Returns True if object exists or at least one object has this prefix.
        """
        try:
            self.client.stat_object(self.bucket_name, path)
            return True
        except Exception:
            objs = list(self.client.list_objects(self.bucket_name, prefix=path.rstrip("/") + "/", recursive=False))
            return len(objs) > 0

    async def cat(self, path: str) -> str:
        """Read a file and return its content as a UTF-8 string."""
        data = await self.read(path)
        return data.decode("utf-8")


    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        """
        Return metadata about a file or "directory" as a FilesystemResourceInfoResult.
        In MinIO, directories are virtual: even empty prefixes are reported as directories.

        Args:
            path (str): Object key or directory prefix.

        Returns:
            FilesystemResourceInfoResult
        """
        try:
            # Try as a file
            obj = self.client.stat_object(self.bucket_name, path)
            return FilesystemResourceInfoResult(
                path=path,
                size=obj.size,
                type=FilesystemResourceInfo.FILE,
                modified=obj.last_modified
            )
        except Exception:
            # File not found, treat as directory (even if empty)
            prefix = path.rstrip("/") + "/"
            objs = list(self.client.list_objects(self.bucket_name, prefix=prefix, recursive=False))
            return FilesystemResourceInfoResult(
                path=path,
                size=None,
                type=FilesystemResourceInfo.DIRECTORY,
                modified=None
            )
        
    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        regex = re.compile(pattern)
        matches = []
        for entry in await self.list(prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)
        return matches