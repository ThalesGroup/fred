# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Turn-free capability ports: the save-path model port and the route team authorizer."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.common import ModelConfiguration
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.capabilities import platform_ports
from fred_runtime.capabilities.platform_ports import (
    CapabilitySaveRouting,
    RebacCapabilityTeamAuthorizer,
    RoutedCapabilityModelPort,
    parse_save_routing,
    team_authorizer_binder,
)
from fred_runtime.model_routing.contracts import (
    ModelCapability,
    ModelProfile,
    ModelRoutingPolicy,
)
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.resolver import ModelRoutingResolver
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_sdk.contracts.capability.manifest import model_capability_id
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    CapabilityModelUnavailableError,
    CapabilityTeamAuthorizer,
    capability_team_authorizer,
)
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

TEXT_PROFILE = "chat.text"
VISION_PROFILE = "chat.vision"
TEXT_ID = model_capability_id("openai", "text-model")
VISION_ID = model_capability_id("openai", "vision-model")


class _NamedProvider:
    """Builds a fake chat model that answers with the wire model name."""

    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object:
        return FakeListChatModel(responses=[model_config.name or ""])


def _factory() -> RoutedChatModelFactory:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: TEXT_PROFILE},
        profiles=(
            ModelProfile(
                profile_id=TEXT_PROFILE,
                capability=ModelCapability.CHAT,
                model=ModelConfiguration(provider="openai", name="text-model"),
            ),
            ModelProfile(
                profile_id=VISION_PROFILE,
                capability=ModelCapability.CHAT,
                model=ModelConfiguration(provider="openai", name="vision-model"),
                supports_vision=True,
            ),
        ),
    )
    return RoutedChatModelFactory(
        resolver=ModelRoutingResolver(policy), provider=_NamedProvider()
    )


def _binding(
    *,
    team_id: str | None = "team-1",
    chat_default_profile_id: str | None = None,
    agent_profile_overrides: dict[str, str] | None = None,
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            team_id=team_id,
            chat_default_profile_id=chat_default_profile_id,
            agent_profile_overrides=agent_profile_overrides,
        ),
        portable_context=PortableContext(
            request_id="req",
            correlation_id="req",
            actor="tester",
            tenant="default",
            environment=PortableEnvironment.DEV,
        ),
    )


def _port(
    monkeypatch: pytest.MonkeyPatch,
    *,
    usable: frozenset[str] | None = None,
    **binding_kwargs: object,
) -> RoutedCapabilityModelPort:
    async def _usable(rebac: object, team_id: str) -> frozenset[str] | None:
        return usable

    monkeypatch.setattr(platform_ports, "usable_model_capability_ids", _usable)
    return RoutedCapabilityModelPort(
        binding=_binding(**binding_kwargs),  # type: ignore[arg-type]
        routing_agent_id="agent-1",
        factory=_factory(),
        rebac=None,
    )


def _ask(port: RoutedCapabilityModelPort, **kwargs: object) -> str:
    message = asyncio.run(port.ainvoke([HumanMessage(content="hi")], **kwargs))  # type: ignore[arg-type]
    assert isinstance(message, AIMessage)
    return str(message.content)


# ---------------------------------------------------------------------------
# Model port: routing, override, vision refusal, ReBAC
# ---------------------------------------------------------------------------


def test_port_uses_the_agent_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _ask(_port(monkeypatch)) == "text-model"


def test_port_follows_the_team_default(monkeypatch: pytest.MonkeyPatch) -> None:
    port = _port(monkeypatch, chat_default_profile_id=VISION_PROFILE)
    assert _ask(port, require_vision=True) == "vision-model"


def test_profile_override_wins_when_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    port = _port(monkeypatch, usable=frozenset({TEXT_ID, VISION_ID}))
    assert _ask(port, profile_id=VISION_PROFILE, require_vision=True) == "vision-model"


def test_unknown_profile_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _ask(_port(monkeypatch), profile_id="chat.ghost") == "text-model"


def test_vision_refused_on_a_text_only_model(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(CapabilityModelUnavailableError, match="vision"):
        _ask(_port(monkeypatch), require_vision=True)


def test_unusable_override_is_ignored_then_vision_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port(monkeypatch, usable=frozenset({TEXT_ID}))
    with pytest.raises(CapabilityModelUnavailableError, match="vision"):
        _ask(port, profile_id=VISION_PROFILE, require_vision=True)


def test_default_outside_usable_models_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(CapabilityModelUnavailableError):
        _ask(_port(monkeypatch, usable=frozenset()))


def test_team_override_for_the_template_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    port = _port(monkeypatch, agent_profile_overrides={"agent-1": VISION_PROFILE})
    assert _ask(port) == "vision-model"


def test_a_revoked_model_stops_being_used_after_the_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usable = {"ids": frozenset({TEXT_ID, VISION_ID})}
    queries: list[str] = []
    now = {"t": 1000.0}

    async def _usable(rebac: object, team_id: str) -> frozenset[str]:
        queries.append(team_id)
        return usable["ids"]

    monkeypatch.setattr(platform_ports, "usable_model_capability_ids", _usable)
    monkeypatch.setattr(platform_ports, "_monotonic", lambda: now["t"])
    port = RoutedCapabilityModelPort(
        binding=_binding(), routing_agent_id="agent-1", factory=_factory(), rebac=None
    )

    assert _ask(port, profile_id=VISION_PROFILE) == "vision-model"
    usable["ids"] = frozenset({TEXT_ID})
    now["t"] += 5
    assert _ask(port, profile_id=VISION_PROFILE) == "vision-model"
    assert len(queries) == 1
    now["t"] += platform_ports._USABLE_MODELS_TTL_S
    assert _ask(port, profile_id=VISION_PROFILE) == "text-model"
    assert len(queries) == 2


def test_port_without_routed_factory_fails_closed() -> None:
    port = RoutedCapabilityModelPort(
        binding=_binding(), routing_agent_id="a", factory=None, rebac=None
    )
    with pytest.raises(CapabilityModelUnavailableError):
        _ask(port)


# ---------------------------------------------------------------------------
# Save path wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def runtime_context():
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid"))
    )
    yield
    set_runtime_context(None)


@pytest.mark.usefixtures("runtime_context")
def test_save_services_carry_the_model_port_and_routing() -> None:
    routing = CapabilitySaveRouting(
        template_agent_id="template-1",
        chat_default_profile_id=VISION_PROFILE,
        agent_profile_overrides={"template-1": TEXT_PROFILE},
    )
    services = agent_app_module._build_capability_save_services(
        capability_id="ppt_builder",
        user_id="u1",
        team_id="team-1",
        access_token="secret-token",
        agent_instance_id="agent-1",
        routing=routing,
    )
    port = services.capability_model
    assert isinstance(port, RoutedCapabilityModelPort)
    context = port._binding.runtime_context
    assert context.chat_default_profile_id == VISION_PROFILE
    assert context.agent_profile_overrides == {"template-1": TEXT_PROFILE}
    assert context.access_token is None
    assert port._binding.platform_chat_model_binding is None
    assert port._definition.agent_id == "template-1"


def test_parse_save_routing_from_query_parameters() -> None:
    routing = parse_save_routing(
        {
            "template_agent_id": "template-1",
            "chat_default_profile_id": VISION_PROFILE,
            "agent_profile_overrides": json.dumps({"template-1": TEXT_PROFILE}),
            "usable_model_ids": "x",
        }
    )
    assert routing == CapabilitySaveRouting(
        template_agent_id="template-1",
        chat_default_profile_id=VISION_PROFILE,
        agent_profile_overrides={"template-1": TEXT_PROFILE},
    )
    assert parse_save_routing({}) is None
    with pytest.raises(HTTPException) as exc:
        parse_save_routing({"agent_profile_overrides": "3"})
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Team authorizer
# ---------------------------------------------------------------------------


class _FakeRebac:
    enabled = True

    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str]] = []

    async def check_user_team_permission_or_raise(
        self, user: KeycloakUser, permission: object, team_id: str
    ) -> None:
        self.calls.append((str(permission), team_id))
        if not self.allowed:
            raise AuthorizationError(user.uid, "update", Resource.TEAM, "denied")


def _user(uid: str = "u1") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[])


def _require(authorizer: RebacCapabilityTeamAuthorizer, team_id: str) -> None:
    asyncio.run(authorizer.require_agent_editor(team_id))


def test_rebac_denial_is_403() -> None:
    rebac = _FakeRebac(allowed=False)
    authorizer = RebacCapabilityTeamAuthorizer(
        user=_user(),
        enforce=True,
        rebac=rebac,  # type: ignore[arg-type]
    )
    with pytest.raises(HTTPException) as exc:
        _require(authorizer, "team-1")
    assert exc.value.status_code == 403
    assert rebac.calls and "team-1" in rebac.calls[0]


def test_agent_editor_passes() -> None:
    rebac = _FakeRebac(allowed=True)
    authorizer = RebacCapabilityTeamAuthorizer(
        user=_user(),
        enforce=True,
        rebac=rebac,  # type: ignore[arg-type]
    )
    _require(authorizer, "team-1")


def test_personal_team_belongs_to_its_owner_only() -> None:
    authorizer = RebacCapabilityTeamAuthorizer(
        user=_user("u1"), enforce=True, rebac=None
    )
    _require(authorizer, "personal-u1")
    with pytest.raises(HTTPException) as exc:
        _require(authorizer, "personal-u2")
    assert exc.value.status_code == 403


def test_secured_route_without_user_is_403() -> None:
    authorizer = RebacCapabilityTeamAuthorizer(user=None, enforce=True, rebac=None)
    with pytest.raises(HTTPException):
        _require(authorizer, "team-1")


def _route_app(*, bind: bool) -> TestClient:
    router = APIRouter()

    @router.get("/rows/{team_id}")
    async def read_row(
        team_id: str,
        authz: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> dict[str, str]:
        await authz.require_agent_editor(team_id)
        return {"team_id": team_id}

    app = FastAPI()
    deps = [Depends(team_authorizer_binder(security_enabled=False))] if bind else []
    app.include_router(router, dependencies=deps)
    return TestClient(app)


def test_bound_router_reaches_the_authorizer() -> None:
    assert _route_app(bind=True).get("/rows/team-1").status_code == 200


def test_unbound_router_fails_closed() -> None:
    assert _route_app(bind=False).get("/rows/team-1").status_code == 503
