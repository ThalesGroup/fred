"""Control-plane routes under a delegated grant, through the real authentication
chain: team access and account status are decided for the person the role-holding
workload names, never for the workload's own verified identity, and no route
presents the workload's bearer to another service for that person.
"""

from __future__ import annotations

import asyncio
import functools
import json
from collections.abc import Awaitable, Callable, Iterable, Iterator
from types import SimpleNamespace
from typing import Any, NoReturn

import httpx
import pytest
from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.config.models import (
    ManagedAgentTuning,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.knowledge_bases import api as knowledge_bases_api
from control_plane_backend.knowledge_bases import service as knowledge_base_service
from control_plane_backend.product import api as product_api
from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import get_product_service_dependencies
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
    get_config,
)
from fred_core.common import TeamId
from fred_core.common.fastapi_handlers import (
    register_exception_handlers as register_authorization_handlers,
)
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.security import oidc
from fred_core.security.delegation import (
    GRANT_PARAM_NAMES,
    DelegationConfig,
    enforce_account_status,
    initialize_delegation,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.teams.metadata_store import TeamMetadata
from fred_core.users.store.postgres_user_store import get_user_store
from fred_sdk.contracts.capability import (
    CapabilityCatalogEntry,
    ChatControlItem,
    ChatControlsRequest,
    ChatControlsResponse,
    ChatControlsResult,
)
from httpx2 import Response

_CREATOR = "person-synthetic"
_RUN = "run-synthetic"
_TEAM = TeamId("team-synthetic")
_RUNTIME = "runtime-synthetic"
_AGENT = "agent-synthetic"
_WORKLOAD_CLIENT = "workload-client-synthetic"
_WORKLOAD_SUBJECT = "workload-subject-synthetic"
_ISSUER = "https://id.invalid/realms/fred"
_AUDIENCE = "fred-delegation"
_WORKLOAD_TOKEN = "workload-token-synthetic"
_PERSON = "person-own-synthetic"
_PERSON_TOKEN = "person-token-synthetic"
_GRANT = {"person": _CREATOR, "run": _RUN, "agent": _AGENT}
_INSTANCE = "instance-synthetic"
_SESSION = "session-synthetic"
_CAPABILITY = "capability-synthetic"
_REACHED = 418


class _RecordingRebac(NoopRebacEngine):
    """Engine requiring an active account, recording the subject of every authorization read.

    `suspended` is true only for the people listed there, as for a stored direct
    tuple; `unreachable` makes that check fail. Every other permission is granted.
    """

    def __init__(
        self, *, suspended: frozenset[str] = frozenset(), unreachable: bool = False
    ) -> None:
        self.reads: list[tuple[str, str, str]] = []
        self._suspended = suspended
        self._unreachable = unreachable

    @property
    def enabled(self) -> bool:
        return True

    @property
    def requires_active_accounts(self) -> bool:
        return True

    async def validate_account_status_model(self) -> None:
        return None  # the shipped model, which defines `suspended`

    async def _has_permission_raw(
        self,
        subject: RebacReference,
        permission: RebacPermission | RelationType,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        self.reads.append((subject.id, permission.value, resource.id))
        if permission == RelationType.SUSPENDED and resource.id == ORGANIZATION_ID:
            if self._unreachable:
                raise ConnectionError("synthetic store outage")
            return subject.id in self._suspended
        return True


async def _team_metadata(team_id: TeamId) -> TeamMetadata:
    return TeamMetadata(id=team_id, name="Synthetic team")


_MANAGED_INSTANCE = AgentInstanceRecord(
    agent_instance_id=_INSTANCE,
    team_id=_TEAM,
    template_id=f"{_RUNTIME}:{_AGENT}",
    source_runtime_id=_RUNTIME,
    source_agent_id=_AGENT,
    display_name="Synthetic agent",
    description=None,
    enabled=True,
    created_by=_PERSON,
    tuning=ManagedAgentTuning(
        role="Synthetic agent",
        description="Synthetic agent",
        selected_capability_ids=[_CAPABILITY],
    ),
)


async def _instance_for_team(
    agent_instance_id: str, team_id: TeamId
) -> AgentInstanceRecord | None:
    if (agent_instance_id, team_id) == (_INSTANCE, _TEAM):
        return _MANAGED_INSTANCE
    return None


async def _no_routing_policy(*, team_id: TeamId) -> None:
    return None


async def _no_reasoning_models() -> set[str]:
    return set()


def _deps(rebac: _RecordingRebac, resolved: list[str] | None = None) -> Any:
    async def get_for_team(
        agent_instance_id: str, team_id: TeamId
    ) -> AgentInstanceRecord | None:
        if resolved is not None:
            resolved.append(agent_instance_id)
        return await _instance_for_team(agent_instance_id, team_id)

    return SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    RuntimeCatalogSourceConfig(
                        runtime_id=_RUNTIME,
                        base_url="http://runtime-synthetic.invalid",
                        enabled=True,
                        ingress_prefix=f"/runtime/{_RUNTIME}",
                    )
                ]
            )
        ),
        team_dependencies=SimpleNamespace(
            rebac=rebac,
            get_team_metadata_store=lambda: SimpleNamespace(
                get_by_team_id=_team_metadata
            ),
        ),
        get_agent_instance_store=lambda: SimpleNamespace(get_for_team=get_for_team),
        get_kpi_writer=NoOpKPIWriter,
        get_team_routing_policy_store=lambda: SimpleNamespace(get=_no_routing_policy),
        get_model_reasoning_store=lambda: SimpleNamespace(
            list_enabled_model_ids=_no_reasoning_models
        ),
    )


@pytest.fixture
def delegating_workload(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    caller = KeycloakUser(
        uid=_WORKLOAD_SUBJECT,
        username=_WORKLOAD_SUBJECT,
        roles=[],
        client_id=_WORKLOAD_CLIENT,
        token_issuer=_ISSUER,
        token_audiences=frozenset({_AUDIENCE}),
        token_type="Bearer",
        caller_roles=frozenset({"delegation_caller"}),
    )
    person = KeycloakUser(
        uid=_PERSON,
        username=_PERSON,
        roles=[],
        client_id="app",
        token_issuer=_ISSUER,
        token_type="Bearer",
    )
    principals = {_WORKLOAD_TOKEN: caller, _PERSON_TOKEN: person}
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", principals.__getitem__)
    initialize_delegation(
        DelegationConfig(accept_delegated_calls=True),
        issuers=[_ISSUER],
        user_clients=["app"],
    )
    yield


def _client(rebac: _RecordingRebac, resolved: list[str] | None = None) -> TestClient:
    # Installed as at startup, so the request's account status check reads this engine.
    asyncio.run(enforce_account_status(rebac))
    app = FastAPI()
    app.include_router(product_api.router)
    app.include_router(knowledge_bases_api.router)
    register_authorization_handlers(app)
    app.dependency_overrides[get_product_service_dependencies] = lambda: _deps(
        rebac, resolved
    )
    app.dependency_overrides[get_user_store] = lambda: None
    app.dependency_overrides[get_config] = lambda: SimpleNamespace(
        app=SimpleNamespace(gcu_version=None)
    )
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _prepare(monkeypatch: pytest.MonkeyPatch, rebac: _RecordingRebac) -> Response:
    async def templates(base_url: str, include_non_public: bool = False):
        return [SimpleNamespace(template_agent_id=_AGENT)]

    monkeypatch.setattr(product_service, "_fetch_runtime_templates", templates)
    return _client(rebac).post(
        f"/teams/{_TEAM}/runtimes/{_RUNTIME}/agents/{_AGENT}/prepare-execution",
        params=_GRANT,
        headers=_bearer(_WORKLOAD_TOKEN),
    )


def test_prepare_step_authorizes_the_named_creator(
    monkeypatch: pytest.MonkeyPatch, delegating_workload: None
) -> None:
    rebac = _RecordingRebac()

    response = _prepare(monkeypatch, rebac)

    assert response.status_code == 200
    assert response.json() == {
        "runtime_id": _RUNTIME,
        "agent_id": _AGENT,
        "team_id": _TEAM,
        "evaluate_url": f"/runtime/{_RUNTIME}/agents/evaluate",
    }
    assert rebac.reads == [
        (_CREATOR, RelationType.SUSPENDED.value, ORGANIZATION_ID),
        (_CREATOR, TeamPermission.CAN_READ.value, _TEAM),
    ]


@pytest.mark.parametrize(
    ("account_status", "status", "cause"),
    [
        ({"suspended": frozenset({_CREATOR})}, 403, "account_suspended"),
        ({"unreachable": True}, 503, "account_status_unavailable"),
    ],
    ids=["suspended", "unreachable"],
)
def test_prepare_step_refuses_on_the_named_creators_account_status(
    monkeypatch: pytest.MonkeyPatch,
    delegating_workload: None,
    account_status: dict[str, Any],
    status: int,
    cause: str,
) -> None:
    rebac = _RecordingRebac(**account_status)

    response = _prepare(monkeypatch, rebac)

    assert response.status_code == status
    assert response.headers["X-Fred-Denial-Cause"] == cause
    assert rebac.reads[0] == (_CREATOR, RelationType.SUSPENDED.value, ORGANIZATION_ID)
    assert {subject for subject, _, _ in rebac.reads} == {_CREATOR}


@pytest.mark.parametrize(
    ("account_status", "status", "cause"),
    [
        ({"suspended": frozenset({_CREATOR, _PERSON})}, 403, "account_suspended"),
        ({"unreachable": True}, 503, "account_status_unavailable"),
    ],
    ids=["suspended", "unreachable"],
)
@pytest.mark.parametrize(
    ("token", "grant", "subject"),
    [(_WORKLOAD_TOKEN, _GRANT, _CREATOR), (_PERSON_TOKEN, None, _PERSON)],
    ids=["person-named-by-a-grant", "person-own-bearer"],
)
@pytest.mark.parametrize(
    ("method", "route"),
    [("GET", "runtime"), ("POST", "prepare-execution")],
    ids=["runtime-binding", "execution-preparation"],
)
def test_personal_team_routes_refuse_a_suspended_person(
    delegating_workload: None,
    account_status: dict[str, Any],
    status: int,
    cause: str,
    token: str,
    grant: dict[str, str] | None,
    subject: str,
    method: str,
    route: str,
) -> None:
    """A personal team makes no relationship check, so the request's own
    account status check is all that stands between a suspended person and it."""
    rebac, resolved = _RecordingRebac(**account_status), []

    response = _client(rebac, resolved).request(
        method,
        f"/teams/personal-{subject}/agent-instances/{_INSTANCE}/{route}",
        params=grant,
        headers=_bearer(token),
    )

    assert response.status_code == status
    assert response.headers["X-Fred-Denial-Cause"] == cause
    assert rebac.reads == [(subject, RelationType.SUSPENDED.value, ORGANIZATION_ID)]
    assert resolved == []


@pytest.mark.parametrize(
    "path",
    [
        "/teams/{team_id}/runtimes/{runtime_id}/agents/{agent_id}/prepare-execution",
        "/teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution",
    ],
)
def test_prepare_execution_declares_the_grant_without_requiring_it(path: str) -> None:
    """A workload names the person it prepares for; an interactive caller names
    nobody. Both reach these routes, so the grant is declared but not required."""
    app = FastAPI()
    app.include_router(product_api.router)
    operation = app.openapi()["paths"][path]["post"]
    declared = {
        parameter["name"]: parameter
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "query" and parameter["name"] in GRANT_PARAM_NAMES
    }

    assert set(declared) == set(GRANT_PARAM_NAMES)
    assert not any(parameter.get("required") for parameter in declared.values())


_ENROLLMENT = {
    "template_id": f"{_RUNTIME}:{_AGENT}",
    "display_name": "Synthetic agent",
    "usage_statement": "Synthetic use",
}
_ASSET = {"asset_files": ("asset.txt", b"synthetic", "text/plain")}
_ASSET_SLOT = f"{_CAPABILITY}:slot"

# Every route that presents its caller's bearer to another service, with the
# first protected step it takes.
_BEARER_RELAYING_ROUTES = [
    pytest.param(
        "POST",
        f"/teams/{_TEAM}/agent-instances",
        {"json": _ENROLLMENT},
        "team_access",
        id="enroll",
    ),
    pytest.param(
        "PATCH",
        f"/teams/{_TEAM}/agent-instances/{_INSTANCE}",
        {"json": {"display_name": "Renamed"}},
        "team_access",
        id="update",
    ),
    pytest.param(
        "POST",
        f"/teams/{_TEAM}/agent-instances/with-assets",
        {
            "data": {"request": json.dumps(_ENROLLMENT), "asset_slots": _ASSET_SLOT},
            "files": _ASSET,
        },
        "team_access",
        id="enroll-with-assets",
    ),
    pytest.param(
        "PATCH",
        f"/teams/{_TEAM}/agent-instances/{_INSTANCE}/with-assets",
        {
            "data": {"request": json.dumps({}), "asset_slots": _ASSET_SLOT},
            "files": _ASSET,
        },
        "team_access",
        id="update-with-assets",
    ),
    pytest.param(
        "POST",
        "/me/sessions/bulk-delete",
        {"json": {"sessions": [{"session_id": _SESSION, "team_id": _TEAM}]}},
        "bulk_session_delete",
        id="bulk-session-delete",
    ),
    pytest.param(
        "DELETE",
        f"/teams/{_TEAM}/sessions/{_SESSION}/attachments/attachment-synthetic",
        {},
        "team_access",
        id="attachment-delete",
    ),
    pytest.param(
        "DELETE",
        f"/teams/{_TEAM}/sessions/{_SESSION}",
        {},
        "team_access",
        id="session-delete",
    ),
    pytest.param(
        "POST",
        "/knowledge-bases/instances",
        {
            "json": {
                "definition_id": "definition-synthetic",
                "team_id": _TEAM,
                "folder_name": "Synthetic folder",
                "schedule": {"type": "interval", "every_seconds": 60},
            }
        },
        "knowledge_base_create",
        id="knowledge-base-create",
    ),
    pytest.param(
        "DELETE",
        "/knowledge-bases/instances/knowledge-base-instance-synthetic",
        {},
        "knowledge_base_delete",
        id="knowledge-base-delete",
    ),
]


@pytest.fixture
def protected_work(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Each route's first protected step, recorded with its subject and stopped there.

    That step is team authorization, or a service call authorizing, writing and
    calling onward itself; nothing past it runs, so no store write or onward call.
    """
    reached: list[tuple[str, str]] = []

    def stand_in(step: str) -> Callable[..., Awaitable[NoReturn]]:
        async def reach(*args: Any, **kwargs: Any) -> NoReturn:
            subject = kwargs["user"] if "user" in kwargs else args[0]
            reached.append((step, subject.uid))
            raise HTTPException(status_code=_REACHED, detail="protected_work")

        return reach

    monkeypatch.setattr(product_api, "require_team_access", stand_in("team_access"))
    monkeypatch.setattr(
        product_api, "bulk_delete_sessions", stand_in("bulk_session_delete")
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "create_instance_for_team",
        stand_in("knowledge_base_create"),
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "delete_instance_for_team",
        stand_in("knowledge_base_delete"),
    )
    return reached


@pytest.mark.parametrize(
    ("method", "path", "body", "first_step"), _BEARER_RELAYING_ROUTES
)
def test_a_route_relaying_the_bearer_refuses_a_person_named_by_a_grant(
    delegating_workload: None,
    protected_work: list[tuple[str, str]],
    method: str,
    path: str,
    body: dict[str, Any],
    first_step: str,
) -> None:
    response = _client(_RecordingRebac()).request(
        method, path, params=_GRANT, headers=_bearer(_WORKLOAD_TOKEN), **body
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "requires_own_credential"}
    assert protected_work == []


@pytest.mark.parametrize(
    ("token", "subject"),
    [(_WORKLOAD_TOKEN, _WORKLOAD_SUBJECT), (_PERSON_TOKEN, _PERSON)],
    ids=["workload-as-itself", "person-own-bearer"],
)
@pytest.mark.parametrize(
    ("method", "path", "body", "first_step"), _BEARER_RELAYING_ROUTES
)
def test_a_caller_presenting_its_own_bearer_reaches_the_route(
    delegating_workload: None,
    protected_work: list[tuple[str, str]],
    method: str,
    path: str,
    body: dict[str, Any],
    first_step: str,
    token: str,
    subject: str,
) -> None:
    response = _client(_RecordingRebac()).request(
        method, path, headers=_bearer(token), **body
    )

    assert response.status_code == _REACHED
    assert protected_work == [(first_step, subject)]


@pytest.fixture
def agent_pod(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[httpx.Request]]:
    """The agent pod behind the control plane's real HTTP client, recording every
    request it receives. Like the real pod, it evaluates chat controls only for
    an authenticated caller."""
    received: list[httpx.Request] = []
    template = {
        "template_agent_id": _AGENT,
        "title": "Synthetic agent",
        "description": "Synthetic agent",
        "kind": "assistant",
        "available_capabilities": [
            CapabilityCatalogEntry(
                id=_CAPABILITY,
                version="1",
                name="Synthetic capability",
                description="Synthetic capability",
                icon="extension",
            ).model_dump(mode="json")
        ],
    }

    def serve(request: httpx.Request) -> httpx.Response:
        received.append(request)
        if request.url.path == "/agents/templates":
            return httpx.Response(200, json=[template])
        if "Authorization" not in request.headers:
            return httpx.Response(401)
        asked = ChatControlsRequest.model_validate_json(request.content)
        evaluated = ChatControlsResponse(
            results=[
                ChatControlsResult(
                    capability_id=item.capability_id,
                    manifest_version="1",
                    controls=[ChatControlItem(widget="rag_scope")],
                )
                for item in asked.items
            ]
        )
        return httpx.Response(200, json=evaluated.model_dump(mode="json"))

    monkeypatch.setattr(
        product_service.httpx,
        "AsyncClient",
        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(serve)),
    )
    product_service._chat_controls_cache.clear()
    yield received
    product_service._chat_controls_cache.clear()


@pytest.mark.parametrize(
    ("token", "grant", "pod_requests", "chat_controls"),
    [
        pytest.param(
            _WORKLOAD_TOKEN,
            _GRANT,
            [("/agents/templates", None)],
            [],
            id="person-named-by-a-grant",
        ),
        pytest.param(
            _PERSON_TOKEN,
            None,
            [
                ("/agents/templates", None),
                ("/agents/capabilities/chat-controls", f"Bearer {_PERSON_TOKEN}"),
            ],
            [{"capability_id": _CAPABILITY, "widget": "rag_scope"}],
            id="person-own-bearer",
        ),
    ],
)
def test_managed_preparation_presents_only_the_callers_own_bearer_to_the_pod(
    delegating_workload: None,
    agent_pod: list[httpx.Request],
    token: str,
    grant: dict[str, str] | None,
    pod_requests: list[tuple[str, str | None]],
    chat_controls: list[dict[str, str]],
) -> None:
    response = _client(_RecordingRebac()).post(
        f"/teams/{_TEAM}/agent-instances/{_INSTANCE}/prepare-execution",
        params=grant,
        headers=_bearer(token),
    )

    assert response.status_code == 200
    assert [
        (request.url.path, request.headers.get("Authorization"))
        for request in agent_pod
    ] == pod_requests
    assert response.json()["chat_controls"] == chat_controls
