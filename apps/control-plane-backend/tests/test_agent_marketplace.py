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

"""Agents marketplace: publication rules and snapshot, failed republication,
removal (manual and automatic), the card state per role, likes, listing,
detail and import, on real SQLite stores with the pod and ReBAC faked."""

# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import control_plane_backend.agent_marketplace.service as marketplace
import control_plane_backend.product.agent_copy as agent_copy
import control_plane_backend.product.service as product_service
import httpx
import pytest
import pytest_asyncio
from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.agent_marketplace.schemas import (
    PublishAgentRequest,
    UnpublishAgentRequest,
)
from control_plane_backend.agent_marketplace.store import AgentMarketplaceStore
from control_plane_backend.config.models import (
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.marketplace_settings.store import (
    PlatformMarketplaceSettingsStore,
)
from control_plane_backend.models.agent_marketplace_models import (
    AgentMarketplaceEntryFileRow,
    AgentMarketplaceEntryRow,
    AgentMarketplaceImportRow,
    AgentMarketplaceLikeRow,
)
from control_plane_backend.notifications.schemas import (
    AgentMarketplaceRemovedNotification,
    AgentMarketplaceRemovedPayload,
)
from control_plane_backend.notifications.service import NotificationService
from control_plane_backend.notifications.store import NotificationStore
from control_plane_backend.product.schemas import ManagedAgentInstanceSummary
from fred_core import (
    AuthorizationError,
    KeycloakUser,
    OrganizationPermission,
    RebacReference,
    Resource,
    TeamPermission,
)
from fred_core.common import PostgresStoreConfig, TeamId
from fred_core.sql import create_async_engine_from_config
from fred_core.teams.metadata_store import (
    TEAM_DESCRIPTION_PLACEHOLDER,
    TeamMetadataPatch,
    TeamMetadataStore,
    TeamVisibility,
)
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine
from test_capability_selection_1974 import _DEMO_ENTRY, _template_payload

_TEAM = TeamId("alpha")
_OTHER = TeamId("beta")
_THIRD = TeamId("gamma")
_EDITOR, _MEMBER, _ADMIN, _PLATFORM, _OUTSIDER = (
    "editor",
    "member",
    "team-admin",
    "platform-admin",
    "outsider",
)
_EDITOR_PERMS = {
    TeamPermission.CAN_USE_TEAM_AGENTS,
    TeamPermission.CAN_UPDATE_AGENTS,
    TeamPermission.CAN_PUBLISH_MARKETPLACE_AGENTS,
    TeamPermission.CAN_UNPUBLISH_MARKETPLACE_AGENTS,
}
_TEMPLATE_CAP = product_service.template_capability_id("runtime-a", "rags.sample.echo")


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=None)


class _Rebac:
    """Team permissions per `{team: {uid: {permission}}}`; platform admins by uid."""

    def __init__(self) -> None:
        self.perms: dict[str, dict[str, set[TeamPermission]]] = {
            _TEAM: {
                _EDITOR: set(_EDITOR_PERMS),
                _MEMBER: {TeamPermission.CAN_USE_TEAM_AGENTS},
                _ADMIN: {TeamPermission.CAN_UNPUBLISH_MARKETPLACE_AGENTS},
            },
            _OTHER: {_EDITOR: set(_EDITOR_PERMS), _OUTSIDER: set(_EDITOR_PERMS)},
            _THIRD: {_EDITOR: set(_EDITOR_PERMS), _OUTSIDER: set(_EDITOR_PERMS)},
        }
        self.platform_admins = {_PLATFORM}

    def _has(self, uid: str, permission: Any, resource_id: str) -> bool:
        if isinstance(permission, OrganizationPermission):
            return uid in self.platform_admins
        return permission in self.perms.get(resource_id, {}).get(uid, set())

    async def has_user_permission(self, user, permission, resource_id, **_) -> bool:
        return self._has(user.uid, permission, resource_id)

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **_
    ) -> None:
        if not self._has(user.uid, permission, resource_id):
            raise AuthorizationError(user.uid, str(permission), Resource.TEAM, "no")

    async def has_permissions(self, subject, permissions, resource, **_) -> list[bool]:
        return [self._has(subject.id, p, resource.id) for p in permissions]

    async def lookup_user_resources(self, user, permission, **_):
        return [
            RebacReference(Resource.TEAM, team_id)
            for team_id, users in self.perms.items()
            if permission in users.get(user.uid, set())
        ]

    async def revoke_team_public_relations(self, team_ids, **_):
        return None

    async def delete_all_relations_of_reference(self, reference) -> None:
        return None


@dataclass
class _Pod:
    """The pod's `export-config` and `copy-config`, as recorded calls."""

    export_status: dict[str, int] = field(default_factory=dict)
    unreachable: bool = False
    exports: list[tuple[str, dict[str, Any], str | None]] = field(default_factory=list)
    copies: list[tuple[str, Any]] = field(default_factory=list)
    on_export: Any = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.unreachable:
            raise httpx.ConnectError("down", request=request)
        capability_id = request.url.path.split("/")[-2]
        body = json.loads(request.content)
        self.exports.append((capability_id, body, request.headers.get("Authorization")))
        if self.on_export is not None:
            await self.on_export()
        status = self.export_status.get(capability_id, 200)
        if status != 200:
            return httpx.Response(status, json={"detail": "nope"})
        config = dict(body["config"]["config"])
        files: dict[str, str] = {}
        if capability_id == "demo_echo":
            config["library_ids"] = []  # scope-private reset by the pod
        else:
            files["template.pptx"] = base64.b64encode(b"PPTX-BYTES").decode()
        return httpx.Response(
            200,
            json={
                "schema_version": body["config"]["schema_version"],
                "config": config,
                "files": files,
            },
        )


@dataclass
class _Env:
    deps: Any
    agents: AgentInstanceStore
    market: AgentMarketplaceStore
    teams: TeamMetadataStore
    settings: PlatformMarketplaceSettingsStore
    rebac: _Rebac
    pod: _Pod
    engine: AsyncEngine
    audits: list[tuple[str, dict[str, Any]]]
    usable: dict[str, set[str] | None]
    public_template: list[bool]
    template_kwargs: dict[str, Any]
    notifications: NotificationService


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    from control_plane_backend.models.base import Base as CPBase
    from fred_core.models.base import Base as FredCoreBase

    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "marketplace.sqlite3"))
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(FredCoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)

    teams = TeamMetadataStore(engine)
    for team_id, name in ((_TEAM, "Alpha"), (_OTHER, "Beta"), (_THIRD, "Gamma")):
        await teams.create(team_id, name, TEAM_DESCRIPTION_PLACEHOLDER)
        await teams.upsert(team_id, TeamMetadataPatch(visibility=TeamVisibility.PUBLIC))
    settings = PlatformMarketplaceSettingsStore(engine)
    await settings.set(
        agents_publishing_enabled=True, agents_publish_quota=2, updated_by=None
    )
    notifications = NotificationService(NotificationStore(engine))
    agents = AgentInstanceStore(engine, notifications=notifications)
    market = AgentMarketplaceStore(engine)
    rebac = _Rebac()
    pod = _Pod()
    client = httpx.AsyncClient(transport=httpx.MockTransport(pod.handle))
    usable: dict[str, set[str] | None] = {}
    public_template = [True]
    template_kwargs: dict[str, Any] = {}

    async def _templates(base_url: str, include_non_public: bool = False):
        if not include_non_public and not public_template[0]:
            return []
        return [_template_payload(**template_kwargs)]

    async def _usable(_rebac, team_id):
        return usable.get(str(team_id))

    async def _copy(*, base_url, capability_id, request, authorization):
        pod.copies.append((capability_id, request))
        return {
            "schema_version": request.config.schema_version,
            "config": request.config.config,
            "notices": [],
        }

    audits: list[tuple[str, dict[str, Any]]] = []

    def _audit(name, level="info", /, **fields):
        audits.append((name, fields))

    monkeypatch.setattr(product_service, "_fetch_runtime_templates", _templates)
    monkeypatch.setattr(agent_copy, "usable_capability_ids", _usable)
    monkeypatch.setattr(product_service, "usable_capability_ids", _usable)
    monkeypatch.setattr(agent_copy, "_copy_capability_config_via_pod", _copy)
    monkeypatch.setattr(agent_copy, "emit_audit_log", lambda *a, **k: None)
    monkeypatch.setattr(marketplace, "emit_audit_log", _audit)
    monkeypatch.setattr(
        "control_plane_backend.agent_marketplace.store.emit_audit_log", _audit
    )

    team_deps = SimpleNamespace(
        rebac=rebac,
        get_marketplace_settings_store=lambda: settings,
        get_team_metadata_store=lambda: teams,
        get_agent_marketplace_store=lambda: market,
        get_agent_instance_store=lambda: agents,
        get_kpi_writer=None,
        get_notification_service=lambda: notifications,
    )
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    RuntimeCatalogSourceConfig(
                        runtime_id="runtime-a",
                        base_url="http://runtime-a/pod/v1",
                        enabled=True,
                        ingress_prefix="/runtime/runtime-a",
                    )
                ]
            )
        ),
        team_dependencies=team_deps,
        get_agent_instance_store=lambda: agents,
        get_agent_marketplace_store=lambda: market,
        get_team_metadata_store=lambda: teams,
        get_runtime_http_client=lambda: client,
        get_kpi_writer=lambda: None,
        get_notification_service=lambda: notifications,
    )
    try:
        yield _Env(
            deps=deps,
            agents=agents,
            market=market,
            teams=teams,
            settings=settings,
            rebac=rebac,
            pod=pod,
            engine=engine,
            audits=audits,
            usable=usable,
            public_template=public_template,
            template_kwargs=template_kwargs,
            notifications=notifications,
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def _agent(
    env: _Env, agent_id: str = "agent-1", name: str = "Analyst", team=_TEAM
) -> AgentInstanceRecord:
    return await env.agents.create(
        AgentInstanceRecord(
            agent_instance_id=agent_id,
            team_id=team,
            template_id="runtime-a:rags.sample.echo",
            source_runtime_id="runtime-a",
            source_agent_id="rags.sample.echo",
            display_name=name,
            description="Answers questions",
            enabled=True,
            created_by="someone",
            tuning=ManagedAgentTuning(
                role="Analyst",
                description="Answers questions",
                values={"prompts.system": "Be precise."},
                selected_capability_ids=["demo_echo", "probe_echo"],
                capability_config={
                    "demo_echo": {
                        "schema_version": "0.1.0",
                        "config": {"uppercase": True, "library_ids": ["lib-1"]},
                    },
                    "probe_echo": {
                        "schema_version": "1.0.0",
                        "config": {"template_key": "template.pptx"},
                    },
                },
            ),
        )
    )


async def _publish(
    env: _Env,
    agent_id: str = "agent-1",
    *,
    uid: str = _EDITOR,
    expected_version: int | None = None,
    team=_TEAM,
):
    return await marketplace.publish_agent(
        user=_user(uid),
        team_id=team,
        agent_instance_id=agent_id,
        request=PublishAgentRequest(expected_version=expected_version),
        deps=env.deps,
        authorization=f"Bearer {uid}-token",
    )


async def _unpublish(
    env: _Env, version: int, *, uid: str, reason: str | None = None
) -> None:
    await marketplace.unpublish_agent(
        user=_user(uid),
        team_id=_TEAM,
        agent_instance_id="agent-1",
        request=UnpublishAgentRequest(expected_version=version, reason=reason),
        deps=env.deps,
    )


async def _card(env: _Env, uid: str, agent_id: str = "agent-1"):
    record = await env.agents.get(agent_id)
    assert record is not None
    summary = ManagedAgentInstanceSummary(
        agent_instance_id=agent_id,
        team_id=record.team_id,
        template_id=record.template_id,
        display_name=record.display_name,
        role=record.tuning.role,
        status="enabled" if record.enabled else "disabled",
        updated_at=record.updated_at,
    )
    await marketplace.attach_marketplace_states(
        user=_user(uid), team_id=record.team_id, summaries=[summary], deps=env.deps
    )
    return summary.marketplace


async def _expect(code: str, call) -> marketplace.MarketplaceError:
    with pytest.raises(marketplace.MarketplaceError) as caught:
        _ = await call
    assert caught.value.code == code
    return caught.value


async def _count(env: _Env, model) -> int:
    async with env.engine.connect() as conn:
        return (
            await conn.execute(select(func.count()).select_from(model))
        ).scalar_one()


# --- publication --------------------------------------------------------------


@pytest.mark.asyncio
async def test_editor_publishes_a_snapshot_with_reset_settings_and_files(
    env,
) -> None:
    await _agent(env)

    state = await _publish(env)

    assert (state.state, state.version, state.modified) == ("published", 1, False)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    assert entry is not None
    tuning = ManagedAgentTuning.model_validate_json(entry.tuning_json)
    assert tuning.capability_config["demo_echo"]["config"] == {
        "uppercase": True,
        "library_ids": [],
    }
    assert tuning.values == {"prompts.system": "Be precise."}
    assert [c["id"] for c in entry.capabilities] == ["demo_echo", "probe_echo"]
    assert entry.capabilities[0]["name"] == _DEMO_ENTRY.name
    files = await env.market.list_files(entry.entry_id)
    assert [(f.capability_id, f.filename, f.size) for f in files] == [
        ("probe_echo", "template.pptx", len(b"PPTX-BYTES"))
    ]
    exported = {cap: (body, auth) for cap, body, auth in env.pod.exports}
    assert exported["demo_echo"][0]["team_id"] == _TEAM
    assert exported["demo_echo"][0]["agent_instance_id"] == "agent-1"
    assert exported["demo_echo"][1] == "Bearer editor-token"
    assert ("agent.published", "agent-1") in [
        (name, fields["agent_instance_id"]) for name, fields in env.audits
    ]


@pytest.mark.asyncio
async def test_graph_agent_saved_with_an_empty_selection_publishes_its_defaults(
    env,
) -> None:
    # Older saves of a template without free selection stored `[]`; the runtime
    # still runs the included defaults, so the snapshot must list them.
    env.template_kwargs.update(
        default_capability_ids=["demo_echo"], supports_capabilities=False
    )
    record = await _agent(env)
    await env.agents.update(
        record.agent_instance_id,
        _TEAM,
        tuning=record.tuning.model_copy(
            update={"selected_capability_ids": [], "capability_config": {}}
        ),
    )

    await _publish(env)

    entry = await env.market.get_for_agent("agent-1", _TEAM)
    assert entry is not None
    assert [c["id"] for c in entry.capabilities] == ["demo_echo"]
    tuning = ManagedAgentTuning.model_validate_json(entry.tuning_json)
    assert tuning.selected_capability_ids == ["demo_echo"]
    assert [cap for cap, _body, _auth in env.pod.exports] == ["demo_echo"]


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", [_MEMBER, _ADMIN])
async def test_only_an_editor_publishes(env, uid: str) -> None:
    await _agent(env)

    with pytest.raises(AuthorizationError):
        await _publish(env, uid=uid)


@pytest.mark.asyncio
async def test_private_team_switch_off_and_non_public_type_are_refused(env) -> None:
    await _agent(env)

    env.public_template[0] = False
    await _expect("marketplace_template_not_public", _publish(env))
    env.public_template[0] = True

    await env.teams.set_marketplace_overrides(
        _TEAM, agents_publishing_enabled=False, agents_publish_quota=None
    )
    await _expect("marketplace_switch_off", _publish(env))
    await env.teams.set_marketplace_overrides(
        _TEAM, agents_publishing_enabled=None, agents_publish_quota=None
    )

    await env.teams.upsert(_TEAM, TeamMetadataPatch(visibility=TeamVisibility.PRIVATE))
    await _expect("marketplace_team_private", _publish(env))
    assert await env.market.get_for_agent("agent-1", _TEAM) is None


@pytest.mark.parametrize(
    ("flip", "code"),
    [
        ("team_override", "marketplace_switch_off"),
        ("default", "marketplace_switch_off"),
        ("private", "marketplace_team_private"),
    ],
)
@pytest.mark.asyncio
async def test_publish_rechecks_the_switch_at_write_time(
    env, monkeypatch: pytest.MonkeyPatch, flip: str, code: str
) -> None:
    # The change lands during the export, after the pre-checks: the write must
    # still refuse. Postgres row locks serialize the two; SQLite only proves the re-read.
    await _agent(env)
    build_snapshot = marketplace._build_snapshot

    async def _flip_then_build(**kwargs):
        if flip == "team_override":
            await env.teams.set_marketplace_overrides(
                _TEAM, agents_publishing_enabled=False, agents_publish_quota=None
            )
        elif flip == "default":
            await env.settings.set(
                agents_publishing_enabled=False, agents_publish_quota=2, updated_by=None
            )
        else:
            await env.teams.upsert(
                _TEAM, TeamMetadataPatch(visibility=TeamVisibility.PRIVATE)
            )
        return await build_snapshot(**kwargs)

    monkeypatch.setattr(marketplace, "_build_snapshot", _flip_then_build)

    await _expect(code, _publish(env))
    assert await env.market.get_for_agent("agent-1", _TEAM) is None


@pytest.mark.asyncio
async def test_deactivated_or_suspended_agent_is_not_published(env) -> None:
    await _agent(env)

    await env.agents.update("agent-1", _TEAM, enabled=False, updated_by=_EDITOR)
    await _expect("marketplace_agent_inactive", _publish(env))
    await env.agents.update("agent-1", _TEAM, enabled=True, updated_by=_EDITOR)

    await env.agents.set_suspension("agent-1", _TEAM, reason="capability_unavailable")
    await _expect("marketplace_agent_inactive", _publish(env))
    assert await env.market.get_for_agent("agent-1", _TEAM) is None


@pytest.mark.parametrize("flip", ["deactivate", "suspend"])
@pytest.mark.asyncio
async def test_publish_rechecks_the_agent_state_at_write_time(
    env, monkeypatch: pytest.MonkeyPatch, flip: str
) -> None:
    # Deactivated or suspended during the export: nothing removes an entry that
    # does not exist yet, so the write itself must refuse.
    await _agent(env)
    build_snapshot = marketplace._build_snapshot

    async def _flip_then_build(**kwargs):
        if flip == "deactivate":
            await env.agents.update("agent-1", _TEAM, enabled=False)
        else:
            await env.agents.set_suspension(
                "agent-1", _TEAM, reason="capability_unavailable"
            )
        return await build_snapshot(**kwargs)

    monkeypatch.setattr(marketplace, "_build_snapshot", _flip_then_build)

    await _expect("marketplace_agent_inactive", _publish(env))
    assert await env.market.get_for_agent("agent-1", _TEAM) is None


@pytest.mark.asyncio
async def test_personal_space_never_publishes(env) -> None:
    await _expect(
        "marketplace_personal_space",
        _publish(env, team=TeamId("personal")),
    )


@pytest.mark.asyncio
async def test_quota_limits_new_publications_but_not_republication(env) -> None:
    for agent_id, name in (("agent-1", "A"), ("agent-2", "B"), ("agent-3", "C")):
        await _agent(env, agent_id, name)
    await _publish(env, "agent-1")
    await _publish(env, "agent-2")

    await _expect("marketplace_quota_reached", _publish(env, "agent-3"))

    # Quota lowered below the published count: republishing is still accepted.
    await env.teams.set_marketplace_overrides(
        _TEAM, agents_publishing_enabled=None, agents_publish_quota=1
    )
    state = await _publish(env, "agent-1", expected_version=1)
    assert state.version == 2
    assert (await env.market.count_published([_TEAM]))[_TEAM] == 2


@pytest.mark.asyncio
async def test_publish_after_a_removal_counts_against_the_quota(env) -> None:
    await _agent(env, "agent-1", "A")
    await _agent(env, "agent-2", "B")
    await _agent(env, "agent-3", "C")
    first = await _publish(env, "agent-1")
    await _publish(env, "agent-2")
    await _unpublish(env, first.version, uid=_EDITOR)
    await _publish(env, "agent-3")

    await _expect(
        "marketplace_quota_reached", _publish(env, "agent-1", expected_version=2)
    )

    await env.teams.set_marketplace_overrides(
        _TEAM, agents_publishing_enabled=None, agents_publish_quota=3
    )
    before = await env.market.get_for_agent("agent-1", _TEAM)
    state = await _publish(env, "agent-1", expected_version=2)
    after = await env.market.get_for_agent("agent-1", _TEAM)
    assert state.state == "published" and state.version == 3
    assert before is not None and after is not None
    assert after.first_published_at == before.first_published_at


@pytest.mark.asyncio
async def test_failed_republication_keeps_the_previous_snapshot(env) -> None:
    await _agent(env)
    await _publish(env)
    await env.agents.update("agent-1", _TEAM, description="Changed", updated_by=_EDITOR)
    before = await env.market.get_for_agent("agent-1", _TEAM)

    env.pod.export_status = {"probe_echo": 404}
    error = await _expect(
        "marketplace_capability_not_exportable", _publish(env, expected_version=1)
    )
    assert (error.http_status, error.capability_id) == (422, "probe_echo")
    env.pod.export_status = {"demo_echo": 422}
    error = await _expect(
        "marketplace_capability_not_exportable", _publish(env, expected_version=1)
    )
    assert error.http_status == 422
    env.pod.export_status = {}
    env.pod.unreachable = True
    error = await _expect(
        "marketplace_runtime_unavailable", _publish(env, expected_version=1)
    )
    assert error.http_status == 503

    after = await env.market.get_for_agent("agent-1", _TEAM)
    assert after == before
    assert len(await env.market.list_files(after.entry_id)) == 1
    card = await _card(env, _EDITOR)
    assert card is not None and card.modified is True


@pytest.mark.asyncio
async def test_stale_or_missing_version_answers_conflict(env) -> None:
    await _agent(env)
    await _publish(env)

    await _expect("marketplace_version_conflict", _publish(env))
    await _publish(env, expected_version=1)
    # Double republication from the same card version: the second one loses.
    await _expect("marketplace_version_conflict", _publish(env, expected_version=1))


@pytest.mark.asyncio
async def test_republish_and_remove_from_the_same_version(env) -> None:
    await _agent(env)
    await _publish(env)

    await _publish(env, expected_version=1)
    await _expect("marketplace_version_conflict", _unpublish(env, 1, uid=_EDITOR))
    await _unpublish(env, 2, uid=_ADMIN)
    await _expect("marketplace_version_conflict", _publish(env, expected_version=2))


# --- modified state -------------------------------------------------------------


@pytest.mark.asyncio
async def test_modified_follows_real_changes_only(env) -> None:
    await _agent(env)
    await _publish(env)
    record = await env.agents.get("agent-1")
    assert record is not None

    # A save that changes nothing keeps updated_at.
    await env.agents.update(
        "agent-1",
        _TEAM,
        display_name=record.display_name,
        description=record.description,
        tuning=record.tuning,
        updated_by=_EDITOR,
    )
    assert (await env.agents.get("agent-1")).updated_at == record.updated_at
    assert (await _card(env, _EDITOR)).modified is False

    # Like and hide never touch the agent row.
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    await env.market.set_like(entry.entry_id, _MEMBER, liked=True)
    assert (await env.agents.get("agent-1")).updated_at == record.updated_at

    await env.agents.update(
        "agent-1",
        _TEAM,
        tuning=record.tuning.model_copy(update={"values": {"prompts.system": "New"}}),
        updated_by=_EDITOR,
    )
    card = await _card(env, _EDITOR)
    assert card.modified is True and card.like_count == 1
    unchanged = await env.market.get_for_agent("agent-1", _TEAM)
    assert unchanged.tuning_json == entry.tuning_json

    await _publish(env, expected_version=1)
    assert (await _card(env, _EDITOR)).modified is False


@pytest.mark.asyncio
async def test_a_save_during_publication_still_shows_modified(env) -> None:
    await _agent(env)

    async def save_meanwhile() -> None:
        env.pod.on_export = None
        await env.agents.update(
            "agent-1", _TEAM, description="Saved during publish", updated_by=_EDITOR
        )

    env.pod.on_export = save_meanwhile
    await _publish(env)

    assert (await _card(env, _EDITOR)).modified is True


# --- removal ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", [_EDITOR, _ADMIN])
async def test_removal_by_the_team_leaves_no_removed_state(env, uid: str) -> None:
    await _agent(env)
    await _publish(env)

    await _unpublish(env, 1, uid=uid)

    card = await _card(env, _EDITOR)
    assert card.state == "dismissed"
    assert (await env.market.list_published()) == []
    assert (await env.agents.get("agent-1")).enabled is True
    assert await _count(env, AgentMarketplaceEntryFileRow) == 0


@pytest.mark.asyncio
async def test_platform_admin_removes_with_a_reason(env) -> None:
    await _agent(env)
    await _publish(env)

    await _unpublish(env, 1, uid=_PLATFORM, reason="Outdated instructions")

    card = await _card(env, _EDITOR)
    assert card.state == "removed"
    assert card.removed_reason == "removed_by_platform_admin"
    assert card.removed_message == "Outdated instructions"
    assert ("agent.unpublished", "removed_by_platform_admin") in [
        (name, fields.get("reason")) for name, fields in env.audits
    ]


@pytest.mark.asyncio
async def test_member_cannot_remove_and_only_admins_give_reasons(env) -> None:
    await _agent(env)
    await _publish(env)

    await _expect("marketplace_forbidden", _unpublish(env, 1, uid=_MEMBER))
    await _expect(
        "marketplace_forbidden", _unpublish(env, 1, uid=_EDITOR, reason="Because")
    )
    assert len(await env.market.list_published()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", [_EDITOR, _ADMIN])
async def test_hide_is_for_editors_and_team_admin(env, uid: str) -> None:
    await _agent(env)
    await _publish(env)
    await env.agents.set_suspension("agent-1", _TEAM, reason="capability_unavailable")

    card = await _card(env, _EDITOR)
    assert (card.state, card.removed_reason) == ("removed", "suspended")
    assert card.removed_at is not None
    with pytest.raises(AuthorizationError):
        await marketplace.dismiss_marketplace_removal(
            user=_user(_MEMBER),
            team_id=_TEAM,
            agent_instance_id="agent-1",
            deps=env.deps,
        )
    await marketplace.dismiss_marketplace_removal(
        user=_user(uid), team_id=_TEAM, agent_instance_id="agent-1", deps=env.deps
    )
    assert (await _card(env, _EDITOR)).state == "dismissed"


@pytest.mark.asyncio
async def test_deactivation_removes_and_reactivation_does_not_republish(env) -> None:
    await _agent(env)
    await _publish(env)

    await env.agents.update("agent-1", _TEAM, enabled=False, updated_by=_EDITOR)
    assert (await _card(env, _EDITOR)).removed_reason == "deactivated"

    await env.agents.update("agent-1", _TEAM, enabled=True, updated_by=_EDITOR)
    assert (await _card(env, _EDITOR)).state == "removed"
    assert await env.market.list_published() == []


@pytest.mark.asyncio
async def test_team_made_private_removes_its_entries(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.teams import service as team_service
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    await _agent(env)
    await _publish(env)

    async def _validated(user, team_id, rebac, permissions, deps):
        return await env.teams.get_by_team_id(team_id), None

    async def _projection(user, metadata, deps, token):
        return metadata

    monkeypatch.setattr(team_service, "_validate_team_and_check_permission", _validated)
    monkeypatch.setattr(team_service, "_build_team_with_permissions", _projection)
    await team_service.update_team(
        _user(_ADMIN),
        _TEAM,
        UpdateTeamRequest(visibility=TeamVisibility.PRIVATE),
        env.deps.team_dependencies,
    )

    assert (await _card(env, _EDITOR)).removed_reason == "team_private"


@pytest.mark.asyncio
async def test_team_made_private_removes_its_entries_even_if_rebac_fails(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.teams import service as team_service
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    await _agent(env)
    await _publish(env)

    async def _validated(user, team_id, rebac, permissions, deps):
        return await env.teams.get_by_team_id(team_id), None

    async def _revoke_fails(team_ids, **_):
        raise RuntimeError("openfga down")

    monkeypatch.setattr(team_service, "_validate_team_and_check_permission", _validated)
    monkeypatch.setattr(env.rebac, "revoke_team_public_relations", _revoke_fails)
    with pytest.raises(RuntimeError):
        await team_service.update_team(
            _user(_ADMIN),
            _TEAM,
            UpdateTeamRequest(visibility=TeamVisibility.PRIVATE),
            env.deps.team_dependencies,
        )

    assert (await env.teams.get_by_team_id(_TEAM)).visibility == TeamVisibility.PRIVATE
    assert await env.market.list_published() == []
    assert ("agent.unpublished", "team_private") in [
        (name, fields.get("reason")) for name, fields in env.audits
    ]


@pytest.mark.asyncio
async def test_private_team_write_rolls_back_if_entry_removal_fails(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.teams import service as team_service
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    await _agent(env)
    await _publish(env)

    async def _validated(user, team_id, rebac, permissions, deps):
        return await env.teams.get_by_team_id(team_id), None

    async def _removal_fails(*args, **kwargs):
        raise RuntimeError("removal failed")

    monkeypatch.setattr(team_service, "_validate_team_and_check_permission", _validated)
    monkeypatch.setattr(env.market, "remove_team_entries", _removal_fails)
    with pytest.raises(RuntimeError, match="removal failed"):
        await team_service.update_team(
            _user(_ADMIN),
            _TEAM,
            UpdateTeamRequest(visibility=TeamVisibility.PRIVATE),
            env.deps.team_dependencies,
        )

    assert (await env.teams.get_by_team_id(_TEAM)).visibility == TeamVisibility.PUBLIC
    assert len(await env.market.list_published()) == 1


@pytest.mark.asyncio
async def test_switch_off_removes_entries_and_counts_them(env) -> None:
    from control_plane_backend.marketplace_settings import service as settings_service
    from control_plane_backend.marketplace_settings.schemas import (
        SetTeamMarketplaceSettingsRequest,
    )

    await _agent(env)
    await _publish(env)

    preview = await settings_service.preview_team_change(
        user=_user(_PLATFORM),
        team_id=_TEAM,
        agents_publishing_enabled=False,
        deps=env.deps.team_dependencies,
    )
    assert preview.removed_published_agents == 1

    result = await settings_service.set_team_marketplace_settings(
        user=_user(_PLATFORM),
        team_id=_TEAM,
        request=SetTeamMarketplaceSettingsRequest(
            agents_publishing_enabled=False, agents_publish_quota=None
        ),
        deps=env.deps.team_dependencies,
    )

    assert result.impact.removed_published_agents == 1
    assert (await _card(env, _EDITOR)).removed_reason == "switch_off"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["default", "team"])
async def test_switch_off_write_rolls_back_if_entry_removal_fails(
    env, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    from control_plane_backend.marketplace_settings import service as settings_service
    from control_plane_backend.marketplace_settings.schemas import (
        SetAgentsMarketplaceDefaultRequest,
        SetTeamMarketplaceSettingsRequest,
    )

    await _agent(env)
    await _publish(env)

    async def _removal_fails(*args, **kwargs):
        raise RuntimeError("removal failed")

    monkeypatch.setattr(env.market, "remove_team_entries", _removal_fails)
    with pytest.raises(RuntimeError, match="removal failed"):
        if scope == "default":
            await settings_service.set_marketplace_default(
                user=_user(_PLATFORM),
                request=SetAgentsMarketplaceDefaultRequest(
                    agents_publishing_enabled=False, agents_publish_quota=2
                ),
                deps=env.deps.team_dependencies,
            )
        else:
            await settings_service.set_team_marketplace_settings(
                user=_user(_PLATFORM),
                team_id=_TEAM,
                request=SetTeamMarketplaceSettingsRequest(
                    agents_publishing_enabled=False, agents_publish_quota=None
                ),
                deps=env.deps.team_dependencies,
            )

    assert (await env.settings.get()).agents_publishing_enabled is True
    assert (await env.teams.get_by_team_id(_TEAM)).agents_publishing_enabled is None
    assert len(await env.market.list_published()) == 1


@pytest.mark.asyncio
async def test_counters_survive_removal_and_republication(env) -> None:
    await _agent(env)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    for uid in ("u1", "u2"):
        await env.market.set_like(entry.entry_id, uid, liked=True)
    await env.market.record_import(
        entry_id=entry.entry_id,
        target_team_id=_OTHER,
        user_id="u1",
        agent_instance_id="agent-1",
        version=1,
    )

    await _unpublish(env, 1, uid=_EDITOR)
    await _publish(env, expected_version=2)

    card = await _card(env, _EDITOR)
    assert (card.like_count, card.import_count) == (2, 1)


# --- card state per role ------------------------------------------------------


@pytest.mark.asyncio
async def test_member_sees_only_published(env) -> None:
    await _agent(env)
    await _publish(env)
    await env.agents.update("agent-1", _TEAM, description="Changed", updated_by=_EDITOR)

    member = await _card(env, _MEMBER)
    assert (member.state, member.modified) == ("published", False)
    assert (await _card(env, _ADMIN)).modified is True

    await env.agents.set_suspension("agent-1", _TEAM, reason="capability_unavailable")
    assert await _card(env, _MEMBER) is None
    assert (await _card(env, _EDITOR)).state == "removed"


# --- likes, listing, detail -----------------------------------------------------


@pytest.mark.asyncio
async def test_likes_toggle_are_idempotent_and_keep_history(env) -> None:
    await _agent(env)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    like = marketplace.set_marketplace_like

    summary = await like(
        user=_user(_EDITOR), entry_id=entry.entry_id, liked=True, deps=env.deps
    )
    assert (summary.like_count, summary.liked_by_me) == (1, True)
    summary = await like(
        user=_user(_EDITOR), entry_id=entry.entry_id, liked=True, deps=env.deps
    )
    assert summary.like_count == 1
    summary = await like(
        user=_user(_EDITOR), entry_id=entry.entry_id, liked=False, deps=env.deps
    )
    assert (summary.like_count, summary.liked_by_me) == (0, False)
    await like(user=_user(_EDITOR), entry_id=entry.entry_id, liked=True, deps=env.deps)
    assert await _count(env, AgentMarketplaceLikeRow) == 2

    await _unpublish(env, 1, uid=_EDITOR)
    await _expect(
        "marketplace_entry_not_found",
        like(user=_user(_MEMBER), entry_id=entry.entry_id, liked=True, deps=env.deps),
    )


@pytest.mark.asyncio
async def test_likes_since_the_update_and_metadata_only_files(env) -> None:
    await _agent(env)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    for uid in ("u1", "u2", "u3", "u4"):
        await env.market.set_like(entry.entry_id, uid, liked=True)
    await _publish(env, expected_version=1)
    await env.market.set_like(entry.entry_id, "u5", liked=True)

    detail = await marketplace.get_marketplace_agent(
        user=_user("u5"), entry_id=entry.entry_id, deps=env.deps
    )

    assert (detail.like_count, detail.likes_since_update) == (5, 1)
    assert detail.liked_by_me is True
    assert detail.team_name == "Alpha"
    assert detail.agent_instance_id == "agent-1"
    assert detail.tuning_field_values == {"prompts.system": "Be precise."}
    assert [f.model_dump() for f in detail.files] == [
        {"capability_id": "probe_echo", "filename": "template.pptx", "size": 10}
    ]
    assert "content" not in json.dumps(detail.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_secret_values_never_reach_the_detail_or_an_import(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One field is secret on the instance, the other only on the template.
    record = await _agent(env)
    await env.agents.update(
        "agent-1",
        _TEAM,
        tuning=record.tuning.model_copy(
            update={
                "fields": [
                    ManagedAgentFieldSpec(key="api.key", type="secret", title="Key")
                ],
                "values": {
                    **record.tuning.values,
                    "api.key": "s3cr3t-instance",
                    "api.token": "s3cr3t-template",
                },
            }
        ),
    )
    template = _template_payload()
    template.default_tuning.fields = [
        ManagedAgentFieldSpec(key="api.token", type="secret", title="Token")
    ]
    monkeypatch.setattr(
        product_service,
        "_fetch_runtime_templates",
        lambda *_a, **_k: _async([template]),
    )
    monkeypatch.setattr(
        agent_copy, "usable_capability_ids", lambda _r, _t: _async(None)
    )
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)

    detail = await marketplace.get_marketplace_agent(
        user=_user(_OUTSIDER), entry_id=entry.entry_id, deps=env.deps
    )
    [imported] = await marketplace.import_marketplace_agent(
        user=_user(_OUTSIDER),
        entry_id=entry.entry_id,
        target_team_ids=[_OTHER],
        deps=env.deps,
        authorization="Bearer outsider-token",
        require_editor=await _require_editor_for(env, _OUTSIDER),
    )

    assert detail.tuning_field_values == {"prompts.system": "Be precise."}
    assert "s3cr3t" not in json.dumps(detail.model_dump(mode="json"))
    assert "s3cr3t" not in entry.tuning_json
    copy = await env.agents.get(imported.agent.agent_instance_id)
    assert copy.tuning.values == {"prompts.system": "Be precise."}


@pytest.mark.asyncio
async def test_listing_order_filters_and_live_team_name(env) -> None:
    await _agent(env, "agent-1", "Analyst")
    await _agent(env, "agent-2", "Writer")
    await _agent(env, "agent-9", "Beta helper", team=_OTHER)
    await _publish(env, "agent-1")
    await _publish(env, "agent-2")
    await _publish(env, "agent-9", team=_OTHER)
    await _publish(env, "agent-1", expected_version=1)
    await env.agents.set_suspension("agent-2", _TEAM, reason="capability_unavailable")
    await env.teams.upsert(_OTHER, TeamMetadataPatch(name="Beta Renamed"))

    listed = await marketplace.list_marketplace_agents(
        user=_user(_OUTSIDER), q=None, team_id=None, deps=env.deps
    )
    assert [(a.display_name, a.team_name) for a in listed] == [
        ("Beta helper", "Beta Renamed"),
        ("Analyst", "Alpha"),
    ]
    assert [a.role for a in listed] == ["Analyst", "Analyst"]
    by_q = await marketplace.list_marketplace_agents(
        user=_user(_OUTSIDER), q="analy", team_id=None, deps=env.deps
    )
    assert [a.display_name for a in by_q] == ["Analyst"]
    by_team_name = await marketplace.list_marketplace_agents(
        user=_user(_OUTSIDER), q="beta renamed", team_id=None, deps=env.deps
    )
    assert [a.display_name for a in by_team_name] == ["Beta helper"]
    by_team = await marketplace.list_marketplace_agents(
        user=_user(_OUTSIDER), q=None, team_id=_OTHER, deps=env.deps
    )
    assert [a.display_name for a in by_team] == ["Beta helper"]
    assert (
        await marketplace.list_marketplace_agents(
            user=_user(_OUTSIDER), q="nothing like it", team_id=None, deps=env.deps
        )
        == []
    )


# --- import ---------------------------------------------------------------------


async def _require_editor_for(env: _Env, uid: str):
    async def require_editor(team_id: TeamId) -> TeamId:
        if str(team_id) == "personal":
            return TeamId(f"personal-{uid}")
        if TeamPermission.CAN_UPDATE_AGENTS not in env.rebac.perms.get(
            str(team_id), {}
        ).get(uid, set()):
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Not an editor.")
        return team_id

    return require_editor


@pytest.mark.asyncio
async def test_import_targets_exclude_the_publishing_team(env) -> None:
    await _agent(env)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    env.usable = {_OTHER: {_TEMPLATE_CAP, "demo_echo"}}
    env.deps.team_dependencies.rebac = env.rebac

    targets = await marketplace.list_marketplace_import_targets(
        user=_user(_EDITOR), entry_id=entry.entry_id, deps=env.deps
    )

    by_team = {t.team_id: t for t in targets}
    assert _TEAM not in by_team
    assert set(by_team) == {"personal-editor", _OTHER, _THIRD}


@pytest.mark.asyncio
async def test_an_agent_type_made_internal_is_imported_by_platform_admins_only(
    env,
) -> None:
    await _agent(env)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    env.public_template[0] = False

    await _expect(
        "marketplace_template_not_public",
        marketplace.list_marketplace_import_targets(
            user=_user(_OUTSIDER), entry_id=entry.entry_id, deps=env.deps
        ),
    )
    await _expect(
        "marketplace_template_not_public",
        marketplace.import_marketplace_agent(
            user=_user(_OUTSIDER),
            entry_id=entry.entry_id,
            target_team_ids=[_OTHER],
            deps=env.deps,
            authorization="Bearer outsider-token",
            require_editor=await _require_editor_for(env, _OUTSIDER),
        ),
    )
    assert env.pod.copies == []
    assert await _count(env, AgentMarketplaceImportRow) == 0

    targets = await marketplace.list_marketplace_import_targets(
        user=_user(_PLATFORM), entry_id=entry.entry_id, deps=env.deps
    )
    assert [t.team_id for t in targets] == ["personal-platform-admin"]


@pytest.mark.asyncio
async def test_import_copies_the_snapshot_per_destination(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _agent(env)
    await _agent(env, "beta-1", "Analyst", team=_OTHER)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    usable = {
        _OTHER: {_TEMPLATE_CAP, "demo_echo", "probe_echo"},
        _THIRD: {"demo_echo"},
        "personal-editor": {_TEMPLATE_CAP, "demo_echo"},
    }
    monkeypatch.setattr(
        agent_copy, "usable_capability_ids", lambda _r, t: _async(usable.get(str(t)))
    )
    # The source agent changes after publication: the import must not see it.
    await env.agents.update(
        "agent-1", _TEAM, description="Live only", updated_by=_EDITOR
    )

    results = await marketplace.import_marketplace_agent(
        user=_user(_EDITOR),
        entry_id=entry.entry_id,
        target_team_ids=[_OTHER, _THIRD, _TEAM, "personal"],
        deps=env.deps,
        authorization="Bearer editor-token",
        require_editor=await _require_editor_for(env, _EDITOR),
        locale="fr",
    )

    by_team = {r.team_id: r for r in results}
    assert by_team[_OTHER].agent.display_name == "Analyst (copie 1)"
    assert by_team[_OTHER].agent.description == "Answers questions"
    assert by_team["personal-editor"].agent.display_name == "Analyst"
    assert [c.id for c in by_team["personal-editor"].dropped_capabilities] == [
        "probe_echo"
    ]
    assert by_team[_THIRD].error is not None and by_team[_THIRD].agent is None
    assert by_team[_TEAM].error_code == "marketplace_publishing_team"
    copied = [request for cap, request in env.pod.copies if cap == "probe_echo"]
    assert copied and all(
        r.source_agent_instance_id == entry.entry_id
        and r.asset_files == {"template.pptx": base64.b64encode(b"PPTX-BYTES").decode()}
        for r in copied
    )
    demo = [request for cap, request in env.pod.copies if cap == "demo_echo"]
    assert all(r.config.config["library_ids"] == [] for r in demo)
    assert await _count(env, AgentMarketplaceImportRow) == 2

    summary = (
        await marketplace.list_marketplace_agents(
            user=_user(_OUTSIDER), q=None, team_id=None, deps=env.deps
        )
    )[0]
    assert summary.import_count == 2

    # The imported agent can be deleted; its import row stays.
    await env.agents.delete(by_team[_OTHER].agent.agent_instance_id, _OTHER)
    async with env.engine.connect() as conn:
        kept = (
            (await conn.execute(select(AgentMarketplaceImportRow.agent_instance_id)))
            .scalars()
            .all()
        )
    assert sorted(kept, key=str) == sorted(
        [None, by_team["personal-editor"].agent.agent_instance_id], key=str
    )


async def _async(value):
    return value


# --- cascade and team deletion ---------------------------------------------------


@pytest.mark.asyncio
async def test_agent_deletion_cascades_entry_likes_and_imports(env) -> None:
    await _agent(env)
    await _publish(env)
    entry = await env.market.get_for_agent("agent-1", _TEAM)
    await env.market.set_like(entry.entry_id, "u1", liked=True)
    await env.market.record_import(
        entry_id=entry.entry_id,
        target_team_id=_OTHER,
        user_id="u1",
        agent_instance_id="agent-1",
        version=1,
    )
    env.audits.clear()

    await env.agents.delete("agent-1", _TEAM, actor_uid="u1")

    assert [
        (name, fields["agent_instance_id"], fields["reason"], fields["user_id"])
        for name, fields in env.audits
    ] == [("agent.unpublished", "agent-1", "deleted", "u1")]
    for model in (
        AgentMarketplaceEntryRow,
        AgentMarketplaceEntryFileRow,
        AgentMarketplaceLikeRow,
        AgentMarketplaceImportRow,
    ):
        assert await _count(env, model) == 0


@pytest.mark.asyncio
async def test_team_deletion_deletes_its_agents_and_entries(env) -> None:
    from control_plane_backend.teams.service import delete_team

    await _agent(env)
    await _agent(env, "agent-2", "Second")
    await _agent(env, "beta-1", "Other", team=_OTHER)
    await _publish(env)
    env.rebac.platform_admins.add(_PLATFORM)
    kpis: list[tuple[str, dict[str, str]]] = []
    env.deps.team_dependencies.get_kpi_writer = lambda: SimpleNamespace(
        count=lambda name, dims, actor: kpis.append((name, dims))
    )
    env.audits.clear()

    await delete_team(_user(_PLATFORM), _TEAM, env.deps.team_dependencies)

    assert await env.agents.list_by_team(_TEAM) == []
    assert len(await env.agents.list_by_team(_OTHER)) == 1
    assert await _count(env, AgentMarketplaceEntryRow) == 0
    assert sorted(kpis, key=lambda k: k[1]["agent_instance_id"]) == [
        ("agent.deleted_total", {"team_id": _TEAM, "agent_instance_id": "agent-1"}),
        ("agent.deleted_total", {"team_id": _TEAM, "agent_instance_id": "agent-2"}),
    ]
    assert [
        (name, fields["agent_instance_id"], fields["reason"])
        for name, fields in env.audits
    ] == [("agent.unpublished", "agent-1", "team_deleted")]


# --- capability revoke preview and routes ----------------------------------------


@pytest.mark.asyncio
async def test_capability_revoke_preview_counts_published_agents(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.capabilities import service as capability_service
    from control_plane_backend.capabilities.impact import (
        CapabilityImpact,
        ImpactedInstance,
    )

    await _agent(env, "agent-1", "A")
    await _agent(env, "agent-2", "B")
    await _publish(env, "agent-1")

    async def _allowed(*_a, **_k) -> None:
        return None

    async def _catalog(_deps):
        return []

    async def _impact(_deps, *, capability_id, team_id=None, store=None):
        return CapabilityImpact(
            suspended_instances=2,
            instances=[
                ImpactedInstance(agent_instance_id=a, team_id=_TEAM, display_name=a)
                for a in ("agent-1", "agent-2")
            ],
        )

    monkeypatch.setattr(capability_service, "_require_can_manage", _allowed)
    monkeypatch.setattr(capability_service, "aggregate_capability_catalog", _catalog)
    monkeypatch.setattr(
        capability_service, "_catalog_entry_for_revoke", lambda _c, _id: None
    )
    monkeypatch.setattr(
        capability_service, "is_projected_product_object", lambda _e: False
    )
    monkeypatch.setattr(capability_service, "preview_revoke_impact", _impact)

    preview = await capability_service.preview_capability_revoke(
        user=_user(_PLATFORM), capability_id="demo_echo", team_id=_TEAM, deps=env.deps
    )

    assert (preview.suspended_instances, preview.published_instances) == (2, 1)


@pytest.mark.asyncio
async def test_routes_answer_with_the_marketplace_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.main import create_app
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        refused = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/agent-1/publish",
            headers={"Authorization": "Bearer user-token"},
            json={},
        )
        listed = await client.get(
            "/control-plane/v1/marketplace/agents",
            headers={"Authorization": "Bearer user-token"},
        )
        missing = await client.get(
            "/control-plane/v1/marketplace/agents/unknown",
            headers={"Authorization": "Bearer user-token"},
        )

    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "marketplace_personal_space"
    assert (listed.status_code, listed.json()) == (200, [])
    assert missing.status_code == 404


# --- publisher notifications --------------------------------------------------------

_EDITOR_2 = "editor-2"


async def _save(env: _Env, uid: str, description: str, agent_id: str = "agent-1"):
    from control_plane_backend.product.schemas import UpdateAgentInstanceRequest

    return await product_service.update_agent_instance(
        team_id=_TEAM,
        agent_instance_id=agent_id,
        request=UpdateAgentInstanceRequest(description=description),
        deps=env.deps,
        user=_user(uid),
    )


async def _inbox(env: _Env, uid: str):
    page = await env.notifications.list_page(_user(uid), limit=50, before=None)
    return page.items


def _removal(item: Any) -> AgentMarketplaceRemovedPayload:
    assert isinstance(item, AgentMarketplaceRemovedNotification)
    return item.payload


@pytest_asyncio.fixture
async def editors(env, monkeypatch: pytest.MonkeyPatch):
    async def _usable(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(product_service, "can_team_use_capability", _usable)
    env.rebac.perms[_TEAM][_EDITOR_2] = set(_EDITOR_PERMS)
    return env


@pytest.mark.asyncio
async def test_publish_and_republish_record_the_publisher(editors) -> None:
    env = editors
    await _agent(env)
    await _publish(env)
    assert (await env.market.get_for_agent("agent-1", _TEAM)).published_by == _EDITOR

    await _publish(env, uid=_EDITOR_2, expected_version=1)
    assert (await env.market.get_for_agent("agent-1", _TEAM)).published_by == _EDITOR_2


@pytest.mark.asyncio
async def test_another_editors_save_asks_the_publisher_to_republish_once(
    editors,
) -> None:
    env = editors
    await _agent(env)
    await _publish(env)

    await _save(env, _EDITOR_2, "First change")
    await _save(env, _EDITOR_2, "Second change")

    [notification] = await _inbox(env, _EDITOR)
    assert notification.type == "agent.republish_needed"
    assert notification.payload.editor_name == _EDITOR_2
    assert notification.payload.agent_name == "Analyst"
    assert notification.payload.team_name == "Alpha"
    assert (await env.notifications.summary(_user(_EDITOR))).unseen_count == 1
    assert await _inbox(env, _EDITOR_2) == []


@pytest.mark.asyncio
async def test_no_republish_request_for_the_publisher_a_no_op_or_a_legacy_entry(
    editors,
) -> None:
    env = editors
    await _agent(env)
    await _publish(env)

    await _save(env, _EDITOR, "The publisher's own change")
    await _save(env, _EDITOR_2, "The publisher's own change")  # nothing changes
    assert await _inbox(env, _EDITOR) == []

    async with env.engine.begin() as conn:
        await conn.execute(update(AgentMarketplaceEntryRow).values(published_by=None))
    await _save(env, _EDITOR_2, "A change to a legacy entry")
    assert await _inbox(env, _EDITOR) == []


@pytest.mark.asyncio
async def test_a_failing_notification_store_never_fails_the_save(
    editors, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = editors
    await _agent(env)
    await _publish(env)

    async def _down(*_args, **_kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(env.notifications.store, "upsert", _down)

    saved = await _save(env, _EDITOR_2, "Saved anyway")

    assert saved is not None and saved.description == "Saved anyway"


@pytest.mark.asyncio
async def test_republishing_resolves_the_request(editors) -> None:
    env = editors
    await _agent(env)
    await _publish(env)
    await _save(env, _EDITOR_2, "A change")
    await _publish(env, uid=_EDITOR_2, expected_version=1)

    [handled] = await _inbox(env, _EDITOR)
    assert handled.handled_by_name == _EDITOR_2
    assert handled.handled_outcome == "republished"

    # The new publisher is now the one asked, and their own republish clears it.
    await _save(env, _EDITOR, "Another change")
    assert len(await _inbox(env, _EDITOR_2)) == 1
    await _publish(env, uid=_EDITOR_2, expected_version=2)
    assert await _inbox(env, _EDITOR_2) == []


@pytest.mark.asyncio
async def test_platform_admin_removal_tells_the_publisher_with_the_reason(
    editors,
) -> None:
    env = editors
    await _agent(env)
    await _publish(env)
    await _save(env, _EDITOR_2, "A change")

    await _unpublish(env, 1, uid=_PLATFORM, reason="Duplicate entry")

    by_type = {item.type: item for item in await _inbox(env, _EDITOR)}
    removed = _removal(by_type["agent.marketplace_removed"])
    assert removed.reason == "removed_by_platform_admin"
    assert removed.message == "Duplicate entry"
    assert removed.team_name == "Alpha"
    assert by_type["agent.republish_needed"].handled_outcome == "removed"


@pytest.mark.asyncio
async def test_removal_by_the_team_notifies_nobody(editors) -> None:
    env = editors
    await _agent(env)
    await _publish(env)

    await _unpublish(env, 1, uid=_EDITOR_2)

    assert await _inbox(env, _EDITOR) == []


@pytest.mark.asyncio
async def test_automatic_removal_tells_the_publisher(
    editors, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.teams import service as team_service
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    env = editors
    await _agent(env)
    await _publish(env)

    async def _validated(user, team_id, rebac, permissions, deps):
        return await env.teams.get_by_team_id(team_id), None

    async def _projection(user, metadata, deps, token):
        return metadata

    monkeypatch.setattr(team_service, "_validate_team_and_check_permission", _validated)
    monkeypatch.setattr(team_service, "_build_team_with_permissions", _projection)
    await team_service.update_team(
        _user(_ADMIN),
        _TEAM,
        UpdateTeamRequest(visibility=TeamVisibility.PRIVATE),
        env.deps.team_dependencies,
    )

    [removed] = await _inbox(env, _EDITOR)
    assert _removal(removed).reason == "team_private"


@pytest.mark.asyncio
async def test_bulk_switch_off_emits_one_row_per_entry_in_one_insert(
    editors, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.marketplace_settings import service as settings_service
    from control_plane_backend.marketplace_settings.schemas import (
        SetTeamMarketplaceSettingsRequest,
    )

    env = editors
    await _agent(env)
    await _agent(env, "agent-2", name="Writer")
    await _publish(env)
    await _publish(env, "agent-2", uid=_EDITOR_2)
    inserts: list[int] = []
    upsert = env.notifications.store.upsert

    async def _counting(drafts):
        inserts.append(len(drafts))
        return await upsert(drafts)

    monkeypatch.setattr(env.notifications.store, "upsert", _counting)

    await settings_service.set_team_marketplace_settings(
        user=_user(_PLATFORM),
        team_id=_TEAM,
        request=SetTeamMarketplaceSettingsRequest(
            agents_publishing_enabled=False, agents_publish_quota=None
        ),
        deps=env.deps.team_dependencies,
    )

    assert inserts == [2]
    for uid in (_EDITOR, _EDITOR_2):
        [removed] = await _inbox(env, uid)
        assert _removal(removed).reason == "switch_off"


@pytest.mark.asyncio
async def test_deactivation_by_another_editor_tells_the_publisher(editors) -> None:
    env = editors
    await _agent(env)
    await _publish(env)

    await env.agents.update("agent-1", _TEAM, enabled=False, updated_by=_EDITOR_2)
    await env.agents.update("agent-1", _TEAM, enabled=True, updated_by=_EDITOR)
    await _publish(env, expected_version=2)
    await env.agents.update("agent-1", _TEAM, enabled=False, updated_by=_EDITOR)

    [removed] = await _inbox(env, _EDITOR)
    assert _removal(removed).reason == "deactivated"


@pytest.mark.asyncio
async def test_team_deletion_deletes_the_teams_notifications(editors) -> None:
    from control_plane_backend.teams.service import delete_team

    env = editors
    await _agent(env)
    await _publish(env)
    await _save(env, _EDITOR_2, "A change")
    assert len(await _inbox(env, _EDITOR)) == 1

    await delete_team(_user(_PLATFORM), _TEAM, env.deps.team_dependencies)

    assert await _inbox(env, _EDITOR) == []
