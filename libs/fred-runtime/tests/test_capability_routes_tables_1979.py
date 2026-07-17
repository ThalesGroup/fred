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

"""
Capability routes + tables + migration CLI (#1979, RFC §7.1, §9.1).

Covers:
- a capability's `manifest.router` is auto-mounted under
  `/capabilities/{id}` and callable, and its ingress-relative base URL is
  advertised on the template catalog (`route_base_url`)
- table hygiene is enforced at pod boot: `cap_<id>_` prefix and no foreign keys
- the migration runner discovers a capability's own Alembic tree and applies it
  under a per-capability version table
- the per-capability OpenAPI dump yields only that capability's routes/schemas
"""

from __future__ import annotations

import pytest
from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app import create_agent_app
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.demo import DemoEchoCapability
from fred_runtime.capabilities.errors import CapabilityTableHygieneError
from fred_runtime.capabilities.openapi_dump import dump_capability_openapi
from fred_runtime.migrations import run_all_migrations
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from test_agent_app import _build_test_config, _EchoAgent

# ---------------------------------------------------------------------------
# Helpers — a running pod with the demo capability discovered
# ---------------------------------------------------------------------------


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
        raising=True,
    )
    definition = _EchoAgent()
    app = create_agent_app(
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )
    client = TestClient(app)
    client.__enter__()  # run lifespan → boot registry on app.state
    return client


# ---------------------------------------------------------------------------
# Routes (RFC §9.1)
# ---------------------------------------------------------------------------


def test_capability_router_auto_mounted_and_callable(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        response = client.post(
            "/pod/v1/capabilities/demo_echo/analyze", json={"text": "hi"}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"original": "hi", "transformed": "HI", "length": 2}
    finally:
        client.__exit__(None, None, None)


def test_catalog_advertises_route_base_url(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        response = client.get("/pod/v1/agents/templates")
        assert response.status_code == 200, response.text
        entry = response.json()[0]["available_capabilities"][0]
        assert entry["route_base_url"] == "/pod/v1/capabilities/demo_echo"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Table hygiene (RFC §7.1)
# ---------------------------------------------------------------------------


class _BadPrefixBase(DeclarativeBase):
    pass


class _BadPrefixRow(_BadPrefixBase):
    __tablename__ = "notes"  # missing cap_<id>_ prefix
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class _BadPrefixCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    manifest = CapabilityManifest(
        id="badprefix",
        version="0.1.0",
        name="k",
        description="k",
        icon="i",
        tables=[_BadPrefixRow],
    )
    ConfigModel = EmptyModel

    def middleware(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> list[AgentMiddleware]:
        return []


class _FkBase(DeclarativeBase):
    pass


class _FkRow(_FkBase):
    __tablename__ = "cap_withfk_row"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # A foreign key of any kind is forbidden on a capability table.
    other_id: Mapped[str] = mapped_column(
        String, ForeignKey("session_history.session_id")
    )


class _FkCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    manifest = CapabilityManifest(
        id="withfk",
        version="0.1.0",
        name="k",
        description="k",
        icon="i",
        tables=[_FkRow],
    )
    ConfigModel = EmptyModel

    def middleware(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> list[AgentMiddleware]:
        return []


def test_table_hygiene_rejects_missing_prefix() -> None:
    registry = CapabilityRegistry()
    registry.register(_BadPrefixCapability())
    with pytest.raises(CapabilityTableHygieneError, match="cap_badprefix_"):
        registry.validate({})


def test_table_hygiene_rejects_foreign_key() -> None:
    registry = CapabilityRegistry()
    registry.register(_FkCapability())
    with pytest.raises(CapabilityTableHygieneError, match="foreign key"):
        registry.validate({})


def test_demo_tables_pass_hygiene() -> None:
    registry = CapabilityRegistry()
    registry.register(DemoEchoCapability())
    registry.validate({})  # must not raise


# ---------------------------------------------------------------------------
# Migration discovery + runner (RFC §7.1)
# ---------------------------------------------------------------------------


def test_migration_locations_include_demo() -> None:
    registry = CapabilityRegistry()
    registry.register(DemoEchoCapability())
    locations = dict(registry.migration_locations())
    assert "demo_echo" in locations
    assert locations["demo_echo"].endswith("demo_migrations")


def test_run_all_migrations_creates_per_capability_version_table(
    tmp_path, monkeypatch
) -> None:
    import sqlite3

    db_path = tmp_path / "migrate.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    upgraded = run_all_migrations()
    assert upgraded[0] == "fred-runtime"
    assert "demo_echo" in upgraded

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table'")
        }
    finally:
        conn.close()
    # fred-runtime's own version table, the demo capability's OWN version table,
    # and the demo capability's owned table.
    assert "alembic_version_runtime" in tables
    assert "cap_demo_echo_alembic_version" in tables
    assert "cap_demo_echo_notes" in tables


# ---------------------------------------------------------------------------
# Per-capability OpenAPI dump (RFC §9.1)
# ---------------------------------------------------------------------------


def test_dump_capability_openapi_is_isolated() -> None:
    document = dump_capability_openapi(DemoEchoCapability())
    assert list(document["paths"]) == ["/analyze"]
    schemas = document["components"]["schemas"]
    assert "DemoAnalyzeRequest" in schemas
    assert "DemoAnalyzeResponse" in schemas


def test_dump_capability_openapi_without_router_raises() -> None:
    class _NoRouter(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
        manifest = CapabilityManifest(
            id="norouter", version="0.1.0", name="k", description="k", icon="i"
        )
        ConfigModel = EmptyModel

        def middleware(
            self, ctx: CapabilityContext[EmptyModel, EmptyModel]
        ) -> list[AgentMiddleware]:
            return []

    with pytest.raises(ValueError, match="no router"):
        dump_capability_openapi(_NoRouter())
