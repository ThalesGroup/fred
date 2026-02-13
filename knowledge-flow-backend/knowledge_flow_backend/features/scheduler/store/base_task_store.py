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

from abc import ABC, abstractmethod
from typing import Optional

from knowledge_flow_backend.features.scheduler.store.task_structures import (
    WorkflowTaskRecord,
    WorkflowTaskStatus,
)


class BaseWorkflowTaskStore(ABC):
    """
    Persistence interface for tracking the current document per workflow.
    """

    @abstractmethod
    async def upsert_current_document(
        self,
        *,
        workflow_id: str,
        document_uid: Optional[str],
        filename: Optional[str],
    ) -> WorkflowTaskRecord:
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self,
        *,
        workflow_id: str,
        status: WorkflowTaskStatus,
        last_error: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, workflow_id: str) -> WorkflowTaskRecord:
        raise NotImplementedError
