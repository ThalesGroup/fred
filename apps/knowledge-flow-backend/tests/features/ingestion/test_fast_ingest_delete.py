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

from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


def _build_user(uid: str = "user-1") -> KeycloakUser:
    return KeycloakUser(
        uid=uid,
        username=uid,
        email=f"{uid}@localhost",
        roles=["admin"],
    )


@pytest.mark.asyncio
async def test_delete_fast_ingest_artifacts_deletes_vectors_and_ignores_storage_key() -> None:
    # FILES-04: chat attachments no longer keep a raw copy in workspace storage, so deleting
    # a fast-ingested attachment only removes its retrieval vectors; storage_key is ignored.
    controller = IngestionController.__new__(IngestionController)
    deleted_vectors: list[str] = []
    controller.service = SimpleNamespace()
    controller.scheduler_task_service = None

    async def _delete_fast_vectors(*, document_uid: str) -> str:
        deleted_vectors.append(document_uid)
        return SchedulerBackend.MEMORY.value

    controller._delete_fast_vectors = _delete_fast_vectors  # type: ignore[method-assign]

    backend = await controller._delete_fast_ingest_artifacts(
        user=_build_user(),
        document_uid="doc-1",
        storage_key="uploads/file.txt",  # accepted for backward compat, ignored
        is_platform_bypass=False,
    )

    assert backend == SchedulerBackend.MEMORY.value
    assert deleted_vectors == ["doc-1"]
