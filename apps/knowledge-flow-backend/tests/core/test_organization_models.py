# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Knowledge Flow reads the organization's models from the Control Plane's facts only."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext

from knowledge_flow_backend.common import organization_models as module

SPACE, ORGANIZATION = UUID(int=1), UUID(int=2)
CONNECTION = {"credential_binding": "mistral", "api_root": "https://api.mistral.ai/v1", "wire": "openai_chat", "route": "standard", "dialect": "mistral", "auth": {"kind": "api_key"}}


def connection_returning(row):
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return SimpleNamespace(execute=AsyncMock(return_value=result))


def row(**changes):
    return {
        "organization_id": ORGANIZATION,
        "source_id": "mistral",
        "upstream_model_id": "mistral-embed",
        "connection": CONNECTION,
        "source_revision": 3,
        "snapshot_revision": 5,
        "policy_revision": 2,
        "available": True,
        **changes,
    }


@pytest.mark.asyncio
async def test_a_published_choice_becomes_the_admission():
    conn = connection_returning(row())
    model = await module.organization_model(conn, SPACE, "embedding")
    assert model.organization_id == ORGANIZATION
    selection = model.admission.selection
    assert (selection.key.upstream_model_id, selection.source_revision, selection.snapshot_revision, selection.policy_revision) == ("mistral-embed", 3, 5, 2)
    assert model.admission.connection.credential_binding == "mistral"
    assert conn.execute.call_args.args[1] == {"space_id": SPACE, "use": "embedding"}


@pytest.mark.asyncio
async def test_no_choice_is_none_and_an_unavailable_choice_is_explicit():
    assert await module.organization_model(connection_returning(None), SPACE, "chat") is None
    with pytest.raises(module.OrganizationModelUnavailable):
        await module.organization_model(connection_returning(row(available=False)), SPACE, "chat")


@pytest.mark.asyncio
async def test_document_tools_require_the_organization_default_model(monkeypatch):
    engine = MagicMock()
    engine.connect.return_value.__aenter__.return_value = connection_returning(None)
    application = SimpleNamespace(get_pg_async_engine=lambda: engine)
    monkeypatch.setattr("knowledge_flow_backend.application_context.ApplicationContext.get_instance", lambda: application)
    context = DocumentAccessContext(space_id=SPACE, authorized_space_ids=(SPACE,), document_scope=DocumentScope())
    with pytest.raises(HTTPException) as failure:
        await module.organization_chat_model(context)
    assert (failure.value.status_code, failure.value.detail) == (409, "organization_default_model_required")
