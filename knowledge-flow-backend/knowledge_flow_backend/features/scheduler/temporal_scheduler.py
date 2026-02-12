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

import logging
from typing import Optional
from uuid import uuid4

from fastapi import BackgroundTasks
from fred_core import KeycloakUser
from fred_core.scheduler import TemporalClientProvider
from temporalio.client import Client, WorkflowExecutionStatus

from knowledge_flow_backend.common.structures import SchedulerConfig
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    DocumentProgress,
    PipelineDefinition,
)
from knowledge_flow_backend.features.scheduler.store.base_task_store import BaseWorkflowTaskStore
from knowledge_flow_backend.features.scheduler.store.task_structures import WorkflowTaskNotFoundError
from knowledge_flow_backend.features.scheduler.workflow import FastDeleteVectors, FastStoreVectors, Process
from knowledge_flow_backend.features.scheduler.workflow_status import (
    is_non_terminal_status,
    is_terminal_failure_status,
    normalize_workflow_status,
)

logger = logging.getLogger(__name__)


class TemporalScheduler(BaseScheduler):
    """
    Temporal-backed implementation of the ingestion workflow client.

    - Registers a workflow_id and associated document_uids.
    - Starts a Temporal workflow that orchestrates ingestion.
    """

    def __init__(
        self,
        scheduler_config: SchedulerConfig,
        metadata_service: MetadataService,
        temporal_client_provider: Optional[TemporalClientProvider] = None,
        workflow_task_store: Optional[BaseWorkflowTaskStore] = None,
    ) -> None:
        super().__init__(metadata_service)
        self._scheduler_config = scheduler_config
        # Prefer a shared Temporal client provider (mirrors agentic backend pattern)
        self._client_provider = temporal_client_provider or TemporalClientProvider(scheduler_config.temporal)
        self._workflow_task_store = workflow_task_store

    async def start_document_processing(
        self,
        user: KeycloakUser,
        definition: PipelineDefinition,
        background_tasks: Optional[BackgroundTasks] = None,  # kept for interface symmetry, not used
    ) -> WorkflowHandle:
        handle = self._register_workflow(user, definition)

        client: Client = await self._client_provider.get_client()

        workflow_handle = await client.start_workflow(
            Process.run,
            definition,
            id=handle.workflow_id,
            task_queue=self._scheduler_config.temporal.task_queue,
        )

        logger.info("🛠️ started temporal workflow=%s", workflow_handle.id)

        return WorkflowHandle(workflow_id=workflow_handle.id, run_id=workflow_handle.first_execution_run_id)

    async def start_library_processing(
        self,
        user: KeycloakUser,
        library_tag: str,
        processor_path: str,
        document_uids: Optional[list[str]] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        raise NotImplementedError("Library processing is not yet supported with the Temporal scheduler.")

    async def store_fast_vectors(self, payload: dict) -> dict:
        client: Client = await self._client_provider.get_client()
        return await client.execute_workflow(
            FastStoreVectors.run,
            payload,
            id=f"fast-ingest-{uuid4().hex}",
            task_queue=self._scheduler_config.temporal.task_queue,
        )

    async def delete_fast_vectors(self, payload: dict) -> dict:
        client: Client = await self._client_provider.get_client()
        return await client.execute_workflow(
            FastDeleteVectors.run,
            payload,
            id=f"fast-delete-{uuid4().hex}",
            task_queue=self._scheduler_config.temporal.task_queue,
        )

    async def get_workflow_execution_status(self, workflow_id: str) -> Optional[WorkflowExecutionStatus]:
        """
        Return Temporal execution status using the describe API.
        """
        try:
            client: Client = await self._client_provider.get_client()
            handle = client.get_workflow_handle(workflow_id)
            description = await handle.describe()
            return description.status
        except Exception as exc:
            logger.warning("[SCHEDULER] Failed to describe workflow_id=%s: %s", workflow_id, exc)
            return None

    async def get_workflow_last_error(self, workflow_id: str) -> Optional[str]:
        if self._workflow_task_store is None:
            return None
        try:
            task = await self._workflow_task_store.get(workflow_id)
        except WorkflowTaskNotFoundError:
            return None
        return task.last_error

    async def get_progress(self, user: KeycloakUser, workflow_id: Optional[str]):
        base_progress = await super().get_progress(user, workflow_id)

        effective_workflow_id = workflow_id
        if effective_workflow_id is None:
            with self._lock:
                effective_workflow_id = self._last_workflow_by_user.get(user.uid)

        if not effective_workflow_id:
            return base_progress

        description_status = await self.get_workflow_execution_status(effective_workflow_id)
        if description_status is None:
            return base_progress

        status_name = normalize_workflow_status(description_status)
        if is_non_terminal_status(status_name):
            # While parent workflow is still running, do not surface transient
            # per-document failures caused by retried child workflows/activities.
            if base_progress.documents_failed == 0:
                return base_progress
            documents = [doc.model_copy(update={"has_failed": False}) if doc.has_failed else doc for doc in base_progress.documents]
            return base_progress.model_copy(
                update={
                    "documents": documents,
                    "documents_failed": 0,
                }
            )

        if not is_terminal_failure_status(status_name):
            return base_progress
        if self._workflow_task_store is None:
            return base_progress

        try:
            task = await self._workflow_task_store.get(effective_workflow_id)
        except WorkflowTaskNotFoundError:
            return base_progress

        current_uid = task.current_document_uid
        if not current_uid:
            return base_progress

        documents = list(base_progress.documents)
        updated = False
        for idx, doc in enumerate(documents):
            if doc.document_uid != current_uid:
                continue
            if doc.fully_processed:
                return base_progress
            if not doc.has_failed:
                documents[idx] = doc.model_copy(update={"has_failed": True})
                updated = True
            break
        else:
            documents.append(
                DocumentProgress(
                    document_uid=current_uid,
                    stages={},
                    fully_processed=False,
                    has_failed=True,
                )
            )
            updated = True

        if not updated:
            return base_progress

        documents_failed = sum(1 for doc in documents if doc.has_failed)
        documents_found = len(documents)
        documents_missing = max(base_progress.total_documents - documents_found, 0)

        return base_progress.model_copy(
            update={
                "documents": documents,
                "documents_failed": documents_failed,
                "documents_found": documents_found,
                "documents_missing": documents_missing,
            }
        )
