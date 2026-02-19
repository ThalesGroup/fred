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
from typing import Dict, List, Optional

from fred_core import KeycloakUser
from pydantic import BaseModel

from knowledge_flow_backend.common.document_structures import (
    AccessInfo,
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.core.stores.catalog.base_catalog_store import PullFileEntry


class FileToProcessWithoutUser(BaseModel):
    # Common fields
    source_tag: str
    tags: List[str] = []
    display_name: Optional[str] = None
    profile: IngestionProcessingProfile = IngestionProcessingProfile.MEDIUM

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


class FileToProcess(FileToProcessWithoutUser):
    processed_by: KeycloakUser

    @classmethod
    def from_file_to_process_without_user(cls, file: FileToProcessWithoutUser, user: KeycloakUser) -> "FileToProcess":
        return cls(
            **file.model_dump(),
            processed_by=user,
        )

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
    max_parallelism: int = 1


class ProcessDocumentsRequest(BaseModel):
    files: List[FileToProcessWithoutUser]
    pipeline_name: str


class ProcessDocumentsResponse(BaseModel):
    status: str
    pipeline_name: str
    total_files: int
    workflow_id: str
    run_id: Optional[str] = None


class DocumentProgress(BaseModel):
    document_uid: str
    stages: Dict[ProcessingStage, ProcessingStatus]
    fully_processed: bool = False
    has_failed: bool = False


class ProcessDocumentsProgressRequest(BaseModel):
    workflow_id: Optional[str] = None


class ProcessDocumentsProgressResponse(BaseModel):
    total_documents: int
    documents_found: int
    documents_missing: int
    documents_with_preview: int
    documents_vectorized: int
    documents_sql_indexed: int
    documents_fully_processed: int
    documents_failed: int
    documents: List[DocumentProgress]


class ProcessLibraryRequest(BaseModel):
    library_tag: str
    processor: str  # fully qualified class path for a LibraryOutputProcessor
    document_uids: Optional[List[str]] = None  # optional subset; defaults to all docs in tag


class ProcessLibraryResponse(BaseModel):
    status: str
    library_tag: str
    workflow_id: str
    run_id: Optional[str] = None
    document_count: Optional[int] = None
