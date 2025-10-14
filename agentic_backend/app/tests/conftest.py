# app/tests/conftest.py

import os

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import (
    DuckdbStoreConfig,
    M2MSecurity,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    SecurityConfiguration,
    SpiceDbRebacConfig,
    UserSecurity,
)
from pydantic import AnyHttpUrl, AnyUrl

from app.application_context import ApplicationContext

# ⬇️ NEW: Agent/union + RecursionConfig now live in tuning_spec
# ⬇️ REST of your config types stay where they were
from app.common.structures import (
    Agent,
    AIConfig,
    AppConfig,
    Configuration,
    FrontendFlags,
    FrontendSettings,
    ModelConfiguration,
    Properties,
    StorageConfig,
    TimeoutSettings,
)


@pytest.fixture(scope="session")
def minimal_generalist_config() -> Configuration:
    duckdb_store = DuckdbStoreConfig(type="duckdb", duckdb_path="/tmp/test-duckdb.db")
    os.environ.setdefault("SPICEDB_TOKEN", "test")
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
        rebac=SpiceDbRebacConfig(
            endpoint="localhost:50051",
            insecure=True,
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
            default_chat_model=ModelConfiguration(
                provider="openai",
                name="gpt-4o",
                settings={"temperature": 0.0, "max_retries": 2, "request_timeout": 30},
            ),
            agents=[
                # ⬇️ instantiate the concrete Agent (discriminator handled automatically)
                Agent(
                    name="Georges",
                    role="Generalist",
                    description="Generalist",
                    class_path="app.agents.generalist.generalist_expert.Georges",
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
                    tags=["test"],  # optional; good to exercise schema
                    # mcp_servers=[],  # optional; default ok
                    # tuning=None,     # optional; default ok
                ),
            ],
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
    app.include_router(router)
    return TestClient(app)
