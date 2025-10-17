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

from typing import List, Protocol

from pydantic import BaseModel


class PullFileEntry(BaseModel):
    path: str  # Relative path from base pull location (e.g. "reports/2024/q2.pdf")
    size: int  # Size in bytes
    modified_time: float  # Unix timestamp (last modified time)
    hash: str  # SHA256 hash of path, precomputed or generated during scan


# ------------------------------------------------------------------------------
# BaseCatalogStore defines a portable interface for cataloging pull-mode documents
# across different storage backends (e.g., DuckDB today, ClickHouse later).
#
# The catalog itself serves multiple essential purposes:
#
# 1. Performance: Avoids expensive directory scans or remote listings (e.g., S3, WebDAV)
#    every time the UI or backend wants to explore pull-mode sources.
#
# 2. Filtering/Search: Enables fast querying of metadata like filename, extension,
#    size, and modification date — even across thousands of files.
#
# 3. Consistency: Allows Temporal workflows or agents to use a consistent view of
#    available files without reloading them dynamically.
#
# 4. Portability: Supports flexible migration to scalable backends later by keeping
#    a clean and backend-agnostic interface.
#
# 5. Caching/Snapshots: Useful for incremental processing, change detection, and
#    eventually correlating catalog entries with ingestion status.
#
# In short: the catalog is a lightweight, queryable index of pull-source files.
# ------------------------------------------------------------------------------


class BaseCatalogStore(Protocol):
    def save_entries(self, source_tag: str, entries: List[PullFileEntry]) -> None: ...
    def list_entries(self, source_tag: str) -> List[PullFileEntry]: ...
    def add_entries(self, source_tag: str, entries: List[PullFileEntry]) -> None: ...
    def delete_entries(self, source_tag: str, entries: List[PullFileEntry]) -> None: ...
