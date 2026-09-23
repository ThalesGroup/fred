"""The direct runtime-agent prepare step under a delegated grant: team access
and standing are decided for the person the allow-listed workload names, never
for the workload's own verified identity.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from control_plane_backend.config.models import RuntimeCatalogSourceConfig
from control_plane_backend.product import api as product_api
from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import get_product_service_dependencies
from fastapi import FastAPI
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
from fred_core.security import oidc
from fred_core.security.delegation import (
    CallerPolicy,
    DelegationConfig,
    initialize_delegation,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.teams.metadata_store import TeamMetadata
from fred_core.users.store.postgres_user_store import get_user_store

_CREATOR = "person-synthetic"
_RUN = "run-synthetic"
_TEAM = TeamId("team-synthetic")
_RUNTIME = "runtime-synthetic"
_AGENT = "agent-synthetic"
_WORKLOAD_CLIENT = "workload-client-synthetic"
_WORKLOAD_SUBJECT = "workload-subject-synthetic"
_ISSUER = "https://id.invalid/realms/fred"
_AUDIENCE = "control-plane"


class _RecordingRebac(NoopRebacEngine):
    """Engine requiring an active account, recording the subject of every authorization read."""

    def __init__(self) -> None:
        self.reads: list[tuple[str, str, str]] = []

    @property
    def enabled(self) -> bool:
        return True

    @property
    def enforces_standing(self) -> bool:
        return True

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
        return True


async def _team_metadata(team_id: TeamId) -> TeamMetadata:
    return TeamMetadata(id=team_id, name="Synthetic team")


def _deps(rebac: _RecordingRebac) -> Any:
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
    )
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda _token: caller)
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(client_id=_WORKLOAD_CLIENT, subject=_WORKLOAD_SUBJECT)
            ],
        ),
        issuer=_ISSUER,
        audience=_AUDIENCE,
    )
    yield
    initialize_delegation(DelegationConfig())


def test_prepare_step_authorizes_the_named_creator(
    monkeypatch: pytest.MonkeyPatch, delegating_workload: None
) -> None:
    rebac = _RecordingRebac()

    async def templates(base_url: str, include_non_public: bool = False):
        return [SimpleNamespace(template_agent_id=_AGENT)]

    monkeypatch.setattr(product_service, "_fetch_runtime_templates", templates)
    app = FastAPI()
    app.include_router(product_api.router)
    app.dependency_overrides[get_product_service_dependencies] = lambda: _deps(rebac)
    app.dependency_overrides[get_user_store] = lambda: None
    app.dependency_overrides[get_config] = lambda: SimpleNamespace(
        app=SimpleNamespace(gcu_version=None)
    )

    response = TestClient(app).post(
        f"/teams/{_TEAM}/runtimes/{_RUNTIME}/agents/{_AGENT}/prepare-execution",
        params={"person": _CREATOR, "run": _RUN, "agent": _AGENT},
        headers={"Authorization": "Bearer synthetic"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "runtime_id": _RUNTIME,
        "agent_id": _AGENT,
        "team_id": _TEAM,
        "evaluate_url": f"/runtime/{_RUNTIME}/agents/evaluate",
    }
    assert rebac.reads == [
        (_CREATOR, RelationType.ACTIVE.value, ORGANIZATION_ID),
        (_CREATOR, TeamPermission.CAN_READ.value, _TEAM),
    ]
