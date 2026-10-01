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

"""Upload and relaunch share admission and preserve the owning team's task visibility."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import KeycloakUser
from fred_core.tasks.store import TaskStore
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.ingestion import ingestion_controller
from knowledge_flow_backend.features.scheduler.base_scheduler import WorkflowHandle
from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionDelivery
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess, PipelineDefinition
from knowledge_flow_backend.models.base import Base
from knowledge_flow_backend.models.task_models import TASK_TABLES


@pytest.mark.asyncio
async def test_shared_admission_persists_stored_team(tmp_path):
    from fred_core.documents.document_models import DocumentMetadataRow
    from fred_core.documents.tag_models import TagRow
    from sqlalchemy import insert

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(TagRow.__table__.create)
        await connection.run_sync(DocumentMetadataRow.__table__.create)
        await connection.execute(insert(TagRow).values(tag_id="folder", name="Folder", owner_id="stored-team", type="document"))
    try:
        task_store = TaskStore(engine, TASK_TABLES)
        scheduler = SimpleNamespace(start_document_processing=AsyncMock(side_effect=lambda **kw: WorkflowHandle(workflow_id=kw["definition"].workflow_id)))
        delivery = IngestionDelivery(engine, SimpleNamespace(store=task_store), scheduler)
        service = IngestionTaskService.__new__(IngestionTaskService)
        service.delivery = lambda: delivery
        user = KeycloakUser(uid="bob", username="bob", roles=[])
        definition = PipelineDefinition(name="upload", files=[FileToProcess(source_tag="fred", tags=["folder"], document_uid="doc", processed_by=user)])
        await service._admit(user=user, definition=definition)
        handle = await service.deliver_documents(definition)
        run = await task_store.get_run(definition.files[0].task_id)
        assert run.team_id == "stored-team"
        assert run.folder_id == "folder"
        assert run.execution_id == handle.workflow_id
        assert run.target["id"] == "doc"
        assert run.created_by == "bob"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_admission_propagates_start_failure(monkeypatch):
    service = IngestionTaskService.__new__(IngestionTaskService)
    failure = RuntimeError("Ingestion start not confirmed")
    delivery = SimpleNamespace(admit=AsyncMock(), deliver=AsyncMock(side_effect=failure))
    service.delivery = lambda: delivery
    monkeypatch.setattr(ingestion_controller, "resolve_tag_owners", AsyncMock(return_value=({"team"}, set())))
    user = KeycloakUser(uid="bob", username="bob", roles=[])
    definition = PipelineDefinition(name="upload", files=[FileToProcess(source_tag="fred", tags=["folder"], document_uid="doc", processed_by=user)])
    with pytest.raises(RuntimeError, match="start not confirmed"):
        await service._admit(user=user, definition=definition)
        await service.deliver_documents(definition)
    delivery.deliver.assert_awaited_once_with(definition, None)


@pytest.mark.asyncio
async def test_initial_temporal_connection_failure_does_not_admit_tasks(app_context):
    from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcessWithoutUser

    provider = SimpleNamespace(get_client=AsyncMock(side_effect=ConnectionError("Temporal unavailable")))
    service = IngestionTaskService(
        scheduler_config=app_context.configuration.scheduler.model_copy(update={"backend": "temporal"}),
        processing_config=app_context.configuration.processing,
        metadata_service=None,
        temporal_client_provider=provider,
    )
    service._admit = AsyncMock()
    with pytest.raises(ConnectionError, match="Temporal unavailable"):
        await service.submit_documents(
            user=KeycloakUser(uid="bob", username="bob", roles=[]),
            pipeline_name="upload",
            files=[FileToProcessWithoutUser(source_tag="uploads", document_uid="doc", profile="rich")],
        )
    service._admit.assert_not_awaited()
    provider.get_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_only_admission_does_not_connect_to_temporal(app_context):
    from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcessWithoutUser

    provider = SimpleNamespace(get_client=AsyncMock(side_effect=ConnectionError("Temporal unavailable")))
    service = IngestionTaskService(
        scheduler_config=app_context.configuration.scheduler.model_copy(update={"backend": "temporal"}),
        processing_config=app_context.configuration.processing,
        metadata_service=None,
        temporal_client_provider=provider,
    )
    service._admit = AsyncMock()
    definition = await service.admit_documents(
        user=KeycloakUser(uid="bob", username="bob", roles=[]),
        pipeline_name="upload",
        files=[FileToProcessWithoutUser(source_tag="uploads", document_uid="doc", profile="rich")],
        upload_only=True,
    )
    provider.get_client.assert_not_called()
    service._admit.assert_awaited_once()
    assert definition.workflow_id is None
