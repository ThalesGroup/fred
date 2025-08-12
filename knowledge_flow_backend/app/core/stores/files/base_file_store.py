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

from abc import ABC, abstractmethod
from app.core.stores.files.structures import FileInfo

class BaseFileStore(ABC):
    """
    Minimal abstract interface for a namespace-based file store.

    This store is intended to manage binary resources (e.g., templates, documents, prompts)
    that can be accessed by agents or users in a unified way across different backends 
    (e.g., local filesystem, S3/MinIO, HTTP, etc.).

    The API abstracts away storage details behind a clean, strongly typed contract.
    All paths are scoped within named 'namespaces' for logical isolation (e.g. 'templates', 'prompts').

    Implementations MUST ensure:
    - Keys are always relative to the given namespace
    - Namespace + key uniquely identifies a file
    - Keys use POSIX-style forward slashes (`/`) as path separators
    """

    @abstractmethod
    def put(
        self,
        namespace: str,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> FileInfo:
        """
        Store a file at the given namespace/key location.

        Parameters:
            namespace (str): Logical bucket (e.g. 'templates', 'prompts', 'datasets').
            key (str): Path within the namespace (e.g. 'cir-summary/v1.md').
            content (bytes): Raw binary content to store.
            content_type (str): MIME type of the content (e.g. 'text/markdown', 'application/json').

        Returns:
            FileInfo: Structured metadata for the stored file, including its full URI, size, MIME type, and checksum.

        Raises:
            Exception: Implementation-specific errors (e.g. permission denied, storage unavailable).
        """
        ...

    @abstractmethod
    def get(self, namespace: str, key: str) -> bytes:
        """
        Retrieve a file's raw content from the store.

        Parameters:
            namespace (str): Logical bucket where the file is stored.
            key (str): Relative path within the namespace.

        Returns:
            bytes: Raw binary content of the file.

        Raises:
            FileNotFoundError: If the file does not exist.
            Exception: Any other retrieval error (network, permissions, etc.).
        """
        ...

    @abstractmethod
    def list(self, namespace: str, prefix: str = "") -> list[str]:
        """
        List all files in a given namespace (optionally filtered by prefix).

        Parameters:
            namespace (str): Logical bucket to scan (e.g. 'templates').
            prefix (str): Optional prefix to filter results (e.g. 'cir-summary/')

        Returns:
            list[str]: A flat list of keys (relative paths within the namespace), e.g.
                       ['cir-summary/v1.md', 'cir-summary/v2.md', 'other-template/v1.md']

        Notes:
            - Implementations must return keys using POSIX-style paths.
            - Returned keys MUST NOT include the namespace itself.
            - Keys may be used directly in subsequent `get()` or `put()` calls with the same namespace.

        Raises:
            Exception: If listing fails (e.g., namespace not found, storage error).
        """
        ...
