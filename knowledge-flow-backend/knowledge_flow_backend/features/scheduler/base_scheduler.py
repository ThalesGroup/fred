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
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import BackgroundTasks
from fred_core import KeycloakUser

from knowledge_flow_backend.common.document_structures import ProcessingStage, ProcessingStatus
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    DocumentProgress,
    PipelineDefinition,
    ProcessDocumentsProgressResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkflowHandle:
    workflow_id: str
    run_id: Optional[str] = None


class BaseScheduler(ABC):
    """
    Common logic for ingestion workflow clients, regardless of backend.

    Responsibilities:
    - Map workflow ids to document_uids derived from the pipeline definition.
    - Track the "last workflow" per user to support stateless UI polling.
    - Compute progress by reading metadata for the tracked document_uids.
    """

    def __init__(self, metadata_service: MetadataService) -> None:
        self._metadata_service = metadata_service
        self._lock = threading.Lock()
        self._workflows_by_id: Dict[str, List[str]] = {}
        self._last_workflow_by_user: Dict[str, str] = {}

    @abstractmethod
    async def start_document_processing(
        self,
        user: KeycloakUser,
        definition: PipelineDefinition,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        """
        Start an ingestion workflow for the given user and pipeline definition.

        Returns a WorkflowHandle containing the workflow_id (and optionally run_id).
        """
        pass

    @abstractmethod
    async def start_library_processing(
        self,
        user: KeycloakUser,
        library_tag: str,
        processor_path: str,
        document_uids: Optional[List[str]] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        """
        Start a library-level processing workflow.

        Args:
            user: Caller identity.
            library_tag: Tag identifying the library to process.
            processor_path: Fully qualified class path for a LibraryOutputProcessor.
            document_uids: Optional subset of documents within the library tag.
        """
        pass

    @abstractmethod
    async def store_fast_vectors(self, payload: dict) -> dict:
        """
        Store fast-ingest vectors (backend-specific implementation).
        """
        pass

    @abstractmethod
    async def delete_fast_vectors(self, payload: dict) -> dict:
        """
        Delete fast-ingest vectors (backend-specific implementation).
        """
        pass

    def _extract_document_uids(self, definition: PipelineDefinition) -> List[str]:
        document_uids: List[str] = []
        for file in definition.files:
            if file.is_pull():
                virtual_metadata = file.to_virtual_metadata()
                document_uids.append(virtual_metadata.identity.document_uid)
            elif file.document_uid:
                document_uids.append(file.document_uid)
            else:
                logger.warning("[SCHEDULER] Push file without document_uid, skipping from tracking")
        return document_uids

    def _register_workflow(self, user: KeycloakUser, definition: PipelineDefinition) -> WorkflowHandle:
        document_uids = self._extract_document_uids(definition)
        return self._register_workflow_for_uids(user, document_uids)

    def _register_workflow_for_uids(self, user: KeycloakUser, document_uids: List[str]) -> WorkflowHandle:
        workflow_id = f"wf-{uuid4()}"

        with self._lock:
            self._workflows_by_id[workflow_id] = document_uids
            self._last_workflow_by_user[user.uid] = workflow_id

        logger.info(
            "[SCHEDULER] Registered workflow_id=%s user=%s document_number=%d ",
            workflow_id,
            user.username,
            len(document_uids),
        )

        return WorkflowHandle(workflow_id=workflow_id)

    async def get_progress(self, user: KeycloakUser, workflow_id: Optional[str]) -> ProcessDocumentsProgressResponse:
        """
        Compute aggregate processing progress for a workflow.

        If workflow_id is None, the last workflow started for this user is used.
        """
        with self._lock:
            if workflow_id:
                document_uids = self._workflows_by_id.get(workflow_id, [])
            else:
                last = self._last_workflow_by_user.get(user.uid)
                document_uids = self._workflows_by_id.get(last, []) if last else []

        total_requested = len(document_uids)

        documents: List[DocumentProgress] = []
        documents_with_preview = 0
        documents_vectorized = 0
        documents_sql_indexed = 0
        documents_fully_processed = 0
        documents_failed = 0

        for uid in document_uids:
            try:
                metadata = await self._metadata_service.get_document_metadata(user, uid)
            except Exception:
                logger.warning("[SCHEDULER] Document metadata not found for uid=%s", uid)
                continue

            stages = metadata.processing.stages or {}
            has_failed = any(status == ProcessingStatus.FAILED for status in stages.values())
            preview_done = stages.get(ProcessingStage.PREVIEW_READY) == ProcessingStatus.DONE
            vectorized_done = stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE
            sql_indexed_done = stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE
            # Consider PREVIEW_READY as terminal success for pipelines that do not
            # produce vector/sql stages (or where those stages are optional).
            fully_processed = preview_done or vectorized_done or sql_indexed_done

            if preview_done:
                documents_with_preview += 1
            if vectorized_done:
                documents_vectorized += 1
            if sql_indexed_done:
                documents_sql_indexed += 1
            if fully_processed:
                documents_fully_processed += 1
            if has_failed:
                documents_failed += 1

            documents.append(
                DocumentProgress(
                    document_uid=metadata.document_uid,
                    stages=stages,
                    fully_processed=fully_processed,
                    has_failed=has_failed,
                )
            )

        documents_found = len(documents)
        documents_missing = total_requested - documents_found

        return ProcessDocumentsProgressResponse(
            total_documents=total_requested,
            documents_found=documents_found,
            documents_missing=documents_missing,
            documents_with_preview=documents_with_preview,
            documents_vectorized=documents_vectorized,
            documents_sql_indexed=documents_sql_indexed,
            documents_fully_processed=documents_fully_processed,
            documents_failed=documents_failed,
            documents=documents,
        )
