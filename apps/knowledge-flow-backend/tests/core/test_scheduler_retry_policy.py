from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcessWithoutUser


@pytest.mark.asyncio
async def test_submit_documents_embeds_temporal_retry_policy(app_context) -> None:
    """
    Ensure ingestion submissions carry the profile retry policy into file payloads.

    Why:
        The workflow process cannot read live app config directly, so each file
        must carry its profile-derived retry settings at submission time.
    How:
        Stub the scheduler backend, submit one document, and assert the captured
        pipeline file includes the normalized retry policy values.
    """
    service = IngestionTaskService(
        scheduler_config=app_context.configuration.scheduler.model_copy(
            update={"backend": "memory"},
        ),
        processing_config=app_context.configuration.processing,
        metadata_service=MetadataService(),
        max_parallelism=2,
    )

    captured: dict[str, object] = {}

    class _StubScheduler:
        async def start_document_processing(self, *, user, definition, background_tasks=None):
            captured["user"] = user
            captured["definition"] = definition
            return SimpleNamespace(workflow_id="wf-123", run_id="run-123")

    service._scheduler = _StubScheduler()

    user = KeycloakUser(
        uid="test-user",
        username="testuser",
        email="testuser@localhost",
        roles=["admin"],
    )
    files = [
        FileToProcessWithoutUser(
            source_tag="fred",
            display_name="sample.md",
            document_uid="doc-123",
        )
    ]

    definition, handle = await service.submit_documents(
        user=user,
        pipeline_name="retry-policy-test",
        files=files,
    )

    assert handle.workflow_id == "wf-123"
    assert captured["user"] == user
    assert captured["definition"] == definition
    assert len(definition.files) == 1
    file = definition.files[0]
    assert file.retry_initial_interval_seconds == 30
    assert file.retry_backoff_coefficient == 2.0
    assert file.retry_maximum_interval_seconds == 600
    assert file.retry_maximum_attempts == 6
    assert file.retry_non_retryable_error_types == []
