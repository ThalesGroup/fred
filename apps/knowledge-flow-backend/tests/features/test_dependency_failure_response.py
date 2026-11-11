# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""2026-11-11 scenario: a wrong KF_ARTIFACT_ACCESS_KEY says so, without the store's text."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core.common import register_exception_handlers
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_knowledge.artifacts.reader import ArtifactReader
from fred_knowledge.configuration import ArtifactStorageConfig
from minio.error import S3Error
from urllib3 import HTTPResponse

from knowledge_flow_backend.features.content import published_markdown as markdown_module
from knowledge_flow_backend.security.weaver_admission import delegated_person

SPACE, DOC = UUID(int=1), UUID(int=2)
ACCESS_KEY = "wrong-access-key-value"
STORE_TEXT = "The access key ID you provided does not exist in our records."


class _RefusingStore:
    def get_object(self, *_args: object) -> object:
        raise S3Error(HTTPResponse(status=403), "InvalidAccessKeyId", STORE_TEXT, "/app-content-documents/attempt/output.md", "req", "seaweedfs-host")


def test_a_refused_access_key_answers_502_with_the_setting_only(monkeypatch):
    monkeypatch.setenv("KF_ARTIFACT_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("KF_ARTIFACT_SECRET_KEY", "wrong-secret-value")
    reader = ArtifactReader(
        ArtifactStorageConfig(
            endpoint="http://seaweedfs-host:8333",
            allow_insecure=True,
            bucket="app-content-documents",
            access_key_env="KF_ARTIFACT_ACCESS_KEY",
            secret_key_env="KF_ARTIFACT_SECRET_KEY",  # pragma: allowlist secret
        )
    )
    reader.client = _RefusingStore()  # type: ignore[assignment]

    @asynccontextmanager
    async def connect():
        yield object()

    context = SimpleNamespace(get_pg_async_engine=lambda: SimpleNamespace(connect=connect), get_published_artifact_reader=lambda: reader)
    monkeypatch.setattr(markdown_module.ApplicationContext, "get_instance", lambda: context)
    monkeypatch.setattr(markdown_module, "require_space_read", AsyncMock(return_value=(SPACE,)))
    monkeypatch.setattr(markdown_module, "resolve_scope", AsyncMock(return_value=object()))
    monkeypatch.setattr(markdown_module, "published_artifact", AsyncMock(return_value=SimpleNamespace(prefix="attempt/", size=10, sha256="0" * 64)))

    app, router = FastAPI(), APIRouter()
    register_exception_handlers(app)
    markdown_module.MarkdownController(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: SimpleNamespace(uid="alice")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/documents/{DOC}/markdown", headers={DOCUMENT_CONTEXT_HEADER: DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope()).model_dump_json()})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "A dependency refused this service's configuration.",
        "failure": {"code": "misconfigured", "origin": "object_storage", "setting": "KF_ARTIFACT_ACCESS_KEY"},
    }
    for private in (ACCESS_KEY, STORE_TEXT, "app-content-documents", "seaweedfs-host", "8333", "InvalidAccessKeyId"):
        assert private not in response.text
