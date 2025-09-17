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


import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fred_core import KeycloakUser
from pydantic import BaseModel

from app.common.document_structures import AccessInfo, DocumentMetadata, FileInfo, Identity, Processing, SourceInfo, SourceType, Tagging
from app.core.stores.catalog.base_catalog_store import PullFileEntry


class FileToProcess(BaseModel):
    # Common fields
    source_tag: str
    tags: List[str] = []
    display_name: Optional[str] = None
    processed_by: KeycloakUser

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
    def from_pull_entry(cls, entry: PullFileEntry, source_tag: str, user: KeycloakUser) -> "FileToProcess":
        return cls(
            source_tag=source_tag,
            external_path=entry.path,
            size=entry.size,
            modified_time=entry.modified_time,
            hash=entry.hash or hashlib.sha256(entry.path.encode()).hexdigest(),
            display_name=Path(entry.path).name,
            processed_by=user,
        )

    def to_virtual_metadata(self) -> DocumentMetadata:
        """
        Build a v2 DocumentMetadata stub for a *pull* file.
        This is 'virtual' because the raw file isn't in our content store yet.
        """
        if not self.is_pull():
            raise ValueError("Virtual metadata can only be generated for pull files")

        assert self.external_path, "Pull files must have an external path"
        name = Path(self.external_path).name

        # Use modified time if available; otherwise set to epoch (UTC)
        modified_dt = datetime.fromtimestamp(self.modified_time or 0, tz=timezone.utc)

        # Stable UID for pull sources. Keep your existing convention if other systems depend on it.
        uid = self.document_uid or f"pull-{self.source_tag}-{self.hash or hashlib.sha256(self.external_path.encode()).hexdigest()}"

        # Identity block
        identity = Identity(
            document_name=name,
            document_uid=uid,
            title=self.display_name or None,
            created=None,
            modified=modified_dt,
            last_modified_by=None,
        )

        # Source block
        source = SourceInfo(
            source_type=SourceType.PULL,
            source_tag=self.source_tag,
            pull_location=self.external_path,
            retrievable=False,  # not fetched into our store yet
            date_added_to_kb=modified_dt,  # use fs timestamp as best proxy
        )

        # File block (best-effort; we don't know the MIME here)
        file_info = FileInfo(
            file_size_bytes=self.size,
            mime_type=None,
            page_count=None,
            row_count=None,
            sha256=self.hash,  # if provided by catalog
            md5=None,
            language=None,
        )

        # Tags: assuming incoming `tags` are display names.
        # If they are tag IDs in your system, assign them to `tag_ids=` instead.
        tagging = Tagging(tag_names=list(self.tags))

        # Empty processing status; you can mark phases as you progress.
        processing = Processing()  # stages={}, errors={}

        return DocumentMetadata(
            identity=identity,
            source=source,
            file=file_info,
            tags=tagging,
            processing=processing,
            access=AccessInfo(),  # default AccessInfo() will be created by the model
            preview_url=None,
            viewer_url=None,
            extensions=None,
        )


class PipelineDefinition(BaseModel):
    name: str
    files: List[FileToProcess]


class ProcessDocumentsRequest(BaseModel):
    files: List[FileToProcess]
    pipeline_name: str
