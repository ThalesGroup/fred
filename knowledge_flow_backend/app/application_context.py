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

import importlib
import logging
import os
from pathlib import Path
from typing import Dict, Type, Union, Optional
from fred_core import LogStoreConfig, OpenSearchIndexConfig, DuckdbStoreConfig, OpenSearchKPIStore, BaseKPIStore, KpiLogStore, split_realm_url
from opensearchpy import OpenSearch, RequestsHttpConnection
from app.core.stores.catalog.opensearch_catalog_store import OpenSearchCatalogStore
from app.core.stores.content.base_content_loader import BaseContentLoader
from app.core.stores.content.filesystem_content_loader import FileSystemContentLoader
from app.core.stores.content.minio_content_loader import MinioContentLoader
from fred_core.store.sql_store import SQLTableStore
from fred_core.store.structures import StoreInfo

from fred_core.common.structures import SQLStorageConfig
from app.common.structures import (
    Configuration,
    EmbeddingProvider,
    InMemoryVectorStorage,
    FileSystemPullSource,
    LocalContentStorageConfig,
    MinioPullSource,
    MinioStorageConfig,
    WeaviateVectorStorage,
)
from fred_core import KPIWriter
from app.common.utils import validate_settings_or_exit
from app.config.embedding_azure_apim_settings import EmbeddingAzureApimSettings
from app.config.embedding_azure_openai_settings import EmbeddingAzureOpenAISettings
from app.config.ollama_settings import OllamaSettings
from app.config.embedding_openai_settings import EmbeddingOpenAISettings
from app.core.stores.content.base_content_store import BaseContentStore
from app.core.stores.content.filesystem_content_store import FileSystemContentStore
from app.core.stores.content.minio_content_store import MinioStorageBackend
from app.core.stores.catalog.base_catalog_store import BaseCatalogStore
from app.core.stores.catalog.duckdb_catalog_store import DuckdbCatalogStore
from app.core.stores.files.base_file_store import BaseFileStore
from app.core.stores.files.local_file_store import LocalFileStore
from app.core.stores.files.minio_file_store import MinioFileStore
from app.core.stores.metadata.duckdb_metadata_store import DuckdbMetadataStore
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings

from app.core.processors.input.common.base_input_processor import BaseInputProcessor, BaseMarkdownProcessor, BaseTabularProcessor
from app.core.processors.output.base_output_processor import BaseOutputProcessor
from app.core.processors.output.vectorization_processor.azure_apim_embedder import AzureApimEmbedder
from app.core.processors.output.vectorization_processor.embedder import Embedder
from app.core.stores.metadata.base_metadata_store import BaseMetadataStore
from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore
from app.core.stores.resources.base_resource_store import BaseResourceStore
from app.core.stores.resources.duckdb_resource_store import DuckdbResourceStore
from app.core.stores.resources.opensearch_resource_store import OpenSearchResourceStore
from app.core.stores.tags.base_tag_store import BaseTagStore
from app.core.stores.tags.duckdb_tag_store import DuckdbTagStore
from app.core.stores.tags.opensearch_tags_store import OpenSearchTagStore
from app.core.stores.vector.in_memory_langchain_vector_store import InMemoryLangchainVectorStore
from app.core.stores.vector.base_vector_store import BaseEmbeddingModel, BaseTextSplitter, BaseVectoreStore
from app.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from app.core.processors.output.vectorization_processor.semantic_splitter import SemanticSplitter

# Union of supported processor base classes
BaseProcessorType = Union[BaseMarkdownProcessor, BaseTabularProcessor]

# Default mapping for output processors by category
DEFAULT_OUTPUT_PROCESSORS = {
    "markdown": "app.core.processors.output.vectorization_processor.vectorization_processor.VectorizationProcessor",
    "tabular": "app.core.processors.output.tabular_processor.tabular_processor.TabularProcessor",
}

# Mapping file extensions to categories
EXTENSION_CATEGORY = {
    ".pdf": "markdown",
    ".docx": "markdown",
    ".pptx": "markdown",
    ".txt": "markdown",
    ".md": "markdown",
    ".csv": "tabular",
    ".xlsx": "tabular",
    ".xls": "tabular",
    ".xlsm": "tabular",
    ".duckdb": "duckdb",
    ".jsonl": "markdown",
}

logger = logging.getLogger(__name__)


def _mask(value: Optional[str], left: int = 4, right: int = 4) -> str:
    if not value:
        return "<empty>"
    if len(value) <= left + right:
        return "<hidden>"
    return f"{value[:left]}…{value[-right:]}"


def get_configuration() -> Configuration:
    """
    Retrieves the global application configuration.

    Returns:
        Configuration: The singleton application configuration.
    """
    return get_app_context().configuration


def get_kpi_writer() -> KPIWriter:
    """
    Retrieves the global KPI writer instance.

    Returns:
        KPIWriter: The singleton KPI writer instance.
    """
    return get_app_context().get_kpi_writer()


def get_app_context() -> "ApplicationContext":
    """
    Retrieves the global application context instance.

    Returns:
        ApplicationContext: The singleton application context.

    Raises:
        RuntimeError: If the context has not been initialized yet.
    """
    if ApplicationContext._instance is None:
        raise RuntimeError("ApplicationContext is not yet initialized")
    return ApplicationContext._instance


def validate_input_processor_config(config: Configuration):
    """Ensure all input processor classes can be imported and subclass BaseProcessor."""
    for entry in config.input_processors:
        module_path, class_name = entry.class_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            if not issubclass(cls, BaseInputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseProcessor")
            logger.debug(f"Validated input processor: {entry.class_path} for prefix: {entry.prefix}")
        except (ImportError, AttributeError, TypeError) as e:
            raise ImportError(f"Input Processor '{entry.class_path}' could not be loaded: {e}")


def validate_output_processor_config(config: Configuration):
    """Ensure all output processor classes can be imported and subclass BaseProcessor."""
    if not config.output_processors:
        return
    for entry in config.output_processors:
        module_path, class_name = entry.class_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            if not issubclass(cls, BaseOutputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseProcessor")
            logger.debug(f"Validated output processor: {entry.class_path} for prefix: {entry.prefix}")
        except (ImportError, AttributeError, TypeError) as e:
            raise ImportError(f"Output Processor '{entry.class_path}' could not be loaded: {e}")


class ApplicationContext:
    _instance: Optional["ApplicationContext"] = None
    configuration: Configuration
    _input_processor_instances: Dict[str, BaseInputProcessor] = {}
    _output_processor_instances: Dict[str, BaseOutputProcessor] = {}
    _vector_store_instance: Optional[BaseVectoreStore] = None
    _metadata_store_instance: Optional[BaseMetadataStore] = None
    _tag_store_instance: Optional[BaseTagStore] = None
    _kpi_store_instance: Optional[BaseKPIStore] = None
    _opensearch_client: Optional[OpenSearch] = None
    _resource_store_instance: Optional[BaseResourceStore] = None
    _tabular_stores: Optional[Dict[str, StoreInfo]] = None
    _catalog_store_instance: Optional[BaseCatalogStore] = None
    _file_store_instance: Optional[BaseFileStore] = None
    _kpi_writer: Optional[KPIWriter] = None

    def __init__(self, configuration: Configuration):
        # Allow reuse if already initialized with same config
        if ApplicationContext._instance is not None:
            # Optionally: log or assert config equality here
            return

        self.configuration = configuration
        validate_input_processor_config(configuration)
        validate_output_processor_config(configuration)
        self.input_processor_registry: Dict[str, Type[BaseInputProcessor]] = self._load_input_processor_registry()
        self.output_processor_registry: Dict[str, Type[BaseOutputProcessor]] = self._load_output_processor_registry()
        ApplicationContext._instance = self
        self._log_config_summary()

    def is_tabular_file(self, file_name: str) -> bool:
        """
        Returns True if the file is handled by a tabular input processor.
        This allows detecting if a file is meant to be stored in a SQL/structured store like DuckDB.
        """
        ext = Path(file_name).suffix.lower()
        try:
            processor = self.get_input_processor_instance(ext)
            return isinstance(processor, BaseTabularProcessor)
        except ValueError:
            return False

    def get_output_processor_instance(self, extension: str) -> BaseOutputProcessor:
        """
        Get an instance of the output processor for a given file extension.
        This method ensures that the processor is instantiated only once per class path.
        Args:
            extension (str): The file extension for which to get the processor.
        Returns:
            BaseOutputProcessor: An instance of the output processor.
        Raises:
            ValueError: If no processor is found for the given extension.
        """
        processor_class = self._get_output_processor_class(extension)

        if processor_class is None:
            raise ValueError(f"No output processor found for extension '{extension}'")

        class_path = f"{processor_class.__module__}.{processor_class.__name__}"

        if class_path not in self._output_processor_instances:
            logger.debug(f"Creating new instance of output processor: {class_path}")
            self._output_processor_instances[class_path] = processor_class()

        return self._output_processor_instances[class_path]

    def get_input_processor_instance(self, extension: str) -> BaseInputProcessor:
        """
        Get an instance of the input processor for a given file extension.
        This method ensures that the processor is instantiated only once per class path.
        Args:
            extension (str): The file extension for which to get the processor.
        Returns:
            BaseInputProcessor: An instance of the input processor.
        Raises:
            ValueError: If no processor is found for the given extension.
        """
        processor_class = self._get_input_processor_class(extension)

        if processor_class is None:
            raise ValueError(f"No input processor found for extension '{extension}'")

        class_path = f"{processor_class.__module__}.{processor_class.__name__}"

        if class_path not in self._input_processor_instances:
            logger.debug(f"Creating new instance of input processor: {class_path}")
            self._input_processor_instances[class_path] = processor_class()

        return self._input_processor_instances[class_path]

    @classmethod
    def get_instance(cls) -> "ApplicationContext":
        """
        Get the singleton instance of ApplicationContext. It provides access to the
        configuration and processor registry.
        Raises:
            RuntimeError: If the ApplicationContext is not initialized.
        """
        if cls._instance is None:
            raise RuntimeError("ApplicationContext is not initialized yet.")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (used in tests)."""
        cls._instance = None

    def _load_input_processor_registry(self) -> Dict[str, Type[BaseInputProcessor]]:
        registry = {}
        for entry in self.configuration.input_processors:
            cls = self._dynamic_import(entry.class_path)
            if not issubclass(cls, BaseInputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseProcessor")
            logger.debug(f"Loaded input processor: {entry.class_path} for prefix: {entry.prefix}")
            registry[entry.prefix.lower()] = cls
        return registry

    def _load_output_processor_registry(self) -> Dict[str, Type[BaseOutputProcessor]]:
        registry = {}
        if not self.configuration.output_processors:
            return registry
        for entry in self.configuration.output_processors:
            cls = self._dynamic_import(entry.class_path)
            if not issubclass(cls, BaseOutputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseOutputProcessor")
            logger.debug(f"Loaded output processor: {entry.class_path} for prefix: {entry.prefix}")
            registry[entry.prefix.lower()] = cls
        return registry

    def get_config(self) -> Configuration:
        return self.configuration

    def _get_input_processor_class(self, extension: str) -> Optional[Type[BaseInputProcessor]]:
        """
        Get the input processor class for a given file extension. The mapping is
        defined in the configuration.yaml file.
        Args:
            extension (str): The file extension for which to get the processor class.
        Returns:
            Optional[Type[BaseInputProcessor]]: The input processor class, or None if not found.
        """
        return self.input_processor_registry.get(extension.lower())

    def _get_output_processor_class(self, extension: str) -> Optional[Type[BaseOutputProcessor]]:
        """
        Get the output processor class for a given file extension. The mapping is
        defined in the configuration.yaml file but defaults may be used.
        Args:
            extension (str): The file extension for which to get the processor class.
        Returns:
            Optional[Type[BaseOutputProcessor]]: The output processor class, or None if not found.
        """
        processor_class = self.output_processor_registry.get(extension.lower())
        if processor_class:
            return processor_class

        # Else fallback: infer category and default processor
        category = EXTENSION_CATEGORY.get(extension.lower())
        if category:
            default_class_path = DEFAULT_OUTPUT_PROCESSORS.get(category)
            if default_class_path:
                return self._dynamic_import(default_class_path)

        raise ValueError(f"No output processor found for extension '{extension}'")

    def _dynamic_import(self, class_path: str) -> Type:
        """Helper to dynamically import a class from its full path."""
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls

    def get_content_store(self) -> BaseContentStore:
        """
        Factory function to get the appropriate storage backend based on configuration.
        Returns:
            BaseContentStore: An instance of the storage backend.
        """
        # Get the singleton application context and configuration
        config = ApplicationContext.get_instance().get_config().content_storage
        backend_type = config.type

        if isinstance(config, MinioStorageConfig):
            bucket = f"{config.bucket_name}-documents"
            return MinioStorageBackend(endpoint=config.endpoint, access_key=config.access_key, secret_key=config.secret_key, bucket_name=bucket, secure=config.secure)
        elif isinstance(config, LocalContentStorageConfig):
            root = Path(config.root_path).expanduser() / "documents"
            return FileSystemContentStore(Path(root).expanduser())
        else:
            raise ValueError(f"Unsupported storage backend: {backend_type}")

    def get_file_store(self) -> BaseFileStore:
        """
        Return a simple file store.
        Returns:
            BaseContentStore: An instance of the storage backend.
        """
        # Get the singleton application context and configuration
        if self._file_store_instance:
            return self._file_store_instance

        config = ApplicationContext.get_instance().get_config().content_storage
        backend_type = config.type

        if isinstance(config, MinioStorageConfig):
            self._file_store_instance = MinioFileStore(endpoint=config.endpoint, access_key=config.access_key, secret_key=config.secret_key, bucket_name=config.bucket_name, secure=config.secure)
        elif isinstance(config, LocalContentStorageConfig):
            self._file_store_instance = LocalFileStore(Path(config.root_path).expanduser())
        else:
            raise ValueError(f"Unsupported file backend: {backend_type}")
        return self._file_store_instance

    def get_embedder(self) -> BaseEmbeddingModel:
        """
        Factory method to create an embedding model instance based on the configuration.
        Supports Azure OpenAI and OpenAI.
        """
        backend_type = self.configuration.embedding.type

        if backend_type == EmbeddingProvider.OPENAI:
            settings = EmbeddingOpenAISettings()  # type: ignore[call-arg]
            embedding_params = {
                "model": settings.openai_model_name,
                "openai_api_key": settings.openai_api_key,
                "openai_api_base": settings.openai_api_base,
                "openai_api_type": "openai",  # always "openai" for pure OpenAI
            }

            # Only add api_version if it exists
            if settings.openai_api_version:
                embedding_params["openai_api_version"] = settings.openai_api_version

            return Embedder(OpenAIEmbeddings(**embedding_params))  # type: ignore[call-arg]

        elif backend_type == EmbeddingProvider.AZUREOPENAI:
            openai_settings = EmbeddingAzureOpenAISettings()  # type: ignore[call-arg]
            return Embedder(
                AzureOpenAIEmbeddings(
                    deployment=openai_settings.azure_deployment_embedding,
                    openai_api_type="azure",
                    azure_endpoint=openai_settings.azure_openai_endpoint,
                    openai_api_version=openai_settings.azure_api_version,
                    openai_api_key=openai_settings.azure_openai_api_key,
                )
            )  # type: ignore[call-arg]

        elif backend_type == EmbeddingProvider.AZUREAPIM:
            settings = validate_settings_or_exit(EmbeddingAzureApimSettings, "Azure APIM Embedding Settings")
            return AzureApimEmbedder(settings)

        elif backend_type == EmbeddingProvider.OLLAMA:
            ollama_settings = OllamaSettings()
            embedding_params = {
                "model": ollama_settings.embedding_model_name,
            }
            if ollama_settings.api_url:
                embedding_params["base_url"] = ollama_settings.api_url

            return Embedder(OllamaEmbeddings(**embedding_params))

        else:
            raise ValueError(f"Unsupported embedding backend: {backend_type}")

    def get_vector_store(self) -> BaseVectoreStore:
        """
        Vector Store Factory
        """
        if self._vector_store_instance is not None:
            return self._vector_store_instance
        raise ValueError("Vector store is not initialized. Use get_create_vector_store() instead.")

    def get_create_vector_store(self, embedding_model: BaseEmbeddingModel) -> BaseVectoreStore:
        """
        Vector Store Factory
        """
        if self._vector_store_instance is not None:
            return self._vector_store_instance

        store = self.configuration.storage.vector_store

        if isinstance(store, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")

            self._vector_store_instance = OpenSearchVectorStoreAdapter(
                embedding_model=embedding_model,
                host=opensearch_config.host,
                index=store.index,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
            )
            return self._vector_store_instance
        # elif isinstance(store, WeaviateVectorStorage):
        #     if self._vector_store_instance is None:
        #         self._vector_store_instance = WeaviateVectorStore(embedding_model, s.host, s.index_name)
        #     return self._vector_store_instance
        elif isinstance(store, InMemoryVectorStorage):
            self._vector_store_instance = InMemoryLangchainVectorStore(embedding_model=embedding_model)
        else:
            raise ValueError("Unsupported vector store backend")
        return self._vector_store_instance

    def get_metadata_store(self) -> BaseMetadataStore:
        if self._metadata_store_instance is not None:
            return self._metadata_store_instance

        store_config = get_configuration().storage.metadata_store
        if isinstance(store_config, DuckdbStoreConfig):
            db_path = Path(store_config.duckdb_path).expanduser()
            self._metadata_store_instance = DuckdbMetadataStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            self._metadata_store_instance = OpenSearchMetadataStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported metadata storage backend")
        return self._metadata_store_instance

    def get_opensearch_client(self) -> OpenSearch:
        if self._opensearch_client is not None:
            return self._opensearch_client

        opensearch_config = get_configuration().storage.opensearch
        self._opensearch_client = OpenSearch(
            opensearch_config.host,
            http_auth=(opensearch_config.username, opensearch_config.password),
            use_ssl=opensearch_config.secure,
            verify_certs=opensearch_config.verify_certs,
            connection_class=RequestsHttpConnection,
        )
        return self._opensearch_client

    def get_kpi_writer(self) -> KPIWriter:
        if self._kpi_writer is not None:
            return self._kpi_writer

        self._kpi_writer = KPIWriter(store=self.get_kpi_store())
        return self._kpi_writer

    def get_kpi_store(self) -> BaseKPIStore:
        if self._kpi_store_instance is not None:
            return self._kpi_store_instance

        store_config = get_configuration().storage.kpi_store
        if isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            self._kpi_store_instance = OpenSearchKPIStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        elif isinstance(store_config, LogStoreConfig):
            self._kpi_store_instance = KpiLogStore(level=store_config.level)
        else:
            raise ValueError("Unsupported KPI storage backend")
        return self._kpi_store_instance

    def get_tag_store(self) -> BaseTagStore:
        if self._tag_store_instance is not None:
            return self._tag_store_instance

        store_config = get_configuration().storage.tag_store
        if isinstance(store_config, DuckdbStoreConfig):
            db_path = Path(store_config.duckdb_path).expanduser()
            self._tag_store_instance = DuckdbTagStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            self._tag_store_instance = OpenSearchTagStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")
        return self._tag_store_instance

    def get_resource_store(self) -> BaseResourceStore:
        if self._resource_store_instance is not None:
            return self._resource_store_instance

        store_config = get_configuration().storage.resource_store
        if isinstance(store_config, DuckdbStoreConfig):
            db_path = Path(store_config.duckdb_path).expanduser()
            self._resource_store_instance = DuckdbResourceStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            self._resource_store_instance = OpenSearchResourceStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError(f"Unsupported tag storage backend: {store_config.type}")
        return self._resource_store_instance

    def get_tabular_stores(self) -> Dict[str, StoreInfo]:
        if self._tabular_stores is not None:
            return self._tabular_stores

        config_map = get_configuration().storage.tabular_stores or {}
        stores = {}

        for name, cfg in config_map.items():
            if isinstance(cfg, SQLStorageConfig):
                try:
                    database_name = cfg.database
                    if cfg.path is not None:
                        store = SQLTableStore(driver=cfg.driver, path=Path(cfg.path))
                    else:
                        raise ValueError("The path must not be None")

                    stores[database_name] = StoreInfo(store=store, mode=cfg.mode)
                    logger.info(f"[{database_name}] Connected to {cfg.driver} ({cfg.mode}) at {cfg.path}")
                except Exception as e:
                    logger.warning(f"[{name}] Failed to connect to {cfg.driver}: {e}")

        self._tabular_stores = stores
        return stores

    def get_csv_input_store(self) -> SQLTableStore:
        """
        Returns the store named 'base_database' if it exists,
        otherwise returns the first store with mode 'read_and_write'.
        """
        stores = self.get_tabular_stores()

        if "base_database" in stores:
            return stores["base_database"].store

        for store_info in stores.values():
            if store_info.mode == "read_and_write":
                return store_info.store
        raise ValueError("No tabular_stores with mode 'read_and_write' found. Please check the knowledge flow configuration.")

    def get_catalog_store(self) -> BaseCatalogStore:
        """
        Return the store used to save a local view of pull files, i.e. files not yet processed.
        Currently supports only DuckDB.
        """
        if self._catalog_store_instance is not None:
            return self._catalog_store_instance

        store_config = get_configuration().storage.catalog_store
        if isinstance(store_config, DuckdbStoreConfig):
            db_path = Path(store_config.duckdb_path).expanduser()
            self._catalog_store_instance = DuckdbCatalogStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            self._catalog_store_instance = OpenSearchCatalogStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")
        return self._catalog_store_instance

    def get_content_loader(self, source: str) -> BaseContentLoader:
        """
        Factory method to create a document loader instance based on configuration.
        this document loader is legacy it returns directly langchain documents
        Currently supports LocalFileLoader.
        """
        # Get the singleton application context and configuration
        config = self.get_config().document_sources
        if not config or source not in config:
            raise ValueError(f"Unknown document source tag: {source}")
        source_config = config[source]
        if source_config.type != "pull":
            raise ValueError(f"Source '{source}' is not a pull-mode source.")
        if isinstance(source_config, FileSystemPullSource):
            return FileSystemContentLoader(source_config, source)
        elif isinstance(source_config, MinioPullSource):
            return MinioContentLoader(source_config, source)
        else:
            raise NotImplementedError(f"No pull provider implemented for '{source_config.provider}'")

    def get_text_splitter(self) -> BaseTextSplitter:
        """
        Factory method to create a text splitter instance based on configuration.
        Currently returns RecursiveSplitter.
        """
        return SemanticSplitter()

    def get_pull_provider(self, source_tag: str) -> BaseContentLoader:
        source_config = self.configuration.document_sources.get(source_tag)

        if not source_config:
            raise ValueError(f"Unknown document source tag: {source_tag}")
        if source_config.type != "pull":
            raise ValueError(f"Source '{source_tag}' is not a pull-mode source.")

        if source_config.provider == "local_path":
            return FileSystemContentLoader(source_config, source_tag)
        elif source_config.provider == "minio":
            return MinioContentLoader(source_config, source_tag)
        else:
            raise NotImplementedError(f"No pull provider implemented for '{source_config.provider}'")

    def _log_sensitive(self, name: str, value: Optional[str]):
        logger.info(f"     ↳ {name} set: {'✅' if value else '❌'}")

    def _log_config_summary(self):
        sec = self.configuration.app.security

        logger.info("  🔒 security (Knowledge → Knowledge/Third Party):")
        logger.info("     • enabled: %s", sec.enabled)
        logger.info("     • client_id: %s", sec.client_id or "<unset>")
        logger.info("     • keycloak_url: %s", sec.keycloak_url or "<unset>")
        # realm parsing

        if sec.enabled:
            try:
                base, realm = split_realm_url(sec.keycloak_url)
                logger.info("     • realm: %s  (base=%s)", realm, base)
            except Exception as e:
                logger.error("     ❌ keycloak_url invalid (expected …/realms/<realm>): %s", e)
                raise ValueError("Invalid Keycloak URL") from e

            secret = os.getenv("KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET", "")
            if secret:
                logger.info("     • KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET: present  (%s)", _mask(secret))
            else:
                logger.error(
                    "     ⚠️  KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET is not set — external or recursive MCP or REST calls will not be protected (NoAuth). Knowledge Flow will likely suffer from 401."
                )
                raise ValueError("Missing KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET environment variable")

        backend = self.configuration.embedding.type
        logger.info("🔧 Application configuration summary:")
        logger.info("--------------------------------------------------")
        logger.info(f"  📦 Embedding backend: {backend.value}")

        if backend == EmbeddingProvider.OPENAI:
            s = validate_settings_or_exit(EmbeddingOpenAISettings, "OpenAI Embedding Settings")
            self._log_sensitive("OPENAI_API_KEY", s.openai_api_key)
            logger.info(f"     ↳ Model: {s.openai_model_name}")
        elif backend == EmbeddingProvider.AZUREOPENAI:
            s = validate_settings_or_exit(EmbeddingAzureOpenAISettings, "Azure OpenAI Embedding Settings")
            self._log_sensitive("AZURE_OPENAI_API_KEY", s.azure_openai_api_key)
            logger.info(f"     ↳ Deployment: {s.azure_deployment_embedding}")
            logger.info(f"     ↳ API Version: {s.azure_api_version}")
        elif backend == EmbeddingProvider.AZUREAPIM:
            try:
                s = validate_settings_or_exit(EmbeddingAzureApimSettings, "Azure APIM Embedding Settings")
                self._log_sensitive("AZURE_CLIENT_ID", s.azure_client_id)
                self._log_sensitive("AZURE_CLIENT_SECRET", s.azure_client_secret)
                self._log_sensitive("AZURE_APIM_KEY", s.azure_apim_key)
                logger.info(f"     ↳ APIM Base URL: {s.azure_apim_base_url}")
                logger.info(f"     ↳ Deployment: {s.azure_deployment_embedding}")
            except Exception:
                logger.warning("⚠️ Failed to load Azure APIM settings — some variables may be missing.")
        elif backend == EmbeddingProvider.OLLAMA:
            s = validate_settings_or_exit(OllamaSettings, "Ollama Embedding Settings")
            logger.info(f"     ↳ Model: {s.embedding_model_name}")
            logger.info(f"     ↳ API URL: {s.api_url if s.api_url else 'default'}")
        else:
            logger.warning("⚠️ Unknown embedding backend configured.")

        vector_type = self.configuration.storage.vector_store
        logger.info(f"  📚 Vector store backend: {vector_type}")
        try:
            store = self.configuration.storage.vector_store
            s = self.configuration.storage.opensearch
            if isinstance(store, OpenSearchIndexConfig):
                logger.info(f"     ↳ Host: {s.host}")
                logger.info(f"     ↳ Vector Index: {store.index}")
                logger.info(f"     ↳ Secure (TLS): {s.secure}")
                logger.info(f"     ↳ Verify Certs: {s.verify_certs}")
                logger.info(f"     ↳ Username: {s.username}")
                self._log_sensitive("OPENSEARCH_PASSWORD", os.getenv("OPENSEARCH_PASSWORD"))
            elif isinstance(s, WeaviateVectorStorage):
                logger.info(f"     ↳ Host: {s.host}")
                logger.info(f"     ↳ Index Name: {s.index_name}")
                self._log_sensitive("WEAVIATE_API_KEY", os.getenv("WEAVIATE_API_KEY"))
            elif vector_type == "in_memory":
                logger.info("     ↳ In-memory vector store (no host/index)")
        except Exception:
            logger.warning("⚠️ Failed to load vector store settings — some variables may be missing or misconfigured.")

        try:
            st = self.configuration.storage
            logger.info("  🗄️  Storage:")

            def _describe(label: str, store_cfg):
                if isinstance(store_cfg, DuckdbStoreConfig):
                    logger.info("     • %-14s DuckDB  path=%s", label, store_cfg.duckdb_path)
                elif isinstance(store_cfg, OpenSearchIndexConfig):
                    # These carry index name + opensearch global section
                    os_cfg = self.configuration.storage.opensearch
                    logger.info(
                        "     • %-14s OpenSearch host=%s index=%s secure=%s verify=%s",
                        label,
                        os_cfg.host,
                        store_cfg.index,
                        os_cfg.secure,
                        os_cfg.verify_certs,
                    )
                else:
                    # Generic store types from your pydantic StoreConfig could land here
                    logger.info("     • %-14s %s", label, type(store_cfg).__name__)

            _describe("agent_store", st.tag_store)
            _describe("session_store", st.kpi_store)
            _describe("feedback_store", st.catalog_store)
            _describe("feedback_store", st.metadata_store)
            _describe("feedback_store", st.vector_store)
            _describe("feedback_store", st.resource_store)
        except Exception:
            logger.warning("  ⚠️ Failed to read storage section (some variables may be missing).")

        logger.info(f"  📁 Content storage backend: {self.configuration.content_storage.type}")
        if isinstance(self.configuration.content_storage, MinioStorageConfig):
            logger.info(f"     ↳ Local Path: {self.configuration.content_storage.bucket_name}")

        logger.info("  🧩 Input Processor Mappings:")
        for ext, cls in self.input_processor_registry.items():
            logger.info(f"    • {ext} → {cls.__name__}")

        logger.info("  📤 Output Processor Mappings:")
        all_extensions = set(EXTENSION_CATEGORY.keys())
        for ext in sorted(all_extensions):
            if ext in self.output_processor_registry:
                cls = self.output_processor_registry[ext]
            else:
                category = EXTENSION_CATEGORY.get(ext)
                if not category:
                    continue
                default_path = DEFAULT_OUTPUT_PROCESSORS.get(category)
                if default_path:
                    cls = self._dynamic_import(default_path)
                else:
                    continue
            logger.info(f"    • {ext} → {cls.__name__}")

        logger.info("--------------------------------------------------")
