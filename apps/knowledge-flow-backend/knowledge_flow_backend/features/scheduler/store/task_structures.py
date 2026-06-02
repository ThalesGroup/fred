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

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class WorkflowTaskStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkflowTaskRecord(BaseModel):
    workflow_id: str
    current_document_uid: Optional[str] = None
    current_filename: Optional[str] = None
    status: WorkflowTaskStatus = WorkflowTaskStatus.RUNNING
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkflowTaskError(Exception): ...


class WorkflowTaskNotFoundError(WorkflowTaskError): ...
