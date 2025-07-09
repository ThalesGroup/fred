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
from app.application_context import ApplicationContext
from app.common.structures import Configuration, ContentStorageConfig, EmbeddingConfig, InMemoryVectorStore, KnowledgeContextStorageConfig, KnowledgeContextStorageSettings, LocalMetadataStorage, ProcessorConfig

from app.core.stores.content.content_storage_factory import get_content_store
from app.main import create_app
from fastapi.testclient import TestClient
from langchain_community.embeddings import FakeEmbeddings

from app.core.processors.output.vectorization_processor.embedder import Embedder


@pytest.fixture(scope="function", name="client")
def client_fixture(app_context):  # depends on app_context fixture
    """
    Fixture that provides a test client for the FastAPI application.
    Uses a dummy config_path since ApplicationContext is already initialized in app_context.
    """
    app = create_app(config_path="dummy", base_url="/knowledge-flow/v1")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function", autouse=True)
def app_context(monkeypatch):
    """
    Initializes the application context for testing using local metadata and vector storage.
    This avoids needing environment variables or OpenSearch during test runs.
    """

    ApplicationContext._instance = None  # 🧼 Reset singleton
    # Prevent SystemExit by faking OpenAI key
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    config = Configuration(
        security={
            "enabled": False,
            "keycloak_url": "http://fake",
            "client_id": "test-client",
            "authorized_origins": []
        },
        metadata_storage=LocalMetadataStorage(
            type="local",
            root_path="/tmp/test-metadata-store.json"
        ),
        vector_storage=InMemoryVectorStore(
            type="in_memory"
        ),
        content_storage=ContentStorageConfig(type="local"),
        embedding=EmbeddingConfig(type="openai"),  # ✅ safe default, monkeypatched by `fake_embedder`
        knowledge_context_storage=KnowledgeContextStorageConfig(
            type="local",
            settings=KnowledgeContextStorageSettings(local_path="/tmp")
        ),
        input_processors=[
            ProcessorConfig(
                prefix=".docx",
                class_path="app.core.processors.input.docx_markdown_processor.docx_markdown_processor.DocxMarkdownProcessor",
            ),
            ProcessorConfig(
                prefix=".pdf",
                class_path="app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.PdfMarkdownProcessor",
            ),
            ProcessorConfig(
                prefix=".pptx",
                class_path="app.core.processors.input.pptx_markdown_processor.pptx_markdown_processor.PptxMarkdownProcessor",
            ),
        ],
        knowledge_context_max_tokens=50000
    )

    ApplicationContext(config)


@pytest.fixture(scope="function", autouse=True)
def fake_embedder(monkeypatch):
    """
    Monkeypatches the Embedder class's __init__ method to use a fake embedder for testing purposes.
    This function replaces the original __init__ method of the Embedder class in
    'app.core.processors.output.vectorization_processor.embedder' with a fake implementation
    that initializes the model attribute with a FakeEmbeddings instance of size 1352.

    Args:
        monkeypatch: pytest's monkeypatch fixture used to modify or replace attributes for testing.
    """

    def fake_embedder_init(self, config=None):
        self.model = FakeEmbeddings(size=1352)

    monkeypatch.setattr(
        Embedder,
        "__init__", fake_embedder_init)

@pytest.fixture
def content_store(tmp_path):
    return get_content_store()

@pytest.fixture
def metadata_store(app_context):
    return ApplicationContext.get_instance().get_metadata_store()

@pytest.fixture(autouse=True)
def _clear_stores_between_tests(metadata_store, content_store):
    """
    Wipe the in-memory Local*Store instances before **every** test so each case
    starts with a clean slate.
    """
    # ――― test starts ―――
    metadata_store.clear()      
    content_store.clear()        
    yield
    # ――― test ends ―――

