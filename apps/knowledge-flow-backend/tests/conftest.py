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


import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fred_core import M2MSecurity, SecurityConfiguration, UserSecurity
from fred_core.common import OpenSearchStoreConfig, PostgresStoreConfig
from fred_core.common.structures import KpiObservabilityConfig, KpiOpenSearchSinkConfig
from pydantic import AnyHttpUrl, AnyUrl
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import AppConfig, Configuration, ObservabilityConfig, PgVectorStorageConfig, StorageConfig
from knowledge_flow_backend.main import create_app


@pytest.fixture(scope="function", autouse=True)
def app_context(monkeypatch, tmp_path):
    """Initialize the API configuration without a processor registry."""
    ApplicationContext._instance = None
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    # OpenSearchStoreConfig sources its password from this env var; set it so the
    # config below builds without reaching OpenSearch (unit-level, no integration).
    monkeypatch.setenv("OPENSEARCH_PASSWORD", "test")  # pragma: allowlist secret

    fake_security_config = SecurityConfiguration(
        m2m=M2MSecurity(enabled=False, realm_url=AnyUrl("http://localhost:8080/realms/fake-m2m-realm"), client_id="fake-m2m-client"),
        user=UserSecurity(enabled=False, realm_url=AnyUrl("http://localhost:8080/realms/fake-user-realm"), client_id="fake-user-client"),
        authorized_origins=[AnyHttpUrl("http://localhost:5173")],
    )
    config = Configuration(
        app=AppConfig(
            base_url="/knowledge-flow/v2",
            address="127.0.0.1",
            port=8888,
            log_level="debug",
            reload=False,
            reload_dir=".",
        ),
        security=fake_security_config,
        storage=StorageConfig(
            postgres=PostgresStoreConfig(
                host="localhost",
                port=5432,
                username="user",
                database="test_db",
                schema="knowledge",
            ),
            opensearch=OpenSearchStoreConfig(
                host="http://localhost:9200",
                username="admin",
            ),
            vector_store=PgVectorStorageConfig(type="pgvector"),
        ),
        observability=ObservabilityConfig(
            kpi=KpiObservabilityConfig(
                opensearch=KpiOpenSearchSinkConfig(enabled=False),
            )
        ),
    )

    ctx = ApplicationContext(config)
    return ctx


@pytest_asyncio.fixture
async def sqlite_engine(tmp_path):
    """Close SQLite connections before pytest tears down the owning event loop."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
def client_fixture(app_context: ApplicationContext):
    """Returns a test client for FastAPI app."""
    app = create_app()
    with TestClient(app) as client:
        yield client
