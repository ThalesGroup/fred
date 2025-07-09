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
    Configuration,
    ContentStorageConfig,
    EmbeddingConfig,
    InMemoryVectorStorage,
    KnowledgeContextStorageConfig,
    LocalMetadataStorage,
    ProcessorConfig,
)
from app.core.stores.vector.in_memory_langchain_vector_store import InMemoryLangchainVectorStore
from app.core.stores.content.content_storage_factory import get_content_store
from app.main import create_app
from app.core.processors.output.vectorization_processor.embedder import Embedder
from app.tests.test_utils.test_processors import TestMarkdownProcessor, TestTabularProcessor


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
        security={
            "enabled": False,
            "keycloak_url": "http://fake",
            "client_id": "test-client",
            "authorized_origins": [],
        },
        metadata_storage=LocalMetadataStorage(
            type="local",
            root_path="/tmp/test-metadata-store.json",
        ),
        vector_storage=InMemoryVectorStorage(type="in_memory"),
        content_storage=ContentStorageConfig(type="local"),
        embedding=EmbeddingConfig(type="openai"),
        knowledge_context_storage=KnowledgeContextStorageConfig(
            type="local",
            local_path="/tmp",
        ),
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
        knowledge_context_max_tokens=50000,
    )

    ApplicationContext(config)


@pytest.fixture(scope="function")
def client_fixture(app_context):
    """
    TestClient for FastAPI app. ApplicationContext is preloaded.
    """
    app = create_app(config_path="dummy", base_url="/knowledge-flow/v1")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def content_store(app_context, tmp_path):
    """
    Returns the content store after ApplicationContext is initialized.
    """
    return get_content_store()


@pytest.fixture
def metadata_store(app_context):
    """
    Returns the metadata store from the initialized ApplicationContext.
    """
    return ApplicationContext.get_instance().get_metadata_store()

