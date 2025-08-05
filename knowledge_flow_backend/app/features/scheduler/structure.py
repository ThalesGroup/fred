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


from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
import hashlib

from app.common.document_structures import DocumentMetadata, SourceType
from app.core.stores.catalog.base_catalog_store import PullFileEntry


class FileToProcess(BaseModel):
    # Common fields
    source_tag: str
    tags: List[str] = []
    display_name: Optional[str] = None

    # Push-specific
    document_uid: Optional[str] = None  # Present for push files

    # Pull-specific
    external_path: Optional[str] = None
    size: Optional[int] = None
    modified_time: Optional[float] = None  # Unix timestamp
    hash: Optional[str] = None  # Optional, used for UID

    def is_pull(self) -> bool:
        return self.external_path is not None

    def is_push(self) -> bool:
        return not self.is_pull()

    @classmethod
    def from_pull_entry(cls, entry: PullFileEntry, source_tag: str) -> "FileToProcess":
        return cls(
            source_tag=source_tag,
            external_path=entry.path,
            size=entry.size,
            modified_time=entry.modified_time,
            hash=entry.hash or hashlib.sha256(entry.path.encode()).hexdigest(),
            display_name=Path(entry.path).name,
        )

    def to_virtual_metadata(self) -> DocumentMetadata:
        if not self.is_pull():
            raise ValueError("Virtual metadata can only be generated for pull files")
        assert self.external_path, "Pull files must have an external path"
        modified_dt = datetime.fromtimestamp(self.modified_time or 0, tz=timezone.utc)

        return DocumentMetadata(
            document_name=Path(self.external_path).name,
            document_uid=self.document_uid or f"pull-{self.source_tag}-{self.hash}",
            date_added_to_kb=modified_dt,
            retrievable=False,
            source_tag=self.source_tag,
            pull_location=self.external_path,
            source_type=SourceType.PULL,
            processing_stages={},
            modified=modified_dt,
            tags=self.tags,
        )


class PipelineDefinition(BaseModel):
    name: str
    files: List[FileToProcess]


class ProcessDocumentsRequest(BaseModel):
    files: List[FileToProcess]
    pipeline_name: str
