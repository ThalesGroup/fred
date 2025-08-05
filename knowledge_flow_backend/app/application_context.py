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
from app.core.stores.catalog.opensearch_catalog_store import OpenSearchCatalogStore
from app.core.stores.content.base_content_loader import BaseContentLoader
from app.core.stores.content.filesystem_content_loader import FileSystemContentLoader
from app.core.stores.content.minio_content_loader import MinioContentLoader
from fred_core.store.duckdb_store import DuckDBTableStore
from app.common.structures import (
    Configuration,
    DuckdbStorageConfig,
    InMemoryVectorStorage,
    FileSystemPullSource,
    LocalJsonStorageConfig,
    MinioPullSource,
    MinioStorageConfig,
    OpenSearchStorageConfig,
    WeaviateVectorStorage,
)
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
from app.core.stores.metadata.duckdb_metadata_store import DuckdbMetadataStore
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings

from app.core.processors.input.common.base_input_processor import BaseInputProcessor, BaseMarkdownProcessor, BaseTabularProcessor
from app.core.processors.output.base_output_processor import BaseOutputProcessor
from app.core.processors.output.vectorization_processor.azure_apim_embedder import AzureApimEmbedder
from app.core.processors.output.vectorization_processor.embedder import Embedder
from app.core.stores.metadata.base_metadata_store import BaseMetadataStore
from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore
from app.core.stores.prompts.base_prompt_store import BasePromptStore
from app.core.stores.prompts.duckdb_prompt_store import DuckdbPromptStore
from app.core.stores.prompts.opensearch_prompt_store import OpenSearchPromptStore
from app.core.stores.tags.base_tag_store import BaseTagStore
from app.core.stores.tags.duckdb_tag_store import DuckdbTagStore
from app.core.stores.tags.local_tag_store import LocalTagStore
from app.core.stores.tags.opensearch_tags_store import OpenSearchTagStore
from app.core.stores.vector.in_memory_langchain_vector_store import InMemoryLangchainVectorStore
from app.core.stores.vector.base_vector_store import BaseEmbeddingModel, BaseTextSplitter, BaseVectoreStore
from app.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from app.core.processors.output.vectorization_processor.semantic_splitter import SemanticSplitter
from app.core.stores.vector.weaviate_vector_store import WeaviateVectorStore

# Union of supported processor base classes
BaseProcessorType = Union[BaseMarkdownProcessor, BaseTabularProcessor]

# Default mapping for output processors by category
DEFAULT_OUTPUT_PROCESSORS = {
    "markdown": "app.core.processors.output.vectorization_processor.vectorization_processor.VectorizationProcessor",
    "tabular": "app.core.processors.output.tabular_processor.tabular_processor.TabularProcessor",
    "duckdb": "app.core.processors.output.duckdb_processor.duckdb_processor.DuckDBProcessor",
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
}

logger = logging.getLogger(__name__)


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
    _input_processor_instances: Dict[str, BaseInputProcessor] = {}
    _output_processor_instances: Dict[str, BaseOutputProcessor] = {}
    _vector_store_instance: Optional[BaseVectoreStore] = None
    _metadata_store_instance: Optional[BaseMetadataStore] = None
    _tag_store_instance: Optional[BaseTagStore] = None
    _prompt_store_instance: Optional[BasePromptStore] = None
    _tabular_store_instance: Optional[DuckDBTableStore] = None

    def __init__(self, config: Configuration):
        # Allow reuse if already initialized with same config
        if ApplicationContext._instance is not None:
            # Optionally: log or assert config equality here
            return

        self.config = config
        validate_input_processor_config(config)
        validate_output_processor_config(config)
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
        for entry in self.config.input_processors:
            cls = self._dynamic_import(entry.class_path)
            if not issubclass(cls, BaseInputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseProcessor")
            logger.debug(f"Loaded input processor: {entry.class_path} for prefix: {entry.prefix}")
            registry[entry.prefix.lower()] = cls
        return registry

    def _load_output_processor_registry(self) -> Dict[str, Type[BaseOutputProcessor]]:
        registry = {}
        if not self.config.output_processors:
            return registry
        for entry in self.config.output_processors:
            cls = self._dynamic_import(entry.class_path)
            if not issubclass(cls, BaseOutputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseOutputProcessor")
            logger.debug(f"Loaded output processor: {entry.class_path} for prefix: {entry.prefix}")
            registry[entry.prefix.lower()] = cls
        return registry

    def get_config(self) -> Configuration:
        return self.config

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
            return MinioStorageBackend(endpoint=config.endpoint, access_key=config.access_key, secret_key=config.secret_key, bucket_name=config.bucket_name, secure=config.secure)
        elif backend_type == "local":
            return FileSystemContentStore(Path(config.root_path).expanduser())
        else:
            raise ValueError(f"Unsupported storage backend: {backend_type}")

    def get_embedder(self) -> BaseEmbeddingModel:
        """
        Factory method to create an embedding model instance based on the configuration.
        Supports Azure OpenAI and OpenAI.
        """
        backend_type = self.config.embedding.type

        if backend_type == "openai":
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

        elif backend_type == "azureopenai":
            openai_settings = EmbeddingAzureOpenAISettings()  # type: ignore[call-arg]
            return Embedder(
                AzureOpenAIEmbeddings(
                    deployment=openai_settings.azure_deployment_embedding,
                    openai_api_type="azure",
                    azure_endpoint=openai_settings.azure_openai_base_url,
                    openai_api_version=openai_settings.azure_api_version,
                    openai_api_key=openai_settings.azure_openai_api_key,
                )
            )  # type: ignore[call-arg]

        elif backend_type == "azureapim":
            settings = validate_settings_or_exit(EmbeddingAzureApimSettings, "Azure APIM Embedding Settings")
            return AzureApimEmbedder(settings)

        elif backend_type == "ollama":
            ollama_settings = OllamaSettings()
            embedding_params = {
                "model": ollama_settings.embedding_model_name,
            }
            if ollama_settings.api_url:
                embedding_params["base_url"] = ollama_settings.api_url

            return Embedder(OllamaEmbeddings(**embedding_params))

        else:
            raise ValueError(f"Unsupported embedding backend: {backend_type}")

    def get_vector_store(self, embedding_model: BaseEmbeddingModel) -> BaseVectoreStore:
        """
        Vector Store Factory
        ---------------

        This method creates a vector store instance based on the configuration.

        Usage:

            # In your main service (example)
            embedder = application_context.get_embedder()

            # Used in your business logic
            embedded_chunks = embedder.embed_documents(documents)

            # When building a vector store
            vector_store = application_context.get_vector_store(embedder)

            # Now you can add embeddings into the vector store
            vector_store.add_embeddings(embedded_chunks)

        """
        backend_type = self.config.vector_storage.type

        if isinstance(self.config.vector_storage, OpenSearchStorageConfig):
            s = self.config.vector_storage
            if not s.username or not s.password:
                raise ValueError("Missing required environment variables: OPENSEARCH_USER and OPENSEARCH_PASSWORD")

            if self._vector_store_instance is None:
                self._vector_store_instance = OpenSearchVectorStoreAdapter(
                    embedding_model=embedding_model,
                    host=s.host,
                    index=s.index,
                    username=s.username,
                    password=s.password,
                    secure=s.secure,
                    verify_certs=s.verify_certs,
                )
            return self._vector_store_instance
        elif isinstance(self.config.vector_storage, WeaviateVectorStorage):
            s = self.config.vector_storage
            if self._vector_store_instance is None:
                self._vector_store_instance = WeaviateVectorStore(embedding_model, s.host, s.index_name)
            return self._vector_store_instance
        elif isinstance(self.config.vector_storage, InMemoryVectorStorage):
            if self._vector_store_instance is None:
                self._vector_store_instance = InMemoryLangchainVectorStore(embedding_model=embedding_model)
            return self._vector_store_instance
        raise ValueError(f"Unsupported vector store backend: {backend_type}")

    def get_metadata_store(self) -> BaseMetadataStore:
        if self._metadata_store_instance is not None:
            return self._metadata_store_instance
        config = self.config.metadata_storage
        if isinstance(config, DuckdbStorageConfig):
            db_path = Path(config.duckdb_path).expanduser()
            self._metadata_store_instance = DuckdbMetadataStore(db_path)
        elif isinstance(config, OpenSearchStorageConfig):
            username = config.username
            password = config.password

            if not username or not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD")

            self._metadata_store_instance = OpenSearchMetadataStore(
                host=config.host,
                username=username,
                password=password,
                secure=config.secure,
                verify_certs=config.verify_certs,
                index=config.index,
            )

        else:
            raise ValueError(f"Unsupported metadata storage backend: {config.type}")
        return self._metadata_store_instance

    def get_tag_store(self) -> BaseTagStore:
        if self._tag_store_instance is not None:
            return self._tag_store_instance

        config = self.config.tag_storage

        if isinstance(config, LocalJsonStorageConfig):
            path = Path(config.root_path).expanduser()
            self._tag_store_instance = LocalTagStore(path)
            return self._tag_store_instance
        elif isinstance(config, DuckdbStorageConfig):
            path = Path(config.duckdb_path).expanduser()
            self._tag_store_instance = DuckdbTagStore(path)
            return self._tag_store_instance
        elif isinstance(config, OpenSearchStorageConfig):
            username = config.username
            password = config.password

            if not username or not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD")

            self._tag_store_instance = OpenSearchTagStore(
                host=config.host,
                index=config.index,
                username=username,
                password=password,
                secure=config.secure,
                verify_certs=config.verify_certs,
            )
            return self._tag_store_instance
        else:
            raise ValueError(f"Unsupported tag storage backend: {config.type}")

    def get_prompt_store(self) -> BasePromptStore:
        if self._prompt_store_instance is not None:
            return self._prompt_store_instance

        config = self.config.prompt_storage

        if isinstance(config, DuckdbStorageConfig):
            path = Path(config.duckdb_path).expanduser()
            self._prompt_store_instance = DuckdbPromptStore(path)
            return self._prompt_store_instance
        elif isinstance(config, OpenSearchStorageConfig):
            username = config.username
            password = config.password

            if not username or not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD")

            self._prompt_store_instance = OpenSearchPromptStore(
                host=config.host,
                index=config.index,
                username=username,
                password=password,
                secure=config.secure,
                verify_certs=config.verify_certs,
            )
            return self._prompt_store_instance
        else:
            raise ValueError(f"Unsupported tag storage backend: {config.type}")

    def get_tabular_store(self) -> DuckDBTableStore:
        """
        Lazy-initialize and return the configured tabular store backend.
        Currently supports only DuckDB.
        """
        if hasattr(self, "_tabular_store_instance") and self._tabular_store_instance is not None:
            return self._tabular_store_instance

        config = self.config.tabular_storage

        if isinstance(config, DuckdbStorageConfig):
            db_path = Path(config.duckdb_path).expanduser()
            self._tabular_store_instance = DuckDBTableStore(db_path, prefix="tabular_")
        else:
            raise ValueError(f"Unsupported tabular storage backend: {config.type}")

        return self._tabular_store_instance

    def get_catalog_store(self) -> BaseCatalogStore:
        """
        Return the store used to save a local view of pull files, i.e. files not yet processed.
        Currently supports only DuckDB.
        """
        if hasattr(self, "_catalog_store_instance") and self._catalog_store_instance is not None:
            return self._catalog_store_instance

        config = self.config.catalog_storage

        if isinstance(config, DuckdbStorageConfig):
            db_path = Path(config.duckdb_path).expanduser()
            self._catalog_store_instance = DuckdbCatalogStore(db_path)
        elif isinstance(config, OpenSearchStorageConfig):
            username = config.username
            password = config.password

            if not username or not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD")

            self._catalog_store_instance = OpenSearchCatalogStore(
                host=config.host,
                index=config.index,
                username=username,
                password=password,
                secure=config.secure,
                verify_certs=config.verify_certs,
            )
            return self._catalog_store_instance

        else:
            raise ValueError(f"Unsupported catalog storage backend: {config.type}")

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
        source_config = self.config.document_sources.get(source_tag)

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
        backend = self.config.embedding.type
        logger.info("🔧 Application configuration summary:")
        logger.info("--------------------------------------------------")
        logger.info(f"  📦 Embedding backend: {backend}")

        if backend == "openai":
            s = validate_settings_or_exit(EmbeddingOpenAISettings, "OpenAI Embedding Settings")
            self._log_sensitive("OPENAI_API_KEY", s.openai_api_key)
            logger.info(f"     ↳ Model: {s.openai_model_name}")
        elif backend == "azureopenai":
            s = validate_settings_or_exit(EmbeddingAzureOpenAISettings, "Azure OpenAI Embedding Settings")
            self._log_sensitive("AZURE_OPENAI_API_KEY", s.azure_openai_api_key)
            logger.info(f"     ↳ Deployment: {s.azure_deployment_embedding}")
            logger.info(f"     ↳ API Version: {s.azure_api_version}")
        elif backend == "azureapim":
            try:
                s = validate_settings_or_exit(EmbeddingAzureApimSettings, "Azure APIM Embedding Settings")
                self._log_sensitive("AZURE_CLIENT_ID", s.azure_client_id)
                self._log_sensitive("AZURE_CLIENT_SECRET", s.azure_client_secret)
                self._log_sensitive("AZURE_APIM_KEY", s.azure_apim_key)
                logger.info(f"     ↳ APIM Base URL: {s.azure_apim_base_url}")
                logger.info(f"     ↳ Deployment: {s.azure_deployment_embedding}")
            except Exception:
                logger.warning("⚠️ Failed to load Azure APIM settings — some variables may be missing.")
        elif backend == "ollama":
            s = validate_settings_or_exit(OllamaSettings, "Ollama Embedding Settings")
            logger.info(f"     ↳ Model: {s.embedding_model_name}")
            logger.info(f"     ↳ API URL: {s.api_url if s.api_url else 'default'}")
        else:
            logger.warning("⚠️ Unknown embedding backend configured.")

        vector_type = self.config.vector_storage.type
        logger.info(f"  📚 Vector store backend: {vector_type}")
        try:
            s = self.config.vector_storage
            if isinstance(s, OpenSearchStorageConfig):
                logger.info(f"     ↳ Host: {s.host}")
                logger.info(f"     ↳ Vector Index: {s.index}")
                logger.info(f"     ↳ Secure (TLS): {s.secure}")
                logger.info(f"     ↳ Verify Certs: {s.verify_certs}")
                self._log_sensitive("OPENSEARCH_USER", os.getenv("OPENSEARCH_USER"))
                self._log_sensitive("OPENSEARCH_PASSWORD", os.getenv("OPENSEARCH_PASSWORD"))
            elif isinstance(s, WeaviateVectorStorage):
                logger.info(f"     ↳ Host: {s.host}")
                logger.info(f"     ↳ Index Name: {s.index_name}")
                self._log_sensitive("WEAVIATE_API_KEY", os.getenv("WEAVIATE_API_KEY"))
            elif vector_type == "in_memory":
                logger.info("     ↳ In-memory vector store (no host/index)")
        except Exception:
            logger.warning("⚠️ Failed to load vector store settings — some variables may be missing or misconfigured.")

        metadata_type = self.config.metadata_storage.type

        logger.info(f"  🗃️ Metadata storage backend: {metadata_type}")
        if isinstance(self.config.metadata_storage, DuckdbStorageConfig):
            logger.info(f"     ↳ DB Path: {self.config.metadata_storage.duckdb_path}")

        logger.info(f"  📂 Catalog storage backend: {self.config.catalog_storage.type}")
        if isinstance(self.config.catalog_storage, DuckdbStorageConfig):
            logger.info(f"     ↳ DB Path: {self.config.catalog_storage.duckdb_path}")

        logger.info(f"  📂 Prompt storage backend: {self.config.prompt_storage.type}")
        if isinstance(self.config.prompt_storage, DuckdbStorageConfig):
            logger.info(f"     ↳ DB Path: {self.config.prompt_storage.duckdb_path}")

        logger.info(f"  📂 Tag storage backend: {self.config.tag_storage.type}")
        if isinstance(self.config.tag_storage, DuckdbStorageConfig):
            logger.info(f"     ↳ DB Path: {self.config.tag_storage.duckdb_path}")

        logger.info(f"  📁 Content storage backend: {self.config.content_storage.type}")
        if isinstance(self.config.content_storage, MinioStorageConfig):
            logger.info(f"     ↳ Local Path: {self.config.content_storage.bucket_name}")

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
