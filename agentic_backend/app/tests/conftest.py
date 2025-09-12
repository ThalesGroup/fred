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

# app/tests/conftest.py


import pytest
from pydantic import AnyHttpUrl, AnyUrl
from fastapi.testclient import TestClient
from fastapi import FastAPI, APIRouter

from app.common.structures import (
    AIConfig,
    AgentSettings,
    AppConfig,
    Configuration,
    FrontendFlags,
    FrontendSettings,
    ModelConfiguration,
    Properties,
    RecursionConfig,
    StorageConfig,
    TimeoutSettings,
)
from app.application_context import ApplicationContext
from fred_core import (
    DuckdbStoreConfig,
    PostgresStoreConfig,
    OpenSearchStoreConfig,
    SecurityConfiguration,
    M2MSecurity,
    UserSecurity,
)


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
            authorized_origins=[AnyHttpUrl("http://localhost:5173")],
        ),
    )

    return Configuration(
        app=AppConfig(
            base_url="/agentic/v1",
            address="127.0.0.1",
            port=8000,
            log_level="debug",
            reload=False,
            reload_dir=".",
        ),
        frontend_settings=FrontendSettings(
            feature_flags=FrontendFlags(
                enableK8Features=False, enableElecWarfare=False
            ),
            properties=Properties(logoName="fred"),
        ),
        security=fake_security_config,
        ai=AIConfig(
            knowledge_flow_url="http://localhost:8000/agentic/v1",
            timeout=TimeoutSettings(connect=5, read=15),
            default_model=ModelConfiguration(
                provider="openai",
                name="gpt-4o",
                settings={"temperature": 0.0, "max_retries": 2, "request_timeout": 30},
            ),
            agents=[
                AgentSettings(
                    name="GeneralistExpert",
                    role="Generalist",
                    description="Generalist",
                    class_path="app.agents.generalist.generalist_expert.GeneralistExpert",
                    enabled=True,
                    model=ModelConfiguration(
                        provider="openai",
                        name="gpt-4o",
                        settings={
                            "temperature": 0.0,
                            "max_retries": 2,
                            "request_timeout": 30,
                        },
                    ),
                )
            ],
            recursion=RecursionConfig(recursion_limit=40),
        ),
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
            session_store=duckdb_store,
            history_store=duckdb_store,
            feedback_store=duckdb_store,
            kpi_store=duckdb_store,
        ),
    )


@pytest.fixture(scope="session")
def app_context(minimal_generalist_config):
    return ApplicationContext(minimal_generalist_config)


@pytest.fixture
def client(app_context) -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/agentic/v1")
    # ChatbotController(router)
    app.include_router(router)
    return TestClient(app)
