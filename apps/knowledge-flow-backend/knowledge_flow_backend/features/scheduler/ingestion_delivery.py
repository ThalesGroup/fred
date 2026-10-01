# Copyright Thales 2026
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

"""Document task admission and direct scheduler submission."""

from typing import cast
from uuid import uuid4

from fastapi import BackgroundTasks
from fred_core import KeycloakUser
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.sql import make_session_factory
from fred_core.tasks.models import TaskTarget
from fred_core.tasks.service import TaskService
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_structures import PipelineDefinition
from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy, CorpusLifecycle
from knowledge_flow_backend.models.task_models import ACTIVE_DOCUMENT_INDEX, KfTaskRunRow


class IngestionAlreadyActive(ValueError):
    pass


class IngestionDelivery:
    def __init__(self, engine: AsyncEngine, task_service: TaskService, scheduler: BaseScheduler) -> None:
        self.sessions = make_session_factory(engine)
        self.tasks = task_service
        self.scheduler = scheduler

    async def admit(self, user: KeycloakUser, definition: PipelineDefinition, *, upload_only: bool = False) -> str | None:
        if not definition.files:
            raise ValueError("At least one document is required")
        definition.workflow_id = None if upload_only else f"ingestion-{uuid4()}"
        try:
            async with self.sessions.begin() as session:
                if any(len(file.tags) != 1 for file in definition.files):
                    raise ValueError("Ingestion requires exactly one destination folder")
                document_ids = {file.to_virtual_metadata().document_uid if file.is_pull() else file.document_uid for file in definition.files}
                membership_query = select(DocumentMetadataRow.document_uid, DocumentMetadataRow.folder_id).where(DocumentMetadataRow.document_uid.in_(document_ids))
                old_membership = dict((await session.execute(membership_query)).tuples().all())
                old_folders = {folder for folder in old_membership.values() if folder is not None}
                folders = await CorpusLifecycle.lock_folders(session, old_folders | {file.tags[0] for file in definition.files})
                owners = {folder.tag_id: folder.owner_id for folder in folders}
                if any(not owner for owner in owners.values()):
                    raise ValueError("Every corpus folder must have a persisted team owner")
                if dict((await session.execute(membership_query)).tuples().all()) != old_membership:
                    raise CorpusBusy("Document membership changed during admission. Refresh before retrying.")
                for file in definition.files:
                    uid = file.to_virtual_metadata().document_uid if file.is_pull() else file.document_uid
                    if not uid:
                        raise ValueError("A document UID is required for ingestion")
                    if file.task_id:
                        raise ValueError("Ingestion admission creates its own tasks")
                    file.task_id = self.tasks.store.new_task_id()
                    run = await self.tasks.store.create(
                        task_id=file.task_id,
                        kind="ingestion",
                        created_by=user.uid,
                        team_id=owners[file.tags[0]],
                        target=TaskTarget(type="document", id=uid, label=file.display_name or uid),
                        execution_id=definition.workflow_id,
                        session=session,
                    )
                    cast(KfTaskRunRow, run).folder_id = file.tags[0]
        except IntegrityError as exc:
            if ACTIVE_DOCUMENT_INDEX in str(exc.orig):
                raise IngestionAlreadyActive("An ingestion is already active for one of these documents. Refresh its task status before retrying.") from exc
            raise
        return definition.workflow_id

    async def deliver(self, definition: PipelineDefinition, background_tasks: BackgroundTasks | None = None) -> WorkflowHandle:
        try:
            return await self.scheduler.start_document_processing(
                user=definition.files[0].processed_by,
                definition=definition,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            raise RuntimeError(f"Ingestion start not confirmed ({definition.workflow_id}). No automatic resubmission. Check task status before retrying.") from exc
