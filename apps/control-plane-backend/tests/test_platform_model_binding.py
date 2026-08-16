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

"""Platform-wide model binding override — control-plane side.

Chat-only: control-plane can assert one authoritative concrete
`(provider, name, settings)` binding for the `chat` capability that
overrides whatever every pod would otherwise resolve locally (the
runtime-side bypass and precedence were built and tested in
fred-sdk/fred-runtime; this suite covers only persistence, the admin API,
and the trusted per-turn resolution consumed by `get_runtime_binding_for_team`).

Covers:
- the store's CRUD (absent row = unset, set/get round-trip, delete) — chat
  only, no capability argument exists on the store at all; `get()` carries
  the canonical `ModelBinding` end to end, no split provider/name/settings
  triple or open `dict[str, object]` anywhere in the store boundary
- the database CHECK constraint: no row other than `model_capability="chat"`
  can be inserted, even bypassing the store's own API — and a row that
  bypasses the store's own `set()` entirely (malformed provider, unknown
  settings key) fails closed on `get()`, not just at write time
- the service's org-admin gate (`organization_authz.require_manage_any`,
  shared with `capabilities/service.py`)
- `resolve_platform_chat_model_binding`: the trusted, no-client-authz
  per-turn entrypoint threaded into `ManagedAgentRuntimeBinding.
  platform_chat_model_binding` — resolved fresh on the runtime's own
  per-turn `GET .../runtime` lookup, never a client-forwarded session-prep
  snapshot
- the API boundary: an unsupported `provider`, a wrong-typed or
  out-of-range settings value, a provider missing one of its own required
  settings (e.g. `azure-openai` without `azure_openai_api_version`), and
  every forbidden settings shape (credential-designated keys, arbitrary
  headers/cookies/auth objects, unknown keys, URL userinfo, malformed nested
  values) are all rejected with 422 before persistence, every supported
  provider's minimal valid settings are accepted, and ordinary settings
  round-trip without type coercion — each proven at the actual HTTP layer,
  not just fred-sdk unit level
- the removed `{model_capability}` path segment: the old per-capability
  routes no longer exist at all
- `ExecutionPreparation` no longer carries a platform-binding field at all,
  and the `GET .../runtime` endpoint carries the trusted one fresh per call
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy import service as routing_policy_service
from control_plane_backend.routing_policy.schemas import PlatformModelBinding
from control_plane_backend.routing_policy.store import (
    PlatformModelBindingStore,
    StoredPlatformModelBinding,
)
from fred_core import AuthorizationError, KeycloakUser
from fred_core.common import PostgresStoreConfig
from fred_core.security.models import Resource
from fred_core.sql import create_async_engine_from_config
from fred_sdk.contracts.context import ModelBinding
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def _user(*, uid: str = "admin-1") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=["admin"], email=None)


# ---------------------------------------------------------------------------
# store.py — CRUD, absent row = unset, chat-only (no capability argument)
# ---------------------------------------------------------------------------


async def _make_store(tmp_path) -> PlatformModelBindingStore:
    from control_plane_backend.models.base import Base as ControlPlaneBase
    from fred_core.models.base import Base as CoreBase

    engine = create_async_engine_from_config(
        PostgresStoreConfig(
            sqlite_path=str(tmp_path / "platform_model_binding.sqlite3")
        )
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(ControlPlaneBase.metadata.create_all)
    return PlatformModelBindingStore(engine=engine)


async def test_get_omits_a_never_set_binding(tmp_path) -> None:
    store = await _make_store(tmp_path)
    assert await store.get() is None


async def test_set_then_get_round_trips(tmp_path) -> None:
    store = await _make_store(tmp_path)

    await store.set(
        binding=ModelBinding.model_validate(
            {
                "provider": "openai",
                "name": "gpt-4o",
                "settings": {"temperature": 0.2},
            }
        ),
        updated_by="admin-1",
    )

    row = await store.get()
    assert row is not None
    assert row.binding.provider == "openai"
    assert row.binding.name == "gpt-4o"
    assert row.binding.settings.temperature == 0.2
    assert row.updated_by == "admin-1"
    assert row.updated_at is not None


async def test_second_set_upserts_in_place(tmp_path) -> None:
    store = await _make_store(tmp_path)

    await store.set(
        binding=ModelBinding(provider="openai", name="gpt-4o"), updated_by="admin-1"
    )
    await store.set(
        binding=ModelBinding.model_validate(
            {
                "provider": "anthropic",
                "name": "claude-3-5-sonnet",
                "settings": {"top_p": 0.9},
            }
        ),
        updated_by="admin-2",
    )

    row = await store.get()
    assert row is not None
    assert row.binding.provider == "anthropic"
    assert row.binding.name == "claude-3-5-sonnet"
    assert row.binding.settings.top_p == 0.9
    assert row.updated_by == "admin-2"


async def test_concurrent_first_set_from_unset_does_not_500_the_loser(
    tmp_path,
) -> None:
    """Two callers racing `set()` while the binding is currently unset (two
    admins, or a client retrying a timed-out PUT) both see no existing row
    and both attempt an insert on the same `model_capability="chat"` primary
    key. The DB's own PK constraint lets only one commit through; the other
    must retry as an update instead of surfacing the raw `IntegrityError` —
    proven here with genuine `asyncio.gather` concurrency against a real
    SQLite-backed store, not a mock."""

    import asyncio

    store = await _make_store(tmp_path)

    results = await asyncio.gather(
        store.set(
            binding=ModelBinding(provider="openai", name="gpt-4o"),
            updated_by="admin-1",
        ),
        store.set(
            binding=ModelBinding(provider="anthropic", name="claude-3-5-sonnet"),
            updated_by="admin-2",
        ),
    )

    # Both callers get back a normal result — neither sees an unhandled
    # IntegrityError.
    assert {r.binding.provider for r in results} == {"openai", "anthropic"}

    # Exactly one row survives, matching whichever call's write landed last —
    # the CHECK constraint and PK make any other outcome structurally
    # impossible, so this only re-confirms `set()` didn't leave the row
    # missing or duplicated.
    row = await store.get()
    assert row is not None
    assert row.binding.provider in {"openai", "anthropic"}


async def test_delete_removes_the_row_and_get_omits_it_again(tmp_path) -> None:
    store = await _make_store(tmp_path)
    await store.set(
        binding=ModelBinding(provider="openai", name="gpt-4o"), updated_by="admin-1"
    )

    deleted = await store.delete()

    assert deleted is True
    assert await store.get() is None


async def test_delete_on_an_absent_row_returns_false_without_error(tmp_path) -> None:
    store = await _make_store(tmp_path)

    deleted = await store.delete()

    assert deleted is False


async def test_database_rejects_a_non_chat_row_even_bypassing_the_store(
    tmp_path,
) -> None:
    """The CHECK constraint (not just the store's chat-only API surface) is
    the actual enforcement boundary: even a raw insert naming a different
    `model_capability` must fail at the database layer."""

    from control_plane_backend.models.base import Base as ControlPlaneBase
    from control_plane_backend.models.platform_model_binding_models import (
        PlatformModelBindingRow,
    )
    from fred_core.models.base import Base as CoreBase
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine_from_config(
        PostgresStoreConfig(
            sqlite_path=str(tmp_path / "platform_model_binding_constraint.sqlite3")
        )
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(ControlPlaneBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            session.add(
                PlatformModelBindingRow(
                    model_capability="embedding",
                    provider="openai",
                    name="text-embedding-3",
                    settings_json="{}",
                    updated_by="admin-1",
                )
            )
            await session.commit()


CORRUPT_ROW_MATRIX: list[tuple[str, str, str]] = [
    ("empty provider", "", "{}"),
    (
        "unrecognized settings key",
        "openai",
        '{"api_key": "sk-not-a-real-key"}',  # pragma: allowlist secret
    ),
    (
        "azure-openai missing a required setting",
        "azure-openai",
        '{"azure_endpoint": "https://example.openai.azure.com"}',
    ),
    (
        "vertex-ai-model-garden missing a required setting",
        "vertex-ai-model-garden",
        '{"project": "proj-1", "location": "us-central1"}',
    ),
]


@pytest.mark.parametrize("label,provider,settings_json", CORRUPT_ROW_MATRIX)
async def test_get_raises_for_a_corrupt_row_inserted_by_bypassing_the_store(
    tmp_path, label: str, provider: str, settings_json: str
) -> None:
    """`PlatformModelBindingStore.get()` re-validates every row it reads
    through `ModelBinding` (`_binding_row_to_record`) — a row written by
    bypassing this store's own `set()` (e.g. hand-inserted with an empty
    provider, or a settings key `ModelBindingSettings` doesn't recognize)
    must fail closed on read, not hand back a binding that looks
    well-formed. Complements
    `test_database_rejects_a_non_chat_row_even_bypassing_the_store` above,
    which covers the `model_capability` CHECK constraint rather than the
    `ModelBinding` shape."""

    from control_plane_backend.models.base import Base as ControlPlaneBase
    from control_plane_backend.models.platform_model_binding_models import (
        PlatformModelBindingRow,
    )
    from fred_core.models.base import Base as CoreBase
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine_from_config(
        PostgresStoreConfig(
            sqlite_path=str(tmp_path / "platform_model_binding_corrupt.sqlite3")
        )
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(ControlPlaneBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            PlatformModelBindingRow(
                model_capability="chat",
                provider=provider,
                name="gpt-4o",
                settings_json=settings_json,
                updated_by="admin-1",
            )
        )
        await session.commit()

    store = PlatformModelBindingStore(engine=engine)
    with pytest.raises(Exception):  # noqa: B017, PT011 — ModelBinding's pydantic ValidationError
        await store.get()


# ---------------------------------------------------------------------------
# service.py — org-admin gate
# ---------------------------------------------------------------------------


class _RecordingPlatformModelBindingStore:
    def __init__(self, *, seeded: StoredPlatformModelBinding | None = None) -> None:
        self._row: StoredPlatformModelBinding | None = seeded
        self.set_calls: list[dict[str, Any]] = []
        self.delete_calls: int = 0

    async def get(self) -> StoredPlatformModelBinding | None:
        return self._row

    async def set(self, *, binding, updated_by) -> StoredPlatformModelBinding:
        self.set_calls.append({"binding": binding, "updated_by": updated_by})
        record = StoredPlatformModelBinding(
            binding=binding,
            updated_by=updated_by,
            updated_at=datetime.now(timezone.utc),
        )
        self._row = record
        return record

    async def delete(self) -> bool:
        self.delete_calls += 1
        existed = self._row is not None
        self._row = None
        return existed


class _FakeOrgAdminRebac:
    """Fake for `organization_authz.require_manage_any`'s
    `check_user_permission_or_raise` call — a distinct, narrower interface
    than the team-scoped fakes `test_routing_policy.py` uses."""

    def __init__(self, *, allow: bool) -> None:
        self.allow = allow
        self.calls = 0

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        self.calls += 1
        if not self.allow:
            raise AuthorizationError(
                user.uid, str(permission), Resource.ORGANIZATION, "denied"
            )


class _FakeDeps:
    """Minimal stand-in for `ProductServiceDependencies` — only the two
    attributes `routing_policy.service`'s platform-binding functions read."""

    def __init__(self, *, store, rebac) -> None:
        self._store = store
        self.team_dependencies = type("_TD", (), {"rebac": rebac})()

    def get_platform_model_binding_store(self):
        return self._store


def _deps(*, store, rebac) -> ProductServiceDependencies:
    """`_FakeDeps` duck-types `ProductServiceDependencies` (only the two
    attributes these service functions read) — one acknowledged type: ignore
    here instead of one per call site below (mirrors `test_routing_policy.py`)."""

    return _FakeDeps(store=store, rebac=rebac)  # type: ignore[return-value]


def _binding(provider: str = "openai", name: str = "gpt-4o") -> ModelBinding:
    return ModelBinding(provider=provider, name=name)


async def test_non_admin_is_denied_on_get() -> None:
    deps = _deps(
        store=_RecordingPlatformModelBindingStore(),
        rebac=_FakeOrgAdminRebac(allow=False),
    )
    with pytest.raises(AuthorizationError):
        await routing_policy_service.get_platform_model_binding(user=_user(), deps=deps)


async def test_non_admin_is_denied_on_set() -> None:
    deps = _deps(
        store=_RecordingPlatformModelBindingStore(),
        rebac=_FakeOrgAdminRebac(allow=False),
    )
    with pytest.raises(AuthorizationError):
        await routing_policy_service.set_platform_model_binding(
            user=_user(), binding=_binding(), deps=deps
        )


async def test_non_admin_is_denied_on_delete() -> None:
    deps = _deps(
        store=_RecordingPlatformModelBindingStore(),
        rebac=_FakeOrgAdminRebac(allow=False),
    )
    with pytest.raises(AuthorizationError):
        await routing_policy_service.delete_platform_model_binding(
            user=_user(), deps=deps
        )


async def test_admin_get_set_delete_all_succeed() -> None:
    store = _RecordingPlatformModelBindingStore()
    deps = _deps(store=store, rebac=_FakeOrgAdminRebac(allow=True))

    fetched = await routing_policy_service.get_platform_model_binding(
        user=_user(), deps=deps
    )
    assert isinstance(fetched, PlatformModelBinding)
    assert fetched.binding is None

    set_result = await routing_policy_service.set_platform_model_binding(
        user=_user(), binding=_binding(name="gpt-4o-mini"), deps=deps
    )
    assert isinstance(set_result, PlatformModelBinding)
    assert set_result.binding is not None
    assert set_result.binding.name == "gpt-4o-mini"
    assert set_result.model_capability == "chat"
    assert store.set_calls[-1]["updated_by"] == "admin-1"

    delete_result = await routing_policy_service.delete_platform_model_binding(
        user=_user(), deps=deps
    )
    assert delete_result.binding is None
    assert store.delete_calls == 1


# ---------------------------------------------------------------------------
# resolve_platform_chat_model_binding — the trusted per-turn entrypoint
# (replaces the removed resolve_platform_model_bindings_snapshot, which fed
# the now-deleted ExecutionPreparation.platform_model_bindings —
# client-forwarded session-prep snapshot, not a per-turn trusted lookup)
# ---------------------------------------------------------------------------


class _SnapshotDepsImpl:
    """Only `get_platform_model_binding_store` — no `team_dependencies`
    attribute at all, proving `resolve_platform_chat_model_binding`
    genuinely never touches authz itself (its caller,
    `get_runtime_binding_for_team`, is the one that's team-ReBAC-gated)."""

    def __init__(self, *, store) -> None:
        self._store = store

    def get_platform_model_binding_store(self):
        return self._store


def _snapshot_deps(*, store) -> ProductServiceDependencies:
    return _SnapshotDepsImpl(store=store)  # type: ignore[return-value]


async def test_resolve_chat_binding_is_none_when_unset() -> None:
    deps = _snapshot_deps(store=_RecordingPlatformModelBindingStore())

    binding = await routing_policy_service.resolve_platform_chat_model_binding(deps)

    assert binding is None


async def test_resolve_chat_binding_returns_the_set_row() -> None:
    seeded = StoredPlatformModelBinding(
        binding=ModelBinding.model_validate(
            {"provider": "openai", "name": "gpt-4o", "settings": {"temperature": 0.1}}
        ),
        updated_by="admin-1",
        updated_at=datetime.now(timezone.utc),
    )
    deps = _snapshot_deps(store=_RecordingPlatformModelBindingStore(seeded=seeded))

    binding = await routing_policy_service.resolve_platform_chat_model_binding(deps)

    assert binding == ModelBinding.model_validate(
        {"provider": "openai", "name": "gpt-4o", "settings": {"temperature": 0.1}}
    )


# A malformed/corrupt stored row can no longer be represented by
# `StoredPlatformModelBinding` at all — its `binding` field is a
# `ModelBinding`, already validated by construction — so the fail-closed
# "malformed row" cases live at the store layer now:
# `test_get_raises_for_a_corrupt_row_inserted_by_bypassing_the_store` above.
# `resolve_platform_chat_model_binding` inherits that guarantee simply by
# calling `store.get()`, proven below for a generic store failure.


class _RaisingPlatformModelBindingStore:
    """Stands in for a transient infra failure (DB connection error, pool
    exhaustion, table not yet migrated) — anything other than malformed
    stored data."""

    async def get(self) -> StoredPlatformModelBinding | None:
        raise RuntimeError("simulated platform_model_binding store failure")


async def test_resolve_chat_binding_raises_on_store_failure_instead_of_degrading() -> (
    None
):
    """A transient store failure (DB error, pool exhaustion, table not yet
    migrated) must propagate, exactly like a malformed row — never degrade
    to "no platform chat binding this turn". This read sits in the same
    `asyncio.gather` as `team_capability_settings` and
    `reasoning_enabled_model_ids` in `get_runtime_binding_for_team`, so the
    exception fails that whole per-turn call rather than being swallowed
    into a false "unset" result that would route through team/pod defaults
    while platform state is genuinely unknown.
    """
    deps = _snapshot_deps(store=_RaisingPlatformModelBindingStore())

    with pytest.raises(
        RuntimeError, match="simulated platform_model_binding store failure"
    ):
        await routing_policy_service.resolve_platform_chat_model_binding(deps)


# ---------------------------------------------------------------------------
# API boundary — strict ModelBindingSettings rejection/acceptance, chat-only
# routes (no {model_capability} path segment exists anymore)
# ---------------------------------------------------------------------------


REJECTED_SETTINGS_MATRIX: list[tuple[str, dict[str, Any]]] = [
    ("api_key", {"api_key": "sk-not-a-real-key"}),  # pragma: allowlist secret
    ("APIToken", {"APIToken": "t"}),  # pragma: allowlist secret
    ("IDToken", {"IDToken": "t"}),  # pragma: allowlist secret
    ("APISecret", {"APISecret": "s"}),  # pragma: allowlist secret
    ("TLSKey", {"TLSKey": "k"}),  # pragma: allowlist secret
    ("headers", {"headers": {"X-Custom": "v"}}),
    ("headers.Authorization", {"headers": {"Authorization": "Bearer x"}}),
    ("cookies", {"cookies": {"session": "abc"}}),
    ("auth", {"auth": {"user": "u", "pass": "p"}}),
    ("client", {"client": {"transport": "custom"}}),
    ("http_client", {"http_client": "opaque-handle"}),
    ("unknown_extra_key", {"unknown_extra_key": "anything"}),
    ("nested unknown object", {"unknown_extra_key": {"connect": 5, "nested": "x"}}),
    ("timeout (process-wide, pod-local only)", {"timeout": {"connect": 5}}),
    (
        "http_client_limits (process-wide, pod-local only)",
        {"http_client_limits": {"max_connections": 10}},
    ),
]


@pytest.mark.parametrize("label,forged_settings", REJECTED_SETTINGS_MATRIX)
async def test_put_rejects_every_forbidden_settings_shape(
    label: str, forged_settings: dict[str, Any]
) -> None:
    """`ModelBinding`'s own `settings` contract (`ModelBindingSettings`,
    fred-sdk) fires while FastAPI parses the request body — before
    `set_platform_model_binding` (and its org-admin gate) ever runs.
    Empirically confirmed here rather than assumed: FastAPI turns an
    unhandled Pydantic `ValidationError` on a request body into its standard
    422 `RequestValidationError` response, same as any other field-level
    body validation failure in this app."""

    from control_plane_backend.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/control-plane/v1/admin/platform/model-bindings",
            json={
                "binding": {
                    "provider": "openai",
                    "name": "gpt-4o",
                    "settings": forged_settings,
                }
            },
        )

    assert resp.status_code == 422, label


UNSUPPORTED_PROVIDER_MATRIX: list[str] = ["attacker", "mock", "mistral", "vertex", ""]


@pytest.mark.parametrize("provider", UNSUPPORTED_PROVIDER_MATRIX)
async def test_put_rejects_an_unsupported_provider_before_persistence(
    provider: str,
) -> None:
    """`ModelBinding.provider` is restricted to
    `fred_core.model.models.ModelProvider` — a PUT naming an unsupported
    provider must 422 at the request-parsing boundary and never reach the
    store, or every subsequent managed chat turn would fail at runtime
    model construction instead of being caught here."""

    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    await container.get_platform_model_binding_store().delete()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/control-plane/v1/admin/platform/model-bindings",
            json={"binding": {"provider": provider, "name": "gpt-4o", "settings": {}}},
        )

    assert resp.status_code == 422, provider
    assert await container.get_platform_model_binding_store().get() is None


# The minimal settings each provider needs to construct successfully,
# mirroring exactly what `fred_core.model.factory.get_model()`'s own
# `_require_settings(...)` calls require per provider. `openai`, `ollama`,
# and `anthropic` need nothing beyond the provider + non-empty `name` every
# binding already requires.
PROVIDER_MINIMAL_VALID_SETTINGS: dict[str, dict[str, Any]] = {
    "openai": {},
    "ollama": {},
    "anthropic": {},
    "azure-openai": {
        "azure_endpoint": "https://example.openai.azure.com",
        "azure_openai_api_version": "2024-05-01",
    },
    "azure-apim": {
        "azure_ad_client_id": "client-id",
        "azure_ad_client_scope": "scope",
        "azure_apim_base_url": "https://apim.example.internal",
        "azure_apim_resource_path": "/openai",
        "azure_openai_api_version": "2024-05-01",
        "azure_tenant_id": "tenant-id",
    },
    "vertex-ai": {"project": "proj-1", "location": "us-central1"},
    "vertex-ai-model-garden": {
        "project": "proj-1",
        "location": "us-central1",
        "model_family": "mistral",
    },
}


@pytest.mark.parametrize("provider,settings", PROVIDER_MINIMAL_VALID_SETTINGS.items())
async def test_put_accepts_each_provider_with_its_minimal_valid_settings(
    provider: str, settings: dict[str, Any]
) -> None:
    """Every supported provider must be settable through the real HTTP PUT
    with only the settings `fred_core.model.factory.get_model()` actually
    requires for it — proves `ModelBinding`'s provider-required-settings
    validator accepts a genuinely minimal, valid binding rather than
    over-rejecting it."""

    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/control-plane/v1/admin/platform/model-bindings",
                json={
                    "binding": {
                        "provider": provider,
                        "name": "some-model",
                        "settings": settings,
                    }
                },
            )
        assert resp.status_code == 200, (provider, resp.text)
        assert resp.json()["binding"]["provider"] == provider
    finally:
        await container.get_platform_model_binding_store().delete()


PROVIDER_REQUIRED_FIELD_OMISSION_MATRIX: list[tuple[str, str]] = [
    ("azure-openai", "azure_endpoint"),
    ("azure-openai", "azure_openai_api_version"),
    ("azure-apim", "azure_ad_client_id"),
    ("azure-apim", "azure_ad_client_scope"),
    ("azure-apim", "azure_apim_base_url"),
    ("azure-apim", "azure_apim_resource_path"),
    ("azure-apim", "azure_openai_api_version"),
    ("azure-apim", "azure_tenant_id"),
    ("vertex-ai", "project"),
    ("vertex-ai", "location"),
    ("vertex-ai-model-garden", "project"),
    ("vertex-ai-model-garden", "location"),
    ("vertex-ai-model-garden", "model_family"),
]


@pytest.mark.parametrize(
    "provider,omitted_field", PROVIDER_REQUIRED_FIELD_OMISSION_MATRIX
)
async def test_put_rejects_provider_missing_one_required_field_before_persistence(
    provider: str, omitted_field: str
) -> None:
    """A binding missing just one of its provider's required settings must
    422 at request-parsing time and never reach the store — otherwise every
    subsequent managed chat turn would fail at runtime model construction
    instead of being caught here."""

    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    settings = dict(PROVIDER_MINIMAL_VALID_SETTINGS[provider])
    settings.pop(omitted_field)

    app = create_app()
    container = get_application_container_from_app(app)
    await container.get_platform_model_binding_store().delete()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/control-plane/v1/admin/platform/model-bindings",
            json={
                "binding": {
                    "provider": provider,
                    "name": "some-model",
                    "settings": settings,
                }
            },
        )

    assert resp.status_code == 422, (provider, omitted_field)
    assert await container.get_platform_model_binding_store().get() is None


TYPE_AND_RANGE_REJECTED_SETTINGS_MATRIX: list[tuple[str, dict[str, Any]]] = [
    ("max_tokens as string", {"max_tokens": "4096"}),
    ("max_retries as bool", {"max_retries": True}),
    ("streaming as int", {"streaming": 1}),
    ("request_timeout as string", {"request_timeout": "5"}),
    ("request_timeout negative", {"request_timeout": -1.0}),
    ("max_tokens zero", {"max_tokens": 0}),
    ("top_p above range", {"top_p": 1.5}),
]


@pytest.mark.parametrize(
    "label,forged_settings", TYPE_AND_RANGE_REJECTED_SETTINGS_MATRIX
)
async def test_put_rejects_every_type_and_range_violation_before_persistence(
    label: str, forged_settings: dict[str, Any]
) -> None:
    """Same request-parsing-time rejection as the forbidden-shape matrix
    above, for a value that is a plausible JSON type but the wrong one (a
    string where an int belongs, a bool where an int belongs) or out of the
    downstream-consumer-derived bound — never coerced, never persisted."""

    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    await container.get_platform_model_binding_store().delete()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/control-plane/v1/admin/platform/model-bindings",
            json={
                "binding": {
                    "provider": "openai",
                    "name": "gpt-4o",
                    "settings": forged_settings,
                }
            },
        )

    assert resp.status_code == 422, label
    assert await container.get_platform_model_binding_store().get() is None


URL_REJECTED_SETTINGS_MATRIX: list[tuple[str, dict[str, Any]]] = [
    ("non-http(s) scheme", {"base_url": "ftp://internal.example/v1"}),
    ("username userinfo", {"base_url": "https://admin@internal.example/v1"}),
    (
        "password userinfo",
        {"base_url": "https://admin:" + "synthetic-value" + "@internal.example/v1"},
    ),
    ("malformed URL", {"base_url": "not-a-url"}),
]


@pytest.mark.parametrize("label,forged_settings", URL_REJECTED_SETTINGS_MATRIX)
async def test_put_rejects_every_invalid_base_url(
    label: str, forged_settings: dict[str, Any]
) -> None:
    from control_plane_backend.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/control-plane/v1/admin/platform/model-bindings",
            json={
                "binding": {
                    "provider": "openai",
                    "name": "gpt-4o",
                    "settings": forged_settings,
                }
            },
        )

    assert resp.status_code == 422, label


async def test_put_accepts_a_valid_http_on_prem_base_url() -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/control-plane/v1/admin/platform/model-bindings",
                json={
                    "binding": {
                        "provider": "openai",
                        "name": "gpt-4o",
                        "settings": {"base_url": "http://on-prem.internal:8080/v1"},
                    }
                },
            )
        assert resp.status_code == 200
        assert resp.json()["binding"]["settings"] == {
            "base_url": "http://on-prem.internal:8080/v1"
        }
    finally:
        await container.get_platform_model_binding_store().delete()


async def test_put_accepts_ordinary_settings_and_preserves_json_types() -> None:
    """Round-trip proof: boolean, integer, float, string, and a typed nested
    object survive PUT -> persistence -> GET without type coercion."""

    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    settings = {
        "max_tokens": 4096,
        "temperature": 0.2,
        "streaming": True,
        "azure_openai_api_version": "2024-05-01",
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            put_resp = await client.put(
                "/control-plane/v1/admin/platform/model-bindings",
                json={
                    "binding": {
                        "provider": "openai",
                        "name": "gpt-4o",
                        "settings": settings,
                    }
                },
            )
            assert put_resp.status_code == 200
            assert put_resp.json()["binding"]["settings"] == settings

            get_resp = await client.get(
                "/control-plane/v1/admin/platform/model-bindings"
            )
            assert get_resp.status_code == 200
            assert get_resp.json()["binding"]["settings"] == settings
            body = get_resp.json()
            assert body["binding"]["settings"]["max_tokens"] == 4096
            assert isinstance(body["binding"]["settings"]["max_tokens"], int)
            assert isinstance(body["binding"]["settings"]["temperature"], float)
            assert isinstance(body["binding"]["settings"]["streaming"], bool)
    finally:
        await container.get_platform_model_binding_store().delete()


async def test_get_returns_unset_binding_when_none_configured() -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    await container.get_platform_model_binding_store().delete()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/admin/platform/model-bindings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_capability"] == "chat"
    # response_model_exclude_none=True: a None binding is omitted, not null.
    assert "binding" not in body


async def test_delete_clears_the_binding() -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app

    app = create_app()
    container = get_application_container_from_app(app)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.put(
            "/control-plane/v1/admin/platform/model-bindings",
            json={"binding": {"provider": "openai", "name": "gpt-4o", "settings": {}}},
        )
        resp = await client.delete("/control-plane/v1/admin/platform/model-bindings")

    assert resp.status_code == 200
    assert "binding" not in resp.json()
    assert await container.get_platform_model_binding_store().get() is None


async def test_legacy_capability_scoped_routes_no_longer_exist() -> None:
    """The `{model_capability}` path segment (pre-Slice-2 shape) is gone —
    V1 is chat-only, so there is no per-capability route to request at all.
    Any client still targeting the old shape (including a value that used
    to mean `language`/`embedding`/`image`) gets a 404: the route itself no
    longer exists, not a 200 that silently ignores the capability."""

    from control_plane_backend.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for capability in ("chat", "language", "embedding", "image"):
            get_resp = await client.get(
                f"/control-plane/v1/admin/platform/model-bindings/{capability}"
            )
            assert get_resp.status_code == 404, capability

            put_resp = await client.put(
                f"/control-plane/v1/admin/platform/model-bindings/{capability}",
                json={
                    "binding": {
                        "provider": "openai",
                        "name": "gpt-4o",
                        "settings": {},
                    }
                },
            )
            assert put_resp.status_code == 404, capability

            delete_resp = await client.delete(
                f"/control-plane/v1/admin/platform/model-bindings/{capability}"
            )
            assert delete_resp.status_code == 404, capability


# ---------------------------------------------------------------------------
# get_runtime_binding_for_team / GET .../runtime — the TRUSTED per-turn
# endpoint. Replaces the removed `prepare_execution` fold-in:
# `ExecutionPreparation` no longer carries a platform-binding field at all —
# the binding is resolved only here, on the runtime's own per-turn,
# server-to-server lookup, never forwarded through the browser.
# ---------------------------------------------------------------------------


async def test_prepare_execution_response_has_no_platform_binding_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for the removal itself: a caller reading
    `ExecutionPreparation` (session-prep, client-forwarded) must not find a
    platform-binding key anywhere in the payload, set or not — proving the
    client-forwarded channel this feature used to (ab)use is gone, not just
    empty."""
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.config.models import RuntimeCatalogSourceConfig
    from control_plane_backend.main import create_app
    from test_main import (
        _fake_require_team_access,
        _FakeAgentInstanceStore,
        _make_record,
        _patch_store,
    )

    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access",
        _fake_require_team_access,
    )
    store = _FakeAgentInstanceStore(
        [
            _make_record(
                agent_instance_id="inst-pmb-1",
                source_runtime_id="runtime-pmb",
                template_id="runtime-pmb:rags.sample.echo",
                source_agent_id="rags.sample.echo",
            )
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-pmb",
            base_url="http://runtime-pmb.internal",
            enabled=True,
            ingress_prefix="/runtime/runtime-pmb",
        )
    ]

    binding_store = container.get_platform_model_binding_store()
    await binding_store.delete()
    try:
        await binding_store.set(
            binding=ModelBinding.model_validate(
                {
                    "provider": "openai",
                    "name": "gpt-4o-mini",
                    "settings": {"temperature": 0.2},
                }
            ),
            updated_by="admin-1",
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/control-plane/v1/teams/personal/agent-instances/inst-pmb-1/prepare-execution"
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert "platform_model_bindings" not in payload
        assert "platform_chat_model_binding" not in payload
    finally:
        await binding_store.delete()


async def test_runtime_binding_endpoint_carries_the_trusted_chat_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The team-scoped `GET .../runtime` endpoint — the runtime pod's own
    per-turn, server-to-server lookup — must carry the current platform
    `chat` binding, fresh on every call."""
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from test_main import (
        _fake_require_team_access,
        _FakeAgentInstanceStore,
        _make_record,
        _patch_store,
    )

    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access",
        _fake_require_team_access,
    )
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)

    binding_store = container.get_platform_model_binding_store()
    await binding_store.delete()
    try:
        await binding_store.set(
            binding=ModelBinding.model_validate(
                {
                    "provider": "openai",
                    "name": "gpt-4o-mini",
                    "settings": {"temperature": 0.2},
                }
            ),
            updated_by="admin-1",
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/control-plane/v1/teams/personal/agent-instances/instance-1/runtime"
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["platform_chat_model_binding"] == {
            "provider": "openai",
            "name": "gpt-4o-mini",
            "settings": {"temperature": 0.2},
        }
    finally:
        await binding_store.delete()


async def test_runtime_binding_endpoint_omits_chat_binding_when_none_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from test_main import (
        _fake_require_team_access,
        _FakeAgentInstanceStore,
        _make_record,
        _patch_store,
    )

    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access",
        _fake_require_team_access,
    )
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    # Belt and suspenders: this DB is session-shared across this file's
    # tests, so make sure no earlier test left a binding set.
    await container.get_platform_model_binding_store().delete()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/control-plane/v1/teams/personal/agent-instances/instance-1/runtime"
        )

    assert resp.status_code == 200
    # response_model_exclude_none=True: a None binding is omitted, not null —
    # same convention as every other optional field on this response.
    assert "platform_chat_model_binding" not in resp.json()


async def test_runtime_binding_endpoint_fails_closed_when_binding_resolution_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store/validation failure while resolving the platform chat binding
    must surface as a 500 that is
    NOT parseable as a successful "no binding set" response — never a 200
    silently omitting `platform_chat_model_binding`, which the runtime and a
    client cannot distinguish from the legitimate unset case. Verifies the
    resolution failure actually reaches the HTTP boundary (not just the unit
    level covered by `test_resolve_chat_binding_raises_on_store_failure_instead_of_degrading`).
    """
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from test_main import (
        _fake_require_team_access,
        _FakeAgentInstanceStore,
        _make_record,
        _patch_store,
    )

    async def _raise(deps: ProductServiceDependencies) -> ModelBinding | None:
        raise RuntimeError("simulated platform_model_binding store failure")

    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access",
        _fake_require_team_access,
    )
    monkeypatch.setattr(
        "control_plane_backend.product.service.resolve_platform_chat_model_binding",
        _raise,
    )
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    await container.get_platform_model_binding_store().delete()

    # `raise_app_exceptions=False`: let the request actually run through
    # Starlette's built-in `ServerErrorMiddleware` (this app registers no
    # catch-all `Exception` handler of its own — only typed domain errors
    # get one, see `main.py`) and produce the real HTTP 500 response a
    # deployed server would send, instead of re-raising into the test — the
    # default `True` is a test-debugging convenience.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/control-plane/v1/teams/personal/agent-instances/instance-1/runtime"
        )

    assert resp.status_code == 500
    # Starlette's default `ServerErrorMiddleware` fallback: plain text, not
    # a `ManagedAgentRuntimeBinding` JSON payload a caller could mistake for
    # a successful "unset" response.
    assert "platform_chat_model_binding" not in resp.text


async def test_runtime_binding_endpoint_reflects_a_binding_change_on_the_next_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freshness: no session-open snapshot contract exists
    for this field — an admin clearing or changing the binding must be
    visible on the very next per-turn call, not held over from an earlier
    resolution."""
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from test_main import (
        _fake_require_team_access,
        _FakeAgentInstanceStore,
        _make_record,
        _patch_store,
    )

    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access",
        _fake_require_team_access,
    )
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    binding_store = container.get_platform_model_binding_store()
    await binding_store.delete()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            url = "/control-plane/v1/teams/personal/agent-instances/instance-1/runtime"

            first = await client.get(url)
            assert "platform_chat_model_binding" not in first.json()

            await binding_store.set(
                binding=ModelBinding(provider="openai", name="gpt-4o-mini"),
                updated_by="admin-1",
            )
            second = await client.get(url)
            assert second.json()["platform_chat_model_binding"]["name"] == "gpt-4o-mini"

            await binding_store.delete()
            third = await client.get(url)
            assert "platform_chat_model_binding" not in third.json()
    finally:
        await binding_store.delete()
