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

from unittest.mock import MagicMock
import pytest
from app.application_context import ApplicationContext
from app.common.structures import Configuration, ContentStorageConfig, EmbeddingConfig, MetadataStorageConfig, ProcessorConfig, VectorStorageConfig

from app.core.stores.content.content_storage_factory import get_content_store
from app.core.stores.content.minio_content_store import MinioContentStore
from app.core.stores.metadata.metadata_storage_factory import get_metadata_store
from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore
from app.main import create_app
from fastapi.testclient import TestClient
from opensearchpy.exceptions import NotFoundError
from langchain_community.embeddings import FakeEmbeddings
from minio.error import S3Error


@pytest.fixture(scope="session", name="client")
def client_fixture():
    """
    Fixture that provides a test client for the FastAPI application.
    This fixture resets the ApplicationContext singleton, creates a new FastAPI app instance,
    and yields a TestClient for use in tests. Ensures that each test gets a fresh application context.

    Yields:
        TestClient: An instance of FastAPI's TestClient for making requests to the app during tests.
    """

    ApplicationContext._instance = None
    app = create_app()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function", autouse=True)
def app_context(request):
    """
    Initializes and configures the application context for testing.
    This function resets the ApplicationContext singleton and sets up a new configuration
    for the application, allowing test cases to override storage types via pytest markers.
    The configuration includes security settings, storage backends (content, metadata, vector),
    embedding configuration, and input processors for various file types.

    Args:
        request: The pytest request object, used to access test markers for overriding
                 storage types.
    Side Effects:
        - Resets the ApplicationContext singleton instance.
        - Instantiates a new ApplicationContext with the specified configuration.
    Pytest Markers Supported:
        - metadata_storage_type(type="..."): Override the metadata storage backend. (opensearch, local)
        - content_storage_type(type="..."): Override the content storage backend. (minio, local)
        - vector_storage_type(type="..."): Override the vector storage backend. (opensearch, in_memory)
    """

    # 🧼 Force reset the singleton before initializing
    ApplicationContext._instance = None

    # Default config
    content_storage_type = "local"
    metadata_storage_type = "local"
    vector_storage_type = "in_memory"

    # Allow test to override via marker
    marker_metadata_storage_type = request.node.get_closest_marker("metadata_storage_type")
    if marker_metadata_storage_type and "type" in marker_metadata_storage_type.kwargs:
        metadata_storage_type = marker_metadata_storage_type.kwargs["type"]

    marker_content_storage_type = request.node.get_closest_marker("content_storage_type")
    if marker_content_storage_type and "type" in marker_content_storage_type.kwargs:
        content_storage_type = marker_content_storage_type.kwargs["type"]

    marker_vector_storage_type = request.node.get_closest_marker("vector_storage_type")
    if marker_vector_storage_type and "type" in marker_vector_storage_type.kwargs:
        vector_storage_type = marker_vector_storage_type.kwargs["type"]

    config = Configuration(
        security={
            "enabled": False,
            "keycloak_url": "http://fake",
            "client_id": "test-client",
        },
        content_storage=ContentStorageConfig(type=content_storage_type),
        metadata_storage=MetadataStorageConfig(type=metadata_storage_type),
        vector_storage=VectorStorageConfig(type=vector_storage_type),
        embedding=EmbeddingConfig(type="openai"),
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
    )

    ApplicationContext(config)


@pytest.fixture(scope="function")
def opensearch_metadata_store():
    """
    Fixture that provides an instance of OpenSearchMetadataStore for testing.
    This fixture initializes the OpenSearch metadata store, creates the required vector index,
    and yields the store instance for use in tests. After the test completes, it attempts to
    delete both the metadata and vector indices to clean up. If the indices do not exist,
    the NotFoundError is caught and ignored.

    Yields:
        OpenSearchMetadataStore: An initialized metadata store connected to OpenSearch.
    """

    opensearch_metadata_store: OpenSearchMetadataStore = get_metadata_store()
    opensearch_metadata_store.client.indices.create(index=opensearch_metadata_store.vector_index_name, ignore=400)

    yield opensearch_metadata_store

    try:
        opensearch_metadata_store.client.indices.delete(index=opensearch_metadata_store.metadata_index_name)
        opensearch_metadata_store.client.indices.delete(index=opensearch_metadata_store.vector_index_name)
    except NotFoundError:
        pass


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

    monkeypatch.setattr("app.core.processors.output.vectorization_processor.embedder.Embedder.__init__", fake_embedder_init)


@pytest.fixture(scope="function")
def minio_content_store():
    """
    Fixture providing a MinioContentStore instance for testing.
    This fixture sets up a MinioContentStore instance and handles cleanup after tests by:
    1. Removing all objects in the bucket
    2. Removing the bucket itself

    Yields:
        MinioContentStore: A configured MinioContentStore instance for testing
    Raises:
        S3Error: Suppressed if cleanup operations fail
    """
    try:
        minio_content_store: MinioContentStore = get_content_store()

        yield minio_content_store

        try:
            objects = minio_content_store.client.list_objects(minio_content_store.bucket_name, recursive=True)
            for obj in objects:
                minio_content_store.client.remove_object(minio_content_store.bucket_name, obj.object_name)

            minio_content_store.client.remove_bucket(minio_content_store.bucket_name)

        except S3Error:
            pass
    except Exception:
        pytest.skip("MinIO server not available - test skipped.")


@pytest.fixture(scope="function")
def mocked_minio_content_store(monkeypatch):
    """
    Mock MinioContentStore when no real MinIO server is available.
    """
    mock_store = MagicMock()

    # Simule un stockage en mémoire
    store_dict = {}

    def put(path, data):
        store_dict[path] = data

    def get(path):
        return store_dict.get(path, b"")

    def exists(path):
        return path in store_dict

    def remove(path):
        store_dict.pop(path, None)

    mock_store.put.side_effect = put
    mock_store.get.side_effect = get
    mock_store.exists.side_effect = exists
    mock_store.remove.side_effect = remove
    mock_store.bucket_name = "mock-bucket"

    yield mock_store


@pytest.fixture(scope="function")
def safe_minio_content_store(request, minio_content_store, mocked_minio_content_store):
    """
    Returns either the real or the mocked MinioContentStore.
    Use @pytest.mark.mock_minio to force the mock version.
    """
    if request.node.get_closest_marker("mock_minio"):
        return mocked_minio_content_store
    return minio_content_store
