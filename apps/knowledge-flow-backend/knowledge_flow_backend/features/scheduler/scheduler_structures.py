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


from typing import List, Optional

from fred_core import KeycloakUser
from pydantic import BaseModel, Field

from knowledge_flow_backend.common.structures import IngestionProcessingProfile


class FileToProcessWithoutUser(BaseModel):
    source_tag: str
    tags: List[str] = []
    display_name: Optional[str] = None
    profile: IngestionProcessingProfile = IngestionProcessingProfile.medium
    task_id: Optional[str] = None  # OPS-04: set when a task_run row has been created
    document_uid: Optional[str] = None


class FileToProcess(FileToProcessWithoutUser):
    processed_by: KeycloakUser
    input_activity_timeout_seconds: int = 3600
    heartbeat_timeout_seconds: int = 300
    retry_initial_interval_seconds: int = 30
    retry_backoff_coefficient: float = 2.0
    retry_maximum_interval_seconds: int = 600
    retry_maximum_attempts: int = 6
    retry_non_retryable_error_types: List[str] = Field(default_factory=list)

    @classmethod
    def from_file_to_process_without_user(cls, file: FileToProcessWithoutUser, user: KeycloakUser) -> "FileToProcess":
        return cls(
            **file.model_dump(),
            processed_by=user,
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
