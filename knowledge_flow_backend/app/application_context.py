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
from typing import Dict, Optional, Type, Union

from fred_core import (
    BaseKPIStore,
    BaseLogStore,
    DuckdbStoreConfig,
    InMemoryLogStorageConfig,
    KpiLogStore,
    KPIWriter,
    LogStoreConfig,
    ModelConfiguration,
    ModelProvider,
    OpenSearchIndexConfig,
    OpenSearchKPIStore,
    OpenSearchLogStore,
    RamLogStore,
    RebacEngine,
    SpiceDbRebacConfig,
    SpiceDbRebacEngine,
    SQLStorageConfig,
    SQLTableStore,
    StoreInfo,
    get_embeddings,
    get_model,
    split_realm_url,
)
from langchain_core.embeddings import Embeddings
from opensearchpy import OpenSearch, RequestsHttpConnection

from app.common.structures import (
    ChromaVectorStorageConfig,
    Configuration,
    FileSystemPullSource,
    InMemoryVectorStorage,
    LocalContentStorageConfig,
    MinioPullSource,
    MinioStorageConfig,
    OpenSearchVectorIndexConfig,
    WeaviateVectorStorage,
)
from app.core.processors.input.common.base_input_processor import BaseInputProcessor, BaseMarkdownProcessor, BaseTabularProcessor
from app.core.processors.output.base_output_processor import BaseOutputProcessor
from app.core.processors.output.vectorization_processor.semantic_splitter import SemanticSplitter
from app.core.stores.catalog.base_catalog_store import BaseCatalogStore
from app.core.stores.catalog.duckdb_catalog_store import DuckdbCatalogStore
from app.core.stores.catalog.opensearch_catalog_store import OpenSearchCatalogStore
from app.core.stores.catalog.sql_catalog_store import SQLCatalogStore
from app.core.stores.content.base_content_loader import BaseContentLoader
from app.core.stores.content.base_content_store import BaseContentStore
from app.core.stores.content.filesystem_content_loader import FileSystemContentLoader
from app.core.stores.content.filesystem_content_store import FileSystemContentStore
from app.core.stores.content.minio_content_loader import MinioContentLoader
from app.core.stores.content.minio_content_store import MinioStorageBackend
from app.core.stores.files.base_file_store import BaseFileStore
from app.core.stores.files.local_file_store import LocalFileStore
from app.core.stores.files.minio_file_store import MinioFileStore
from app.core.stores.metadata.base_metadata_store import BaseMetadataStore
from app.core.stores.metadata.duckdb_metadata_store import DuckdbMetadataStore
from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore
from app.core.stores.resources.base_resource_store import BaseResourceStore
from app.core.stores.resources.duckdb_resource_store import DuckdbResourceStore
from app.core.stores.resources.opensearch_resource_store import OpenSearchResourceStore
from app.core.stores.tags.base_tag_store import BaseTagStore
from app.core.stores.tags.duckdb_tag_store import DuckdbTagStore
from app.core.stores.tags.opensearch_tags_store import OpenSearchTagStore
from app.core.stores.vector.base_text_splitter import BaseTextSplitter
from app.core.stores.vector.base_vector_store import BaseVectorStore
from app.core.stores.vector.in_memory_langchain_vector_store import InMemoryLangchainVectorStore
from app.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter

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


def get_rebac_engine() -> RebacEngine:
    """Expose the shared ReBAC engine instance."""

    return get_app_context().get_rebac_engine()


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


def _require_env(var: str) -> None:
    """Log presence of a required env var or raise loudly if missing."""
    val = os.getenv(var, "")
    if val:
        logger.info("     • %s: present (%s)", var, _mask(val))
        return
    logger.error("     ❌ %s is not set", var)
    raise ValueError(f"Missing required environment variable: {var}")


class ApplicationContext:
    _instance: Optional["ApplicationContext"] = None
    configuration: Configuration
    _input_processor_instances: Dict[str, BaseInputProcessor] = {}
    _output_processor_instances: Dict[str, BaseOutputProcessor] = {}
    _vector_store_instance: Optional[BaseVectorStore] = None
    _metadata_store_instance: Optional[BaseMetadataStore] = None
    _tag_store_instance: Optional[BaseTagStore] = None
    _kpi_store_instance: Optional[BaseKPIStore] = None
    _log_store_instance: Optional[BaseLogStore] = None
    _opensearch_client: Optional[OpenSearch] = None
    _resource_store_instance: Optional[BaseResourceStore] = None
    _tabular_stores: Optional[Dict[str, StoreInfo]] = None
    _catalog_store_instance: Optional[BaseCatalogStore] = None
    _file_store_instance: Optional[BaseFileStore] = None
    _kpi_writer: Optional[KPIWriter] = None
    _rebac_engine: Optional[RebacEngine] = None

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

    def get_log_store(self) -> BaseLogStore:
        """
        Factory function to get the appropriate log storage backend based on configuration.
        Returns:
            BaseLogStore: An instance of the log storage backend.
        """
        if self._log_store_instance is not None:
            return self._log_store_instance

        config = ApplicationContext.get_instance().get_config().storage.log_store
        if isinstance(config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")

            self._log_store_instance = OpenSearchLogStore(
                host=opensearch_config.host,
                index=config.index,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
            )
        elif isinstance(config, InMemoryLogStorageConfig) or config is None:
            self._log_store_instance = RamLogStore(capacity=1000)  # Default to in-memory store if not configured
        else:
            raise ValueError("Log store configuration is missing or invalid")

        return self._log_store_instance

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
            document_bucket = f"{config.bucket_name}-documents"
            object_bucket = f"{config.bucket_name}-objects"
            return MinioStorageBackend(
                endpoint=config.endpoint, access_key=config.access_key, secret_key=config.secret_key, document_bucket=document_bucket, object_bucket=object_bucket, secure=config.secure
            )
        elif isinstance(config, LocalContentStorageConfig):
            document_root = Path(config.root_path).expanduser() / "documents"
            object_root = Path(config.root_path).expanduser() / "objects"
            return FileSystemContentStore(document_root=document_root, object_root=object_root)
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

    def get_embedder(self) -> Embeddings:
        """
        Fred rationale:
        - Knowledge Flow uses the shared fred_core factory to avoid provider drift.
        - Only secrets live in env; all other wiring lives in YAML.
        - Typed return (Embeddings) keeps the contract clear at call sites.
        """
        cfg: ModelConfiguration = self.configuration.embedding_model
        return get_embeddings(cfg)

    def get_utility_model(self):
        if not self.configuration.chat_model:
            raise ValueError("Utility model configuration is missing.")
        return get_model(self.configuration.chat_model)

    def get_vision_model(self):
        if not self.configuration.vision:
            raise ValueError("Vision model configuration is missing.")
        return get_model(self.configuration.vision)

    def get_vector_store(self) -> BaseVectorStore:
        """
        Vector Store Factory
        """
        if self._vector_store_instance is not None:
            return self._vector_store_instance
        raise ValueError("Vector store is not initialized. Use get_create_vector_store() instead.")

    def get_create_vector_store(self, embedding_model: Embeddings) -> BaseVectorStore:
        """
        Vector Store Factory
        """
        if self._vector_store_instance is not None:
            return self._vector_store_instance
        embedding_model_name = self.configuration.embedding_model.name or "unknown"
        store = self.configuration.storage.vector_store

        if isinstance(store, OpenSearchVectorIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")

            self._vector_store_instance = OpenSearchVectorStoreAdapter(
                embedding_model=embedding_model,
                embedding_model_name=embedding_model_name,
                host=opensearch_config.host,
                index=store.index,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                bulk_size=store.bulk_size,
            )
            return self._vector_store_instance
        # elif isinstance(store, WeaviateVectorStorage):
        #     if self._vector_store_instance is None:
        #         self._vector_store_instance = WeaviateVectorStore(embedding_model, s.host, s.index_name)
        #     return self._vector_store_instance
        elif isinstance(store, ChromaVectorStorageConfig):
            from app.core.stores.vector.chromadb_vector_store import ChromaDBVectorStore

            local_path = Path(store.local_path).expanduser()
            local_path.mkdir(parents=True, exist_ok=True)
            self._vector_store_instance = ChromaDBVectorStore(
                persist_path=str(local_path),
                collection_name=store.collection_name,
                embeddings=embedding_model,
                embedding_model_name=embedding_model_name,
            )
        elif isinstance(store, InMemoryVectorStorage):
            self._vector_store_instance = InMemoryLangchainVectorStore(embedding_model=embedding_model, embedding_model_name=embedding_model_name)
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

    def get_rebac_engine(self) -> RebacEngine:
        if self._rebac_engine is not None:
            return self._rebac_engine

        rebac_config = self.configuration.security.rebac
        if isinstance(rebac_config, SpiceDbRebacConfig):
            token_env_var = rebac_config.token_env_var
            token = os.getenv(token_env_var)
            if not token:
                raise ValueError(f"Missing SpiceDB token environment variable: {token_env_var}")

            logger.info(
                "Initializing SpiceDB ReBAC engine (endpoint=%s, insecure=%s)",
                rebac_config.endpoint,
                rebac_config.insecure,
            )
            self._rebac_engine = SpiceDbRebacEngine(
                rebac_config,
                token=token,
            )
        else:
            raise ValueError(f"Unsupported ReBAC engine type: {getattr(rebac_config, 'type', rebac_config)}")
        return self._rebac_engine

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
        elif isinstance(store_config, SQLStorageConfig):
            db_path = Path(store_config.path or "").expanduser()
            self._catalog_store_instance = SQLCatalogStore(driver=store_config.driver, db_path=db_path)
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

    def is_summary_generation_enabled(self) -> bool:
        """
        Checks if the summary generation feature is enabled in the configuration.
        Returns:
            bool: True if enabled, False otherwise.
        """
        return self.configuration.processing.generate_summary

    def _log_sensitive(self, name: str, value: Optional[str]):
        logger.info(f"     ↳ {name} set: {'✅' if value else '❌'}")

    def _log_config_summary(self):
        sec = self.configuration.security.user

        logger.info("  🔒 security (Knowledge → Knowledge/Third Party):")
        logger.info("     • enabled: %s", sec.enabled)
        logger.info("     • client_id: %s", sec.client_id or "<unset>")
        logger.info("     • keycloak_url: %s", sec.realm_url or "<unset>")
        # realm parsing

        if sec.enabled:
            try:
                base, realm = split_realm_url(str(sec.realm_url))
                logger.info("     • realm: %s  (base=%s)", realm, base)
            except Exception as e:
                logger.error("     ❌ keycloak_url invalid (expected …/realms/<realm>): %s", e)
                raise ValueError("Invalid Keycloak URL") from e
            _require_env("KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET")

        rebac = self.configuration.security.rebac
        if rebac:
            logger.info("  🕸️ ReBAC engine: %s", rebac.type)
            logger.info("     • endpoint: %s", rebac.endpoint)
            logger.info("     • insecure: %s", rebac.insecure)
            logger.info("     • sync_schema_on_init: %s", rebac.sync_schema_on_init)
            env_name = rebac.token_env_var
            self._log_sensitive(env_name, os.getenv(env_name))
        else:
            logger.info("  🕸️ ReBAC engine: disabled")

        embedding = self.configuration.embedding_model
        # Non-secret settings from YAML
        for k, v in (embedding.settings or {}).items():
            # Heuristic mask for anything that *looks* sensitive even if put in YAML by mistake
            if any(t in k.lower() for t in ("secret", "token", "key")):
                logger.info("     ↳ %s: (masked)", k)
            else:
                logger.info("     ↳ %s: %s", k, v)

        # Required env vars by provider
        provider = (embedding.provider or "").lower()
        if provider == ModelProvider.OPENAI.value:
            _require_env("OPENAI_API_KEY")
        elif provider == ModelProvider.AZURE_OPENAI.value:
            _require_env("AZURE_OPENAI_API_KEY")
        elif provider == ModelProvider.AZURE_APIM.value:
            _require_env("AZURE_AD_CLIENT_SECRET")
            _require_env("AZURE_APIM_SUBSCRIPTION_KEY")
        elif provider == ModelProvider.OLLAMA.value:
            # Usually no secrets; base_url is in settings
            pass
        else:
            logger.error("     ❌ Unsupported embedding provider: %s", provider)
            raise ValueError(f"Unsupported embedding provider: {provider}")

        processing = self.configuration.processing or {}
        # Processing flags (your new simple shape)
        logger.info("  ⚙️ Processing policy:")
        logger.info("     ↳ use_gpu: %s", processing.use_gpu)
        logger.info("     ↳ process_images: %s", processing.process_images)
        logger.info("     ↳ generate_summary: %s", processing.generate_summary)
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
                    os_cfg = self.configuration.storage.opensearch
                    logger.info(
                        "     • %-14s OpenSearch host=%s index=%s secure=%s verify=%s",
                        label,
                        os_cfg.host,
                        store_cfg.index,
                        os_cfg.secure,
                        os_cfg.verify_certs,
                    )
                elif isinstance(store_cfg, SQLStorageConfig):
                    logger.info("     • %-14s SQLStorage  database=%s  host=%s", label, store_cfg.database or "unset", store_cfg.host or "unset")
                elif isinstance(store_cfg, ChromaVectorStorageConfig):
                    logger.info("     • %-14s ChromaDB  database=%s  host=%s  distance=%s", label, store_cfg.local_path or "unset", store_cfg.collection_name or "unset", store_cfg.distance or "unset")
                elif isinstance(store_cfg, LogStoreConfig):
                    # No-op KPI / log-only store
                    logger.info(
                        "     • %-14s No-op / LogStore  level=%s  (logs only, no persistence)",
                        label,
                        getattr(store_cfg, "level", "INFO"),
                    )
                else:
                    logger.info("     • %-14s %s", label, type(store_cfg).__name__)

            _describe("tag_store", st.tag_store)
            _describe("kpi_store", st.kpi_store)
            _describe("catalog_store", st.catalog_store)
            _describe("metadata_store", st.metadata_store)
            _describe("vector_store", st.vector_store)
            _describe("resource_store", st.resource_store)

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
