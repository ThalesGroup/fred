from __future__ import annotations

from typing import cast

import pytest

from agentic_backend.common.kf_workspace_client import UserStorageUploadResult
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    ArtifactPublishRequest,
    ArtifactScope,
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.integrations.v2_runtime import adapters as v2_adapters
from agentic_backend.integrations.v2_runtime.adapters import FredArtifactPublisher


class FakeWorkspaceClient:
    async def upload_user_blob(
        self,
        *,
        key: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> UserStorageUploadResult:
        del file_content, content_type
        return UserStorageUploadResult(
            key=key,
            file_name=filename,
            size=12,
            document_uid=cast("str | None", 0),
            download_url="https://example.test/download/demo.md",
        )


def _binding(session_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="user-1",
            access_token="token",
        ),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:test",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id="demo.agent",
        ),
    )


@pytest.mark.asyncio
async def test_fred_artifact_publisher_normalizes_invalid_numeric_document_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        v2_adapters,
        "KfWorkspaceClient",
        lambda agent: FakeWorkspaceClient(),
    )
    publisher = FredArtifactPublisher(
        binding=_binding("artifact-session"),
        settings=AgentSettings(id="demo.agent", name="Demo Agent"),
    )

    artifact = await publisher.publish(
        ArtifactPublishRequest(
            file_name="demo.md",
            content_bytes=b"# demo",
            scope=ArtifactScope.USER,
            content_type="text/markdown; charset=utf-8",
        )
    )

    assert artifact.file_name == "demo.md"
    assert artifact.document_uid is None
    assert artifact.href == "https://example.test/download/demo.md"
