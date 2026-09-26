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
@pytest.mark.parametrize("teams,expected", [({"team-fredlab"}, "team-fredlab"), ({"a", "b"}, None), (set(), None)])
async def test_shared_admission_persists_resolved_team(monkeypatch, tmp_path, teams, expected):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        task_store = TaskStore(engine, TASK_TABLES)
        scheduler = SimpleNamespace(start_document_processing=AsyncMock(side_effect=lambda **kw: WorkflowHandle(workflow_id=kw["definition"].workflow_id)))
        delivery = IngestionDelivery(engine, SimpleNamespace(store=task_store), scheduler)
        service = IngestionTaskService.__new__(IngestionTaskService)
        service.delivery = lambda: delivery
        resolve = AsyncMock(return_value=(teams, set()))
        monkeypatch.setattr(ingestion_controller, "resolve_tag_owners", resolve)
        user = KeycloakUser(uid="bob", username="bob", roles=[])
        definition = PipelineDefinition(name="upload", files=[FileToProcess(source_tag="fred", tags=["folder"], document_uid="doc", processed_by=user)])
        handle = await service._admit_and_deliver(user=user, definition=definition)
        run = await task_store.get_run(definition.files[0].task_id)
        assert run.team_id == expected
        assert run.execution_id == handle.workflow_id
        assert run.target["id"] == "doc"
        assert run.created_by == "bob"
        resolve.assert_awaited_once_with(["folder"], user)
    finally:
        await engine.dispose()
