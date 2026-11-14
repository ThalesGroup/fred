# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Admitted corpus survives authority changes; publication stays live."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fred_core.documents.access import SearchScope
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.features.content import published_markdown as markdown
from knowledge_flow_backend.features.document_scope import document_access_context

PERSON = AssertedUser(uid="person", client_id="pod", run_id="run", agent_id="agent")


@pytest.mark.asyncio
async def test_admitted_corpus_is_reused_without_permission_refresh_but_publication_is_live(monkeypatch):
    anchor, ancestor, document = uuid4(), uuid4(), uuid4()
    admitted = (ancestor, anchor)
    access = DocumentAccessContext(space_id=anchor, authorized_space_ids=admitted, document_scope=DocumentScope())
    engine = MagicMock()
    scope = SearchScope(space_id=anchor, space_ids=admitted)
    resolver = AsyncMock(return_value=scope)
    artifact = SimpleNamespace(prefix="published/", size=4, sha256="0" * 64)
    publication = AsyncMock(side_effect=[artifact, artifact, None])
    authorization = MagicMock(side_effect=AssertionError("No per-read authority refresh"))
    app = SimpleNamespace(get_pg_async_engine=lambda: engine, get_authorization_client=authorization, get_published_artifact_reader=lambda: SimpleNamespace(read_bytes=lambda *_: b"text"))
    monkeypatch.setattr(markdown.ApplicationContext, "get_instance", lambda: app)
    monkeypatch.setattr(markdown, "resolve_scope", resolver)
    monkeypatch.setattr(markdown, "published_artifact", publication)
    assert await markdown.published_markdown(PERSON, str(document), access) == "text"
    # A subsequent denial from Control Plane must not be consulted within this turn.
    authorization.side_effect = HTTPException(403, "revoked")
    assert await markdown.published_markdown(PERSON, str(document), access) == "text"
    with pytest.raises(HTTPException) as error:
        await markdown.published_markdown(PERSON, str(document), access)
    assert error.value.status_code == 404
    authorization.assert_not_called()
    assert publication.await_count == 3
    assert all(call.args[1].authorized_space_ids == admitted for call in resolver.await_args_list)


@pytest.mark.parametrize("kind", ["missing_corpus", "invalid_id", "duplicates", "null_corpus"])
def test_malformed_admitted_scope_never_becomes_empty_or_unrestricted(kind):
    anchor = str(uuid4())
    body = {"space_id": anchor, "authorized_space_ids": [], "document_scope": {}}
    if kind == "missing_corpus":
        del body["authorized_space_ids"]
    elif kind == "invalid_id":
        body["authorized_space_ids"] = ["invalid"]
    elif kind == "duplicates":
        body["authorized_space_ids"] = [anchor, anchor]
    else:
        body["authorized_space_ids"] = None
    import json

    with pytest.raises(HTTPException) as error:
        document_access_context(PERSON, json.dumps(body))
    assert error.value.status_code == 400


@pytest.mark.parametrize("missing", ["credentials", "delegation", "control_plane_url"])
def test_authorization_startup_requires_own_delegation_credentials(missing):
    from knowledge_flow_backend.application_context import ApplicationContext

    context = SimpleNamespace(
        configuration=SimpleNamespace(
            control_plane_url=None if missing == "control_plane_url" else "https://authority.test",
            security=SimpleNamespace(
                m2m=SimpleNamespace(enabled=missing != "credentials"),
                delegation=SimpleNamespace(act_for_people=missing != "delegation"),
            ),
        )
    )
    with pytest.raises(ValueError, match="requires Control Plane"):
        ApplicationContext.open_authorization_client(context)
