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
from typing import List, Literal, Protocol


class BaseFilesystem(Protocol):
    """
    Base protocol for asynchronous filesystem operations.

    Implementations can be local, cloud-based (S3/MinIO), or virtual.
    All methods are async-compatible.
    """

    async def read(self, path: str) -> bytes:
        """Read the raw bytes of a file."""
        ...

    async def write(self, path: str, data: bytes | str) -> None:
        """Write data to a file."""
        ...

    async def list(self, prefix: str = "") -> List["FilesystemResourceInfoResult"]:
        """List all files and directories under a given prefix."""
        ...

    async def delete(self, path: str) -> None:
        """Delete a file or directory."""
        ...

    async def print_root_dir(self) -> str:
        """Return the filesystem root (absolute path or bucket URI)."""
        ...

    async def mkdir(self, path: str) -> None:
        """Create a directory."""
        ...

    async def exists(self, path: str) -> bool:
        """Check if a file or directory exists."""
        ...

    async def cat(self, path: str) -> str:
        """Read a file and return it as a UTF-8 string."""
        ...

    async def stat(self, path: str) -> "FilesystemResourceInfoResult":
        """
        Return metadata about a file or directory.

        Returns:
            FilesystemResourceInfoResult
        """
        ...

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        """Search for regex pattern in files under a prefix."""
        ...

class FilesystemResourceInfo:
    FILE = "file"
    DIRECTORY = "directory"

@dataclass
class FilesystemResourceInfoResult:
    """
    Represents metadata about a file or directory.
    """
    path: str
    size: int | None
    type: Literal[FilesystemResourceInfo.FILE, FilesystemResourceInfo.DIRECTORY]
    modified: datetime | None

    def is_file(self) -> bool:
        """Return True if this is a file."""
        return self.type == FilesystemResourceInfo.FILE

    def is_dir(self) -> bool:
        """Return True if this is a directory."""
        return self.type == FilesystemResourceInfo.DIRECTORY

    def __repr__(self) -> str:
        size_str = f"{self.size} bytes" if self.size is not None else "Unknown size"
        mod_str = self.modified.isoformat() if self.modified else "Unknown"
        return f"<FilesystemResourceInfoResult path={self.path} type={self.type} size={size_str} modified={mod_str}>"
