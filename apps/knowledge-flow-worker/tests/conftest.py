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
from fred_core.common import ModelConfiguration, OpenSearchStoreConfig, PostgresStoreConfig
from fred_core.common.structures import KpiObservabilityConfig, KpiOpenSearchSinkConfig
from fred_core.documents.document_structures import DocumentMetadata
from langchain_community.embeddings import FakeEmbeddings
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_worker.application_context import ApplicationContext
from knowledge_flow_worker.common.structures import (
    AppConfig,
    Configuration,
    IngestionProcessingProfile,
    ObservabilityConfig,
    PgVectorStorageConfig,
    ProcessingConfig,
    ProcessorConfig,
    SchedulerConfig,
    StorageConfig,
    TemporalSchedulerConfig,
)
from knowledge_flow_worker.core.processors.output.vectorization_processor.embedder import Embedder
from tests.services.artifact_store import TestArtifactStore

from .test_utils.test_processors import TestDocxProcessor, TestMarkdownProcessor, TestOutputProcessor


class _InMemoryTestMetadataStore:
    def __init__(self) -> None:
        self._items: dict[str, DocumentMetadata] = {}

    async def get_all_metadata(self, filters: dict, session=None) -> list[DocumentMetadata]:
        return [document.model_copy(deep=True) for document in self._items.values()]

    async def get_metadata_by_uids(self, document_uids):
        return [self._items[uid].model_copy(deep=True) for uid in document_uids if uid in self._items]

    async def get_metadata_by_uid(self, document_uid: str, session=None) -> DocumentMetadata | None:
        item = self._items.get(document_uid)
        return item.model_copy(deep=True) if item else None

    async def save_metadata(self, metadata: DocumentMetadata, session=None) -> None:
        self._items[metadata.document_uid] = metadata.model_copy(deep=True)

    async def clear(self, session=None) -> None:
        self._items.clear()


@pytest.fixture(scope="function", autouse=True)
def fake_embedder(monkeypatch):
    """Monkeypatch the Embedder to avoid real API calls."""

    def fake_init(self, config=None):
        self.model = FakeEmbeddings(size=1352)

    monkeypatch.setattr(Embedder, "__init__", fake_init)


@pytest.fixture(scope="function", autouse=True)
def app_context(monkeypatch, fake_embedder, tmp_path):
    """Initialize configuration and test-only artifact/metadata doubles."""
    ApplicationContext._instance = None
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    # OpenSearchStoreConfig sources its password from this env var; set it so the
    # config below builds without reaching OpenSearch (unit-level, no integration).
    monkeypatch.setenv("OPENSEARCH_PASSWORD", "test")  # pragma: allowlist secret

    config = Configuration(
        app=AppConfig(
            base_url="/knowledge-flow/v2",
            address="127.0.0.1",
            port=8888,
            log_level="debug",
            reload=False,
            reload_dir=".",
        ),
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
            default_profile=IngestionProcessingProfile.medium,
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
        observability=ObservabilityConfig(
            kpi=KpiObservabilityConfig(
                opensearch=KpiOpenSearchSinkConfig(enabled=False),
            )
        ),
    )

    ctx = ApplicationContext(config)
    ctx.test_metadata_store = _InMemoryTestMetadataStore()
    ctx._content_store_instance = TestArtifactStore(tmp_path / "artifacts")
    # Production opens the published engine at API startup; unit tests allow all.
    return ctx


@pytest_asyncio.fixture
async def sqlite_engine(tmp_path):
    """Close SQLite connections before pytest tears down the owning event loop."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def content_store(app_context: ApplicationContext):
    return app_context.get_instance().get_content_store()


@pytest.fixture
def metadata_store(app_context: ApplicationContext):
    return app_context.get_instance().test_metadata_store
