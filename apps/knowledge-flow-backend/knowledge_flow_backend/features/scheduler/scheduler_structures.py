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


class FileToProcess(BaseModel):
    # Common fields
    source_tag: str
    tags: List[str] = []
    display_name: Optional[str] = None
    profile: IngestionProcessingProfile = IngestionProcessingProfile.medium

    # Push-specific
    document_uid: Optional[str] = None  # Present for push files

    processed_by: KeycloakUser
    logging_context: Optional[str] = None  # bounded diagnostic envelope, never authority
    # Set at submission from the file's profile, and read back by the workflow to
    # route this document's extraction activity.
    extraction_task_queue: Optional[str] = None
    push_metadata_activity_timeout_seconds: int = 300
    output_activity_timeout_seconds: int = 3600
    input_activity_timeout_seconds: int = 3600
    heartbeat_timeout_seconds: int = 300
    retry_initial_interval_seconds: int = 30
    retry_backoff_coefficient: float = 2.0
    retry_maximum_interval_seconds: int = 600
    retry_maximum_attempts: int = 6
    retry_non_retryable_error_types: List[str] = Field(default_factory=list)


class PipelineDefinition(BaseModel):
    workflow_id: Optional[str] = None
    name: str
    files: List[FileToProcess]
    max_parallelism: int = 1
    logging_context: Optional[str] = None
