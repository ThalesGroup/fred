# Copyright Thales 2025
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

from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import (
    KeycloakUser,
    M2MSecurity,
    SecurityConfiguration,
    UserSecurity,
    get_current_user,
)
from fred_core.common import (
    DuckdbStoreConfig,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
)
from pydantic import AnyHttpUrl, AnyUrl

from agentic_backend.application_context import ApplicationContext

# ⬇️ NEW: Agent/union + RecursionConfig now live in tuning_spec
# ⬇️ REST of your config types stay where they were
from agentic_backend.common.structures import (
    Agent,
    AIConfig,
    AppConfig,
    Configuration,
    FrontendFlags,
    FrontendSettings,
    McpConfiguration,
    Properties,
    StorageConfig,
    TimeoutSettings,
)
from agentic_backend.core.agents import agent_controller
from agentic_backend.core.chatbot import chatbot_controller


@pytest.fixture(scope="session")
def minimal_generalist_config() -> Configuration:
    duckdb_store = DuckdbStoreConfig(type="duckdb", duckdb_path="/tmp/test-duckdb.db")
    fake_security_config = SecurityConfiguration(
        m2m=M2MSecurity(
            enabled=False,
            realm_url=AnyUrl("http://localhost:8080/realms/fake-m2m-realm"),
            client_id="fake-m2m-client",
            audience="fake-audience",
        ),
        user=UserSecurity(
            enabled=False,
            realm_url=AnyUrl("http://localhost:8080/realms/fake-user-realm"),
            client_id="fake-user-client",
        ),
        authorized_origins=[AnyHttpUrl("http://localhost:5173")],
        rebac=None,
    )

    return Configuration(
        app=AppConfig(
            base_url="/agentic/v1",
            address="127.0.0.1",
            port=8000,
            log_level="debug",
            reload=False,
            reload_dir=".",
            kpi_process_metrics_interval_sec=10,
        ),
        frontend_settings=FrontendSettings(
            feature_flags=FrontendFlags(
                enableK8Features=False, enableElecWarfare=False
            ),
            properties=Properties(
                logoName="fred", logoNameDark="fred-dark", siteDisplayName="Fred"
            ),
        ),
        security=fake_security_config,
        ai=AIConfig(
            use_static_config_only=True,
            enable_catalog_mode=False,
            enable_v2_sql_checkpointer=True,
            max_concurrent_agents=128,
            restore_max_exchanges=20,
            knowledge_flow_url="http://localhost:8000/agentic/v1",
            timeout=TimeoutSettings(connect=5, read=15),
            max_concurrent_sessions_per_user=10,
            max_attached_files_per_user=10,
            max_attached_file_size_mb=10,
            default_chat_model=ModelConfiguration(
                provider="test",
                name="test",
                settings={"temperature": 0.0, "max_retries": 2, "request_timeout": 30},
            ),
            default_language_model=ModelConfiguration(
                provider="openai",
                name="gpt-4o",
                settings={"temperature": 0.0, "max_retries": 2, "request_timeout": 30},
            ),
            agents=[
                # ⬇️ instantiate the concrete Agent (discriminator handled automatically)
                Agent(
                    id="basic.react.v2",
                    name="Basic ReAct V2",
                    class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
                    enabled=True,
                )
            ],
        ),
        mcp=McpConfiguration(servers=[]),
        storage=StorageConfig(
            postgres=PostgresStoreConfig(
                host="localhost",
                port=5432,
                username="user",
                database="test_db",
            ),
            opensearch=OpenSearchStoreConfig(
                host="http://localhost:9200",
                username="admin",
            ),
            agent_store=duckdb_store,
            mcp_servers_store=duckdb_store,
            session_store=duckdb_store,
            history_store=duckdb_store,
            feedback_store=duckdb_store,
            kpi_store=duckdb_store,
            task_store=duckdb_store,
        ),
    )


@pytest.fixture(scope="session")
def app_context(minimal_generalist_config):
    return ApplicationContext(minimal_generalist_config)


@pytest.fixture
def client(app_context, monkeypatch) -> TestClient:
    app = FastAPI()
    # Mount our API under the expected base URL
    router = APIRouter(prefix="/agentic/v1")

    # Include the routes under test
    router.include_router(chatbot_controller.router)
    router.include_router(agent_controller.router)
    app.include_router(router)

    class _FakeAgentService:
        def __init__(self, agent_manager):
            self.agent_manager = agent_manager

        async def list_agents(self, user, owner_filter=None, team_id=None):
            return list(app_context.configuration.ai.agents)

        async def get_agent_by_id(self, user, agent_id):
            for agent in app_context.configuration.ai.agents:
                if agent.id == agent_id:
                    return agent
            return None

    monkeypatch.setattr(agent_controller, "AgentService", _FakeAgentService)

    # Minimal app state for dependencies that read app.state.agent_manager
    app.state.agent_manager = SimpleNamespace(config=app_context.configuration)

    # Keep auth predictable
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="u-1", username="tester", email="t@example.com", roles=["user"]
    )

    return TestClient(app)
