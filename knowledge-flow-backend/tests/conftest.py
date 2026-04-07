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


import os

import pytest
from fastapi.testclient import TestClient
from fred_core import (
    M2MSecurity,
    SecurityConfiguration,
    UserSecurity,
)
from fred_core.common import (
    DuckdbStoreConfig,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
)
from langchain_community.embeddings import FakeEmbeddings
from pydantic import AnyHttpUrl, AnyUrl

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.common.structures import (
    AppConfig,
    Configuration,
    IngestionProcessingProfile,
    InMemoryVectorStorage,
    LocalContentStorageConfig,
    LocalFilesystemConfig,
    ProcessingConfig,
    ProcessorConfig,
    PushSourceConfig,
    SchedulerConfig,
    StorageConfig,
    TemporalSchedulerConfig,
)
from knowledge_flow_backend.core.processors.output.vectorization_processor.embedder import Embedder
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
)
from knowledge_flow_backend.main import create_app

from .test_utils.test_processors import TestDocxProcessor, TestMarkdownProcessor, TestOutputProcessor


class _InMemoryTestMetadataStore(BaseMetadataStore):
    def __init__(self) -> None:
        self._items: dict[str, DocumentMetadata] = {}

    async def get_all_metadata(self, filters: dict, session=None) -> list[DocumentMetadata]:
        docs = list(self._items.values())
        if not filters:
            return [d.model_copy(deep=True) for d in docs]

        def _matches(doc: DocumentMetadata) -> bool:
            for key, expected in filters.items():
                if key == "source_tag":
                    if doc.source_tag != expected:
                        return False
                    continue
                if key == "tags":
                    tag_names = list(getattr(doc.tags, "tag_names", []) or [])
                    if isinstance(expected, list):
                        if not all(v in tag_names for v in expected):
                            return False
                    elif expected not in tag_names:
                        return False
                    continue
                actual = getattr(doc, key, None)
                if actual != expected:
                    return False
            return True

        return [d.model_copy(deep=True) for d in docs if _matches(d)]

    async def get_metadata_by_uid(self, document_uid: str, session=None) -> DocumentMetadata | None:
        item = self._items.get(document_uid)
        return item.model_copy(deep=True) if item else None

    async def get_metadata_in_tag(self, tag_id: str, session=None) -> list[DocumentMetadata]:
        out: list[DocumentMetadata] = []
        for doc in self._items.values():
            tag_ids = list(getattr(doc.tags, "tag_ids", []) or [])
            tag_names = list(getattr(doc.tags, "tag_names", []) or [])
            if tag_id in tag_ids or tag_id in tag_names:
                out.append(doc.model_copy(deep=True))
        return out

    async def list_by_source_tag(self, source_tag: str, session=None) -> list[DocumentMetadata]:
        return [doc.model_copy(deep=True) for doc in self._items.values() if doc.source_tag == source_tag]

    async def save_metadata(self, metadata: DocumentMetadata, session=None) -> None:
        self._items[metadata.document_uid] = metadata.model_copy(deep=True)

    async def delete_metadata(self, document_uid: str, session=None) -> None:
        self._items.pop(document_uid, None)

    async def clear(self, session=None) -> None:
        self._items.clear()


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
        rebac=None,
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
                workflow_id_prefix="test-pipeline",
                connect_timeout_seconds=3,
            ),
        ),
        document_sources={
            "uploads": PushSourceConfig(type="push", description="Uploaded files for testing"),
            # Include 'fred' as a valid push source for ingestion tests
            "fred": PushSourceConfig(type="push", description="Manual ingestion test source"),
        },
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
            default_profile=IngestionProcessingProfile.MEDIUM,
            profiles=ProcessingConfig.ProfilesConfig(
                fast=ProcessingConfig.ProfileConfig(
                    use_gpu=False,
                    generate_summary=False,
                    process_images=False,
                    input_processors=[
                        ProcessingConfig.ProfileInputProcessorConfig(
                            suffix=".md",
                            class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
                            description="Test markdown input processor for unit tests",
                        ),
                        ProcessingConfig.ProfileInputProcessorConfig(
                            suffix=".docx",
                            class_path=f"{TestDocxProcessor.__module__}.{TestDocxProcessor.__qualname__}",
                            description="Test docx input processor for unit tests",
                        ),
                    ],
                ),
                medium=ProcessingConfig.ProfileConfig(
                    use_gpu=False,
                    generate_summary=False,
                    process_images=False,
                    input_processors=[
                        ProcessingConfig.ProfileInputProcessorConfig(
                            suffix=".md",
                            class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
                            description="Test markdown input processor for unit tests",
                        ),
                        ProcessingConfig.ProfileInputProcessorConfig(
                            suffix=".docx",
                            class_path=f"{TestDocxProcessor.__module__}.{TestDocxProcessor.__qualname__}",
                            description="Test docx input processor for unit tests",
                        ),
                    ],
                ),
                rich=ProcessingConfig.ProfileConfig(
                    use_gpu=False,
                    generate_summary=False,
                    process_images=False,
                    input_processors=[
                        ProcessingConfig.ProfileInputProcessorConfig(
                            suffix=".md",
                            class_path=f"{TestMarkdownProcessor.__module__}.{TestMarkdownProcessor.__qualname__}",
                            description="Test markdown input processor for unit tests",
                        ),
                        ProcessingConfig.ProfileInputProcessorConfig(
                            suffix=".docx",
                            class_path=f"{TestDocxProcessor.__module__}.{TestDocxProcessor.__qualname__}",
                            description="Test docx input processor for unit tests",
                        ),
                    ],
                ),
            ),
        ),
        output_processors=[
            ProcessorConfig(
                suffix=".pdf",
                class_path=f"{TestOutputProcessor.__module__}.{TestOutputProcessor.__qualname__}",
                description="Test output processor for pdf files",
            ),
            ProcessorConfig(
                suffix=".docx",
                class_path=f"{TestOutputProcessor.__module__}.{TestOutputProcessor.__qualname__}",
                description="Test output processor for docx files",
            ),
        ],
        filesystem=LocalFilesystemConfig(type="local", root="/tmp/knowledge-flow-test-fs"),
    )

    os.makedirs("/tmp/knowledge-flow-test-fs", exist_ok=True)

    ctx = ApplicationContext(config)
    ctx._metadata_store_instance = _InMemoryTestMetadataStore()
    return ctx


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
