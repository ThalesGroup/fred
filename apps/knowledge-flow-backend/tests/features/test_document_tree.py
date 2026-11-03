# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Tree contract and real SQL selection tests.

SQL cases require KF_TREE_TEST_POSTGRES, an async SQLAlchemy PostgreSQL URL to an
empty disposable database. All fixture DDL/data is rolled back; an existing
cp_read schema is refused, never replaced. No index or model service is needed.
"""

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_core.security.delegation import AssertedUser
from fred_core.security.mcp_delegation import declare_delegation_parameters
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.document_scope import declare_document_context_openapi
from knowledge_flow_backend.features.document_tree import controller, service
from knowledge_flow_backend.features.document_tree.structures import DocumentTreeResponse
from knowledge_flow_backend.security.weaver_admission import delegated_person

ANCESTOR, SPACE, OUTSIDE, FOLDER, CHILD, OTHER = [UUID(int=i) for i in range(1, 7)]
DOC, NESTED, ROOT, INHERITED, HIDDEN, ATTACHED, FOREIGN = [UUID(int=i) for i in range(10, 17)]
PERSON = AssertedUser(uid="alice", client_id="pod", run_id="turn", agent_id="agent")


@pytest.fixture
def api(monkeypatch):
    admission = AsyncMock(return_value=(ANCESTOR, SPACE))
    listing = AsyncMock(return_value=DocumentTreeResponse())
    monkeypatch.setattr(controller, "require_space_read", admission)
    monkeypatch.setattr(controller.DocumentTreeService, "tree", listing)
    app, router = FastAPI(), APIRouter(prefix="/custom/kf", dependencies=[Depends(declare_delegation_parameters)])
    controller.DocumentTreeController(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: PERSON
    declare_document_context_openapi(app)
    return app, admission, listing


def test_tree_admission_and_contract(api):
    app, admission, listing = api
    context = DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope.from_ids([str(FOLDER)]))
    with TestClient(app) as client:
        response = client.get("/custom/kf/documents/tree", params={"folder_id": str(FOLDER), "limit": 7}, headers={DOCUMENT_CONTEXT_HEADER: context.model_dump_json()})
    assert response.json() == {"spaces": [], "folders": [], "documents": [], "truncated": False}
    admission.assert_awaited_once_with(PERSON, SPACE)
    listing.assert_awaited_once_with(context=context, user_id="alice", authorized_space_ids=(ANCESTOR, SPACE), folder_id=FOLDER, limit=7)
    schema = app.openapi()
    operation = schema["paths"]["/custom/kf/documents/tree"]["get"]
    assert operation["operationId"] == "list_document_tree"
    assert "requestBody" not in operation
    assert set(operation["responses"]) == {"200", "400", "401", "403", "404", "409", "422", "500", "503"}
    params = {p["name"]: p for p in operation["parameters"]}
    assert set(params) == {"folder_id", "limit", "person", "run", "agent", DOCUMENT_CONTEXT_HEADER}
    assert params["limit"]["schema"]["default"] == 1000
    assert params["limit"]["schema"]["minimum"] == 1
    assert params["limit"]["schema"]["maximum"] == 5000
    assert "folder_not_found" in operation["responses"]["404"]["description"]
    assert "X-Fred-Denial-Cause" in operation["responses"]["403"]["headers"]
    for model in ("DocumentTreeResponse", "DocumentTreeSpace", "DocumentTreeFolder", "DocumentTreeDocument"):
        assert schema["components"]["schemas"][model]["additionalProperties"] is False


@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 5001}, {"folder_id": "not-a-uuid"}])
def test_invalid_navigation_is_422(api, query):
    app, _, listing = api
    with TestClient(app) as client:
        response = client.get("/custom/kf/documents/tree", params=query, headers={DOCUMENT_CONTEXT_HEADER: DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope()).model_dump_json()})
    assert response.status_code == 422
    listing.assert_not_awaited()


def test_folder_refusal_retains_the_shared_error_envelope(api):
    app, _, listing = api
    listing.side_effect = HTTPException(404, "folder_not_found")
    with TestClient(app) as client:
        response = client.get(
            "/custom/kf/documents/tree", params={"folder_id": str(FOLDER)}, headers={DOCUMENT_CONTEXT_HEADER: DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope()).model_dump_json()}
        )
    assert response.status_code == 404
    assert response.json() == {"detail": "folder_not_found"}


@pytest_asyncio.fixture
async def corpus(monkeypatch):
    url = os.getenv("KF_TREE_TEST_POSTGRES")
    if not url:
        pytest.skip("set KF_TREE_TEST_POSTGRES to an empty disposable PostgreSQL database")
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text("CREATE SCHEMA cp_read"))
            for ddl in (
                "CREATE TABLE cp_read.space_state(id uuid PRIMARY KEY, name text, retired boolean)",
                "CREATE TABLE cp_read.folder_path(id uuid PRIMARY KEY, space_id uuid, path text, name text)",
                "CREATE TABLE cp_read.document_visibility(document_id uuid PRIMARY KEY, space_id uuid, folder_id uuid, conversation_id uuid, name text, mime text, created_at timestamptz, visible boolean)",
            ):
                await conn.execute(text(ddl))
            for id, name in ((ANCESTOR, "Organization"), (SPACE, "Project"), (OUTSIDE, "Foreign")):
                await conn.execute(text("INSERT INTO cp_read.space_state VALUES (:id, :name, false)"), {"id": id, "name": name})
            for id, space, path in ((FOLDER, SPACE, f"/{FOLDER}/"), (CHILD, SPACE, f"/{FOLDER}/{CHILD}/"), (OTHER, OUTSIDE, f"/{OTHER}/")):
                await conn.execute(text("INSERT INTO cp_read.folder_path VALUES (:id, :space, :path, :name)"), {"id": id, "space": space, "path": path, "name": f"Folder {id.int}"})
            # Deliberately shuffled insertion order; all other SQL facts are identical.
            for id, space, folder, visible, attachment in (
                (NESTED, SPACE, CHILD, True, False),
                (FOREIGN, OUTSIDE, OTHER, True, False),
                (HIDDEN, SPACE, FOLDER, False, False),
                (ROOT, SPACE, None, True, False),
                (ATTACHED, SPACE, None, True, True),
                (INHERITED, ANCESTOR, None, True, False),
                (DOC, SPACE, FOLDER, True, False),
            ):
                await conn.execute(
                    text("INSERT INTO cp_read.document_visibility VALUES (:id, :space, :folder, :conversation, :name, 'text/plain', '2026-11-03T00:00:00Z', :visible)"),
                    {"id": id, "space": space, "folder": folder, "conversation": UUID(int=100) if attachment else None, "name": f"Doc {id.int}", "visible": visible},
                )

            @asynccontextmanager
            async def connection():
                yield conn

            monkeypatch.setattr(service.ApplicationContext, "get_instance", lambda: SimpleNamespace(get_pg_async_engine=lambda: SimpleNamespace(connect=connection)))
            yield service.DocumentTreeService()
        finally:
            await transaction.rollback()
    await engine.dispose()


async def tree(corpus, scope=DocumentScope(), folder=None, limit=1000, spaces=(ANCESTOR, SPACE)):
    return await corpus.tree(
        context=DocumentAccessContext(space_id=SPACE, document_scope=scope, conversation_id=UUID(int=100), attachment_ids=(ATTACHED,)),
        user_id="alice",
        authorized_space_ids=spaces,
        folder_id=folder,
        limit=limit,
    )


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope,expected",
    [
        (DocumentScope(), {DOC, NESTED, ROOT, INHERITED}),
        (DocumentScope.from_ids([], []), set()),
        (DocumentScope.from_ids([str(FOLDER)]), {DOC}),
        (DocumentScope.from_ids([str(FOLDER)], [str(ROOT)]), {DOC, ROOT}),
        (DocumentScope.from_ids([str(FOLDER)]).intersect(DocumentScope.from_ids(document_ids=[str(DOC), str(NESTED)])), {DOC}),
        (DocumentScope.from_ids([str(FOLDER)]).intersect(DocumentScope.from_ids([str(CHILD)])), set()),
        (DocumentScope.from_ids([str(OTHER)]), set()),
        (DocumentScope.from_ids(document_ids=[str(ATTACHED), str(HIDDEN)]), set()),
    ],
)
async def test_scope_semantics_and_visibility(corpus, scope, expected):
    result = await tree(corpus, scope)
    assert {doc.document_uid for doc in result.documents} == expected
    assert not result.truncated
    assert all(space.space_id in (ANCESTOR, SPACE) for space in result.spaces)
    if not expected:
        assert result.folders == ()


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_ancestor_root_documents_order_and_limit(corpus):
    result = await tree(corpus)
    assert [space.space_id for space in result.spaces] == [ANCESTOR, SPACE]
    assert [doc.document_uid for doc in result.documents] == [INHERITED, ROOT, DOC, NESTED]
    assert [folder.folder_id for folder in result.folders] == [FOLDER, CHILD]
    assert result == await tree(corpus)
    total = len(result.folders) + len(result.documents)
    assert not (await tree(corpus, limit=total)).truncated
    for limit in (1, 3, total - 1):
        limited = await tree(corpus, limit=limit)
        assert limited.truncated
        assert len(limited.folders) + len(limited.documents) == limit
    assert await tree(corpus, spaces=()) == DocumentTreeResponse()


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_subtree_never_expands_selection_and_folders_are_not_an_oracle(corpus):
    assert {d.document_uid for d in (await tree(corpus, folder=FOLDER)).documents} == {DOC, NESTED}
    scoped = await tree(corpus, DocumentScope.from_ids(document_ids=[str(NESTED)]), folder=FOLDER)
    assert [d.document_uid for d in scoped.documents] == [NESTED]
    for folder, selection in ((OTHER, DocumentScope()), (UUID(int=999), DocumentScope()), (CHILD, DocumentScope.from_ids([str(FOLDER)])), (FOLDER, DocumentScope.from_ids([], []))):
        with pytest.raises(HTTPException) as error:
            await tree(corpus, selection, folder=folder)
        assert error.value.status_code == 404
        assert error.value.detail == "folder_not_found"
