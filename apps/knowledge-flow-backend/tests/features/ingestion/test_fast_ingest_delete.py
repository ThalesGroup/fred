from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


class _FakeWorkspaceStorageService:
    def __init__(self) -> None:
        self.deleted_keys: list[tuple[str, str]] = []

    async def delete_user_file(self, user: KeycloakUser, key: str) -> None:
        self.deleted_keys.append((user.uid, key))


def _build_user(uid: str = "user-1") -> KeycloakUser:
    return KeycloakUser(
        uid=uid,
        username=uid,
        email=f"{uid}@localhost",
        roles=["admin"],
        groups=["admins"],
    )


@pytest.mark.asyncio
async def test_delete_fast_ingest_artifacts_deletes_vectors_and_storage() -> None:
    controller = IngestionController.__new__(IngestionController)
    workspace_storage_service = _FakeWorkspaceStorageService()
    deleted_vectors: list[str] = []
    controller.service = SimpleNamespace()
    controller.workspace_storage_service = workspace_storage_service
    controller.scheduler_task_service = None

    async def _delete_fast_vectors(*, document_uid: str) -> str:
        deleted_vectors.append(document_uid)
        return SchedulerBackend.MEMORY.value

    controller._delete_fast_vectors = _delete_fast_vectors  # type: ignore[method-assign]

    backend = await controller._delete_fast_ingest_artifacts(
        user=_build_user(),
        document_uid="doc-1",
        storage_key="uploads/file.txt",
    )

    assert backend == SchedulerBackend.MEMORY.value
    assert deleted_vectors == ["doc-1"]
    assert workspace_storage_service.deleted_keys == [("user-1", "uploads/file.txt")]


@pytest.mark.asyncio
async def test_delete_fast_ingest_artifacts_skips_storage_cleanup_when_key_missing() -> None:
    controller = IngestionController.__new__(IngestionController)
    workspace_storage_service = _FakeWorkspaceStorageService()
    deleted_vectors: list[str] = []
    controller.service = SimpleNamespace()
    controller.workspace_storage_service = workspace_storage_service
    controller.scheduler_task_service = None

    async def _delete_fast_vectors(*, document_uid: str) -> str:
        deleted_vectors.append(document_uid)
        return SchedulerBackend.MEMORY.value

    controller._delete_fast_vectors = _delete_fast_vectors  # type: ignore[method-assign]

    backend = await controller._delete_fast_ingest_artifacts(
        user=_build_user(),
        document_uid="doc-2",
        storage_key=None,
    )

    assert backend == SchedulerBackend.MEMORY.value
    assert deleted_vectors == ["doc-2"]
    assert workspace_storage_service.deleted_keys == []
