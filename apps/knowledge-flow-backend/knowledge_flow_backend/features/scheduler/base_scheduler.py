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

from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.scheduler_structures import PipelineDefinition

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

    async def get_workflow_execution_status(self, workflow_id: str) -> Optional[object]:
        """
        Optional backend-specific workflow execution status.

        Temporal scheduler overrides this to expose WorkflowExecutionStatus from
        Temporal's describe API. Other backends can keep the default (None).
        """
        return None
