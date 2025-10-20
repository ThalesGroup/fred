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
from fastapi.testclient import TestClient
from fred_core import (
    DuckdbStoreConfig,
    M2MSecurity,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    SecurityConfiguration,
    UserSecurity,
)
from langchain_community.embeddings import FakeEmbeddings
from pydantic import AnyHttpUrl, AnyUrl

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import (
    AppConfig,
    Configuration,
    InMemoryVectorStorage,
    LocalContentStorageConfig,
    ProcessingConfig,
    ProcessorConfig,
    PushSourceConfig,
    SchedulerConfig,
    StorageConfig,
    TemporalSchedulerConfig,
)
from knowledge_flow_backend.core.processors.output.vectorization_processor.embedder import Embedder
from knowledge_flow_backend.main import create_app
from .test_utils.test_processors import TestMarkdownProcessor, TestOutputProcessor


@pytest.fixture(scope="function", autouse=True)
def fake_embedder(monkeypatch):
    """Monkeypatch the Embedder to avoid real API calls."""

    def fake_init(self, config=None):
        self.model = FakeEmbeddings(size=1352)

    monkeypatch.setattr(Embedder, "__init__", fake_init)


@pytest.fixture(scope="function", autouse=True)
def app_context(monkeypatch, fake_embedder):
    """Fixture to initialize ApplicationContext with full duckdb/local config."""
    ApplicationContext._instance = None
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    duckdb = DuckdbStoreConfig(type="duckdb", duckdb_path="/tmp/testdb.duckdb")
    fake_security_config = SecurityConfiguration(
        m2m=M2MSecurity(enabled=False, realm_url=AnyUrl("http://localhost:8080/realms/fake-m2m-realm"), client_id="fake-m2m-client", audience="fake-audience"),
        user=UserSecurity(enabled=False, realm_url=AnyUrl("http://localhost:8080/realms/fake-user-realm"), client_id="fake-user-client"),
        authorized_origins=[AnyHttpUrl("http://localhost:5173")],
    )
    config = Configuration(
        app=AppConfig(
            base_url="/knowledge-flow/v1",
            address="127.0.0.1",
            port=8888,
            log_level="debug",
            reload=False,
            reload_dir=".",
        ),
        security=fake_security_config,
        scheduler=SchedulerConfig(
            enabled=False,
            backend="temporal",
            temporal=TemporalSchedulerConfig(
                host="localhost:7233",
                namespace="default",
                task_queue="ingestion",
                workflow_prefix="test-pipeline",
                connect_timeout_seconds=3,
            ),
        ),
        document_sources={"uploads": PushSourceConfig(type="push", description="Uploaded files for testing")},
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
            resource_store=duckdb,
            tag_store=duckdb,
            kpi_store=duckdb,
            metadata_store=duckdb,
            catalog_store=duckdb,
            tabular_stores={"base_tabular_store": duckdb},
            vector_store=InMemoryVectorStorage(type="in_memory"),
        ),
        content_storage=LocalContentStorageConfig(
            type="local",
            root_path="/tmp/knowledge-flow-test-content",
        ),
        chat_model=ModelConfiguration(
            provider="openai",
            name="gpt-4o",
            settings={"temperature": 0, "max_retries": 1},
        ),
        embedding_model=ModelConfiguration(
            provider="openai",
            name="text-embedding-3-large",
            settings={},
        ),
        processing=ProcessingConfig(
            generate_summary=True,
            use_gpu=True,
            process_images=True,
        ),
        input_processors=[
            ProcessorConfig(
                prefix=".md",
                class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
            )
        ],
        output_processors=[
            ProcessorConfig(
                prefix=".pdf",
                class_path=f"{TestOutputProcessor.__module__}.{TestOutputProcessor.__qualname__}",
            ),
            ProcessorConfig(
                prefix=".docx",
                class_path=f"{TestOutputProcessor.__module__}.{TestOutputProcessor.__qualname__}",
            ),
        ],
    )

    return ApplicationContext(config)


@pytest.fixture(scope="function")
def client_fixture(app_context: ApplicationContext):
    """Returns a test client for FastAPI app."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def content_store(app_context: ApplicationContext):
    return app_context.get_instance().get_content_store()


@pytest.fixture
def metadata_store(app_context: ApplicationContext):
    return app_context.get_instance().get_metadata_store()


@pytest.fixture
def all_tabular_stores(app_context: ApplicationContext):
    return app_context.get_instance().get_tabular_stores()
