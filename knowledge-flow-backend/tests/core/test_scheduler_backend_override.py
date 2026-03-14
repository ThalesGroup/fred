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

import pytest
from fred_core.scheduler import FRED_STANDALONE_RUNTIME_ENV, SchedulerBackend

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.in_memory_scheduler import (
    InMemoryScheduler,
)
from knowledge_flow_backend.features.scheduler.scheduler_service import (
    IngestionTaskService,
)


def test_knowledge_flow_scheduler_override_forces_memory_backend(
    monkeypatch: pytest.MonkeyPatch,
    app_context: ApplicationContext,
) -> None:
    monkeypatch.setenv(FRED_STANDALONE_RUNTIME_ENV, "true")

    scheduler_cfg = app_context.get_config().scheduler.model_copy(update={"enabled": True, "backend": SchedulerBackend.TEMPORAL})
    service = IngestionTaskService(
        scheduler_config=scheduler_cfg,
        processing_config=app_context.get_config().processing,
        metadata_service=MetadataService(),
    )

    assert isinstance(service._scheduler, InMemoryScheduler)
