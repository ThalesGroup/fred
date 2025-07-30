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
from langchain_community.embeddings import FakeEmbeddings

from app.application_context import ApplicationContext
from app.common.structures import (
    AppConfig,
    Configuration,
    DuckdbMetadataStorage,
    EmbeddingConfig,
    InMemoryVectorStorage,
    LocalContentStorage,
    LocalTagStore,
    ProcessorConfig,
    DuckDBTabularStorage,
    PushSourceConfig,
    SchedulerConfig,
    TemporalSchedulerConfig,
)
from app.main import create_app
from app.core.processors.output.vectorization_processor.embedder import Embedder
from app.tests.test_utils.test_processors import TestOutputProcessor, TestMarkdownProcessor, TestTabularProcessor


@pytest.fixture(scope="function", autouse=True)
def fake_embedder(monkeypatch):
    """
    Monkeypatch the Embedder to avoid real API calls during tests.
    """

    def fake_embedder_init(self, config=None):
        self.model = FakeEmbeddings(size=1352)

    monkeypatch.setattr(Embedder, "__init__", fake_embedder_init)


@pytest.fixture(scope="function", autouse=True)
def app_context(monkeypatch, fake_embedder):
    """
    Initializes the ApplicationContext with fake storage and a test vector store.
    """
    ApplicationContext._instance = None  # 🧼 Reset singleton

    monkeypatch.setenv("OPENAI_API_KEY", "test")  # Avoid system exit due to missing API key

    config = Configuration(
        app=AppConfig(
            base_url="/knowledge-flow/v1",
            address="127.0.0.1",
            port=8888,
            log_level="info",
            reload=False,
            reload_dir=".",
        ),
        security={
            "enabled": False,
            "keycloak_url": "http://fake",
            "client_id": "test-client",
            "authorized_origins": [],
        },
        scheduler=SchedulerConfig(
            backend="temporal",
            enabled=False,
            temporal=TemporalSchedulerConfig(
                host="localhost:7233",
                namespace="default",
                task_queue="ingestion",
                workflow_prefix="test-pipeline",
                connect_timeout_seconds=3,
            ),
        ),
        document_sources={
            "uploads": PushSourceConfig(type="push", description="User uploaded files"),
        },
        metadata_storage=DuckdbMetadataStorage(type="duckdb", duckdb_path="/tmp/testdb.duckdb"),
        vector_storage=InMemoryVectorStorage(type="in_memory"),
        content_storage=LocalContentStorage(type="local", root_path="/tmp/content"),
        tabular_storage=DuckDBTabularStorage(type="duckdb", duckdb_path="/tmp/testdb.duckdb"),
        catalog_storage=DuckDBTabularStorage(type="duckdb", duckdb_path="/tmp/testdb.duckdb"),
        embedding=EmbeddingConfig(type="openai"),
        tag_storage=LocalTagStore(type="local"),
        input_processors=[
            ProcessorConfig(
                prefix=".docx",
                class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
            ),
            ProcessorConfig(
                prefix=".pdf",
                class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
            ),
            ProcessorConfig(
                prefix=".xlsx",
                class_path=f"{TestMarkdownProcessor.__module__}.{TestTabularProcessor.__qualname__}",
            ),
            ProcessorConfig(
                prefix=".md",
                class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
            ),
            ProcessorConfig(
                prefix=".csv",
                class_path=f"{TestMarkdownProcessor.__module__}.{TestTabularProcessor.__qualname__}",
            ),
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
    """
    TestClient for FastAPI app. ApplicationContext is preloaded.
    """
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def content_store(app_context: ApplicationContext):
    """
    Returns the content store after ApplicationContext is initialized.
    """
    return app_context.get_instance().get_content_store()


@pytest.fixture
def tabular_store(app_context: ApplicationContext):
    """
    Returns the content store after ApplicationContext is initialized.
    """
    return app_context.get_instance().get_tabular_store()


@pytest.fixture
def metadata_store(app_context: ApplicationContext):
    """
    Returns the metadata store from the initialized ApplicationContext.
    """
    return app_context.get_instance().get_metadata_store()
