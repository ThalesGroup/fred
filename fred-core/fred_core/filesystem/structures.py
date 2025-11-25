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

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Literal, Protocol


class BaseFilesystem(Protocol):
    """
    Base protocol for asynchronous filesystem operations.

    Implementations can be local, cloud-based (S3/MinIO), or virtual.
    All methods are async-compatible.
    """

    async def read(self, path: str) -> bytes:
        """
        Read the contents of a file.

        Args:
            path (str): Path to the file relative to the filesystem root.

        Returns:
            bytes: File content as bytes.
        
        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: For general read errors.
        """
        ...

    async def write(self, path: str, data: bytes) -> None:
        """
        Write data to a file, creating directories as needed.

        Args:
            path (str): Path to the file relative to the filesystem root.
            data (bytes): Data to write.

        Raises:
            IOError: If writing fails.
        """
        ...

    async def list(self, prefix: str = "") -> List[str]:
        """
        List all files under a given prefix/directory.

        Args:
            prefix (str, optional): Directory prefix to list. Defaults to "" (root).

        Returns:
            List[str]: List of relative file paths.
        """
        ...

    async def delete(self, path: str) -> None:
        """
        Delete a file at the specified path.

        Args:
            path (str): Path to the file relative to the filesystem root.

        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If deletion fails.
        """
        ...

    async def pwd(self) -> str:
        """
        Return the logical root path of the filesystem.

        For local filesystems, this is an absolute directory path.
        For MinIO/S3, this is the endpoint plus bucket (e.g., http://host:port/bucket).

        Returns:
            str: Filesystem root path or URI.
        """
        ...

    # --- Unix-style utilities ---

    async def mkdir(self, path: str) -> None:
        """
        Simulate a directory in MinIO by relying on the prefix.
        
        No placeholder object is created. 
        A "directory" exists if at least one object has that prefix.

        Args:
            path (str): Directory path relative to the bucket.
        """
        # Nothing is created in the bucket for an empty directory.
        # The directory will implicitly exist once a file is written under this prefix.
        pass


    async def exists(self, path: str) -> bool:
        """
        Check if a file or directory exists at the given path.

        Args:
            path (str): Path relative to the filesystem root.

        Returns:
            bool: True if the file or directory exists, False otherwise.
        """
        ...

    async def cat(self, path: str) -> str:
        """
        Read a file and return its contents as a string.

        Args:
            path (str): Path relative to the filesystem root.

        Returns:
            str: File contents as a UTF-8 string.
        """
        ...

    async def stat(self, path: str) -> dict[str, Any]:
        """
        Return metadata about a file or directory.

        Args:
            path (str): Path relative to the filesystem root.

        Returns:
            dict: Metadata including:
                - size (int | None): Size in bytes (None for directories if unknown)
                - type (str): "file" or "directory"
                - modified (datetime | None): Last modification time
        """
        ...

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        """
        Search for files containing a regex pattern under a given prefix.

        Args:
            pattern (str): Regular expression to search for.
            prefix (str, optional): Directory prefix to search under. Defaults to root.

        Returns:
            List[str]: List of file paths matching the pattern.
        """
        ...

class StatResource:
    FILE = "file"
    DIRECTORY = "directory"

@dataclass
class StatResult:
    """
    Represents metadata about a file or directory.
    """
    size: int | None
    type: Literal[StatResource.FILE, StatResource.DIRECTORY]
    modified: datetime | None

    def is_file(self) -> bool:
        """Return True if the object is a file."""
        return self.type == StatResource.FILE

    def is_dir(self) -> bool:
        """Return True if the object is a directory."""
        return self.type == StatResource.DIRECTORY

    def __repr__(self) -> str:
        size_str = f"{self.size} bytes" if self.size is not None else "Unknown size"
        mod_str = self.modified.isoformat() if self.modified else "Unknown"
        return f"<StatResult type={self.type} size={size_str} modified={mod_str}>"