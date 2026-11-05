# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Real pod/capability composition, with only identity and database IO replaced."""

from dataclasses import replace
from unittest.mock import AsyncMock, create_autospec

import pytest
from fastapi.testclient import TestClient
from fred_capability_writable_document import store as store_module
from fred_capability_writable_document.capability import WritableDocumentCapability
from fred_capability_writable_document.store import (
    WritableDocumentRecord,
    WritableDocumentStore,
)
from fred_core.common import get_config
from fred_core.security import oidc
from fred_runtime.app import agent_app
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.common.outbound_credentials import (
    get_delegation_runtime,
    set_delegation_runtime,
)
from fred_runtime.runtime_context import (
    RuntimeConfig,
    RuntimeContext,
    get_runtime_context_or_none,
    set_runtime_context,
)
from test_app_security import DELEGATED, PERSON, SERVICE, terms_app

BASE = "/pod/capabilities/writable_document/sessions/session-a/documents"
REQUESTS = [
    ("GET", BASE),
    ("GET", f"{BASE}/doc-a"),
    ("PUT", f"{BASE}/doc-a"),
    ("GET", f"{BASE}/doc-a/export?format=md"),
]


@pytest.fixture
def pod(monkeypatch):
    previous = get_delegation_runtime()
    previous_context = get_runtime_context_or_none()
    registry = CapabilityRegistry()
    registry.register(WritableDocumentCapability())
    monkeypatch.setattr(
        agent_app, "boot_capability_registry", lambda **kwargs: registry
    )
    config = AgentPodConfig.model_validate(
        {
            "app": {"runtime_id": "test-pod", "base_url": "/pod"},
            "security": {
                "user": {
                    "enabled": True,
                    "realm_url": "https://iam.invalid/r",
                    "client_id": "browser",
                },
                "m2m": {
                    "enabled": False,
                    "realm_url": "https://iam.invalid/r",
                    "client_id": "pod",
                },
            },
        }
    )
    store = create_autospec(WritableDocumentStore, instance=True)
    store.get.return_value = WritableDocumentRecord(
        "session-a", "doc-a", PERSON.uid, "Report", "body"
    )
    store.list_for_session.return_value = [store.get.return_value]
    store.upsert.side_effect = lambda record: record
    monkeypatch.setattr(store_module, "_provider", lambda: store)
    try:
        set_runtime_context(
            RuntimeContext(
                RuntimeConfig(
                    knowledge_flow_url="http://unused.invalid", service_name="test-pod"
                )
            )
        )
        app = agent_app.create_agent_app({}, config)
        assert set(app.dependency_overrides) == {get_config}
        yield app, store
    finally:
        set_delegation_runtime(previous)
        set_runtime_context(previous_context)


@pytest.mark.parametrize("method,path", REQUESTS)
@pytest.mark.parametrize("subject", [PERSON, DELEGATED, SERVICE])
@pytest.mark.parametrize(
    "error,status,detail",
    [
        (None, 403, "user_not_accept_gcu"),
        (RuntimeError("private SQL details"), 503, "terms_acceptance_unavailable"),
    ],
)
def test_mount_refuses_before_capability_store(
    pod, method, path, subject, error, status, detail
):
    app, store = pod
    terms_app(subject, app=app, accepted=False, error=error)
    client = TestClient(app)
    try:
        response = client.request(method, path, json={"content_md": "edit"})
    finally:
        client.close()
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    store.get.assert_not_awaited()
    store.list_for_session.assert_not_awaited()
    store.upsert.assert_not_awaited()


@pytest.mark.parametrize("method,path", REQUESTS)
@pytest.mark.parametrize("subject", [PERSON, DELEGATED])
def test_mount_admits_owner_once(pod, method, path, subject):
    app, store = pod
    app, _, connection = terms_app(subject, app=app)
    authenticate = AsyncMock(return_value=subject)

    async def identity():
        return await authenticate()

    app.dependency_overrides[oidc.authenticate_request] = identity
    client = TestClient(app)
    try:
        response = client.request(method, path, json={"content_md": "edit"})
    finally:
        client.close()
    assert response.status_code == 200
    connection.scalar.assert_awaited_once()
    assert connection.scalar.await_args.args[1]["uid"] == PERSON.uid
    authenticate.assert_awaited_once()
    if method == "PUT":
        assert store.upsert.await_args.args[0].user_id == PERSON.uid


@pytest.mark.parametrize("method,path", REQUESTS[1:])
@pytest.mark.parametrize("missing,status", [(False, 403), (True, 404)])
def test_mount_keeps_missing_then_foreign_owner_refusals(
    pod, method, path, missing, status
):
    app, store = pod
    store.get.return_value = (
        None if missing else replace(store.get.return_value, user_id="other-person")
    )
    terms_app(DELEGATED, app=app)
    client = TestClient(app)
    try:
        response = client.request(method, path, json={"content_md": "edit"})
    finally:
        client.close()
    assert response.status_code == status
    store.upsert.assert_not_awaited()


def test_mount_lists_only_the_effective_persons_documents(pod):
    app, store = pod
    store.list_for_session.return_value.append(
        replace(store.get.return_value, document_id="foreign", user_id="other-person")
    )
    terms_app(DELEGATED, app=app)
    client = TestClient(app)
    try:
        response = client.get(BASE)
    finally:
        client.close()
    assert response.status_code == 200
    assert [row["document_id"] for row in response.json()] == ["doc-a"]


@pytest.mark.parametrize("method,path", REQUESTS)
def test_mount_rejects_invalid_jwt_before_terms_or_store(
    pod, monkeypatch, method, path
):
    app, store = pod
    app, engine, _ = terms_app(PERSON, app=app)
    del app.dependency_overrides[oidc.authenticate_request]
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    client = TestClient(app)
    try:
        response = client.request(
            method,
            path,
            json={"content_md": "edit"},
            headers={"Authorization": "Bearer malformed"},
        )
    finally:
        client.close()
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    engine.connect.assert_not_called()
    store.get.assert_not_awaited()
    store.list_for_session.assert_not_awaited()
    store.upsert.assert_not_awaited()
