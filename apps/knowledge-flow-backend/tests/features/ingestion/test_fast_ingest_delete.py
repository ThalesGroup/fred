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
    )

    assert backend == SchedulerBackend.MEMORY.value
    assert deleted_vectors == ["doc-1"]
