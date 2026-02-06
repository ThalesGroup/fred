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
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from agentic_backend.scheduler.store.base_task_store import (
    BaseAgentTaskStore,
    is_valid_status_transition,
)
from agentic_backend.scheduler.task_structures import (
    AgentContextRefsV1,
    AgentTaskForbiddenError,
    AgentTaskNotFoundError,
    AgentTaskRecordV1,
    AgentTaskStatus,
)


class MemoryAgentTaskStore(BaseAgentTaskStore):
    """
    Simplest possible in-memory task store for local dev and tests.
    Not durable; wiped on process restart.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, AgentTaskRecordV1] = {}

    def create(
        self,
        *,
        task_id: str,
        user_id: str,
        target_agent: str,
        request_text: str,
        workflow_id: str,
        run_id: Optional[str] = None,
        context: Optional[AgentContextRefsV1] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AgentTaskRecordV1:
        with self._lock:
            now = datetime.utcnow()
            existing = self._records.get(task_id)
            if existing:
                # Upsert semantics: update workflow handle and inputs.
                updated = existing.model_copy(
                    update={
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "request_text": request_text,
                        "context": context or existing.context,
                        "parameters": parameters or existing.parameters,
                        "updated_at": now,
                    }
                )
                self._records[task_id] = updated
                return updated

            record = AgentTaskRecordV1(
                task_id=task_id,
                user_id=user_id,
                target_agent=target_agent,
                request_text=request_text,
                context=context or AgentContextRefsV1(),
                parameters=parameters or {},
                workflow_id=workflow_id,
                run_id=run_id,
                created_at=now,
                updated_at=now,
            )
            self._records[task_id] = record
            return record

    def get(self, task_id: str) -> AgentTaskRecordV1:
        with self._lock:
            record = self._records.get(task_id)
            if not record:
                raise AgentTaskNotFoundError(f"Task {task_id} not found")
            return record

    def get_for_user(self, *, task_id: str, user_id: str) -> AgentTaskRecordV1:
        record = self.get(task_id)
        if record.user_id != user_id:
            raise AgentTaskForbiddenError(f"Task {task_id} not owned by user")
        return record

    def list_for_user(
        self,
        *,
        user_id: str,
        limit: int = 20,
        statuses: Optional[Sequence[AgentTaskStatus]] = None,
        target_agent: Optional[str] = None,
    ) -> List[AgentTaskRecordV1]:
        with self._lock:
            items = [
                r
                for r in self._records.values()
                if r.user_id == user_id
                and (not statuses or r.status in statuses)
                and (not target_agent or r.target_agent == target_agent)
            ]
            items.sort(key=lambda r: r.created_at, reverse=True)
            return items[:limit]

    def update_handle(
        self,
        *,
        task_id: str,
        workflow_id: str,
        run_id: Optional[str],
    ) -> None:
        with self._lock:
            record = self.get(task_id)
            self._records[task_id] = record.model_copy(
                update={
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "updated_at": datetime.utcnow(),
                }
            )

    def update_status(
        self,
        *,
        task_id: str,
        status: AgentTaskStatus,
        last_message: Optional[str] = None,
        percent_complete: Optional[float] = None,
        blocked: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[str]] = None,
        error_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            record = self.get(task_id)
            if not is_valid_status_transition(record.status, status):
                raise ValueError(
                    f"Invalid status transition {record.status} -> {status}"
                )
            updates = {
                "status": status,
                "last_message": last_message
                if last_message is not None
                else record.last_message,
                "percent_complete": (
                    percent_complete
                    if percent_complete is not None
                    else record.percent_complete
                ),
                "artifacts": artifacts if artifacts is not None else record.artifacts,
                "blocked_details": blocked
                if blocked is not None
                else record.blocked_details,
                "error_details": error_json
                if error_json is not None
                else record.error_details,
                "updated_at": datetime.utcnow(),
            }
            self._records[task_id] = record.model_copy(update=updates)
