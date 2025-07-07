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
from typing import Dict, Type, Union, Optional
from knowledge_flow_app.common.structures import Configuration
from knowledge_flow_app.common.utils import validate_settings_or_exit
from knowledge_flow_app.config.embedding_azure_apim_settings import EmbeddingAzureApimSettings
from knowledge_flow_app.config.embedding_azure_openai_settings import EmbeddingAzureOpenAISettings
from knowledge_flow_app.config.ollama_settings import OllamaSettings
from knowledge_flow_app.config.embedding_openai_settings import EmbeddingOpenAISettings
from knowledge_flow_app.config.opensearch_settings import OpenSearchSettings
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings

from knowledge_flow_app.core.processors.input.common.base_input_processor import BaseInputProcessor, BaseMarkdownProcessor, BaseTabularProcessor
from knowledge_flow_app.core.processors.output.base_output_processor import BaseOutputProcessor
from knowledge_flow_app.core.processors.output.vectorization_processor.azure_apim_embedder import AzureApimEmbedder
from knowledge_flow_app.core.processors.output.vectorization_processor.embedder import Embedder
from knowledge_flow_app.core.processors.output.vectorization_processor.in_memory_langchain_vector_store import InMemoryLangchainVectorStore
from knowledge_flow_app.core.processors.output.vectorization_processor.interfaces import BaseDocumentLoader, BaseEmbeddingModel, BaseTextSplitter, BaseVectoreStore
from knowledge_flow_app.core.processors.output.vectorization_processor.local_file_loader import LocalFileLoader
from knowledge_flow_app.core.processors.output.vectorization_processor.opensearch_vector_store import OpenSearchVectorStoreAdapter
from knowledge_flow_app.core.processors.output.vectorization_processor.recursive_splitter import RecursiveSplitter

# Union of supported processor base classes
BaseProcessorType = Union[BaseMarkdownProcessor, BaseTabularProcessor]

# Default mapping for output processors by category
DEFAULT_OUTPUT_PROCESSORS = {
    "markdown": "knowledge_flow_app.core.processors.output.vectorization_processor.vectorization_processor.VectorizationProcessor",
    "tabular": "knowledge_flow_app.core.processors.output.tabular_processor.tabular_processor.TabularProcessor",
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
    _output_processor_instances: Dict[str, BaseOutputProcessor] = {}
    _vector_store_instance: Optional[BaseVectoreStore] = None

    def __init__(self, config: Configuration):
        # Allow reuse if already initialized with same config
        if ApplicationContext._instance is not None:
            # Optionally: log or assert config equality here
            return

        self.config = config
        validate_input_processor_config(config)
        validate_output_processor_config(config)
        self.input_processor_registry: Dict[str, Type[BaseInputProcessor]] = self._load_input_processor_registry()
        self.output_processor_registry: Dict[str, Type[BaseInputProcessor]] = self._load_output_processor_registry()
        ApplicationContext._instance = self
        self._log_config_summary()

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

        if class_path not in self._output_processor_instances:
            logger.debug(f"Creating new instance of input processor: {class_path}")
            self._output_processor_instances[class_path] = processor_class()

        return self._output_processor_instances[class_path]

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

    def get_embedder(self) -> BaseEmbeddingModel:
        """
        Factory method to create an embedding model instance based on the configuration.
        Supports Azure OpenAI and OpenAI.
        """
        backend_type = self.config.embedding.type

        if backend_type == "openai":
            settings = EmbeddingOpenAISettings()
            embedding_params = {
                "model": settings.openai_model_name,
                "openai_api_key": settings.openai_api_key,
                "openai_api_base": settings.openai_api_base,
                "openai_api_type": "openai",  # always "openai" for pure OpenAI
            }

            # Only add api_version if it exists
            if settings.openai_api_version:
                embedding_params["openai_api_version"] = settings.openai_api_version

            return Embedder(OpenAIEmbeddings(**embedding_params))

        elif backend_type == "azureopenai":
            openai_settings = EmbeddingAzureOpenAISettings()
            return Embedder(
                AzureOpenAIEmbeddings(
                    deployment=openai_settings.azure_deployment_embedding,
                    openai_api_type="azure",
                    azure_endpoint=openai_settings.azure_openai_base_url,
                    openai_api_version=openai_settings.azure_api_version,
                    openai_api_key=openai_settings.azure_openai_api_key,
                )
            )

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

        if backend_type == "opensearch":
            settings = validate_settings_or_exit(OpenSearchSettings, "OpenSearch Settings")
            return OpenSearchVectorStoreAdapter(embedding_model, settings)
        elif backend_type == "in_memory":
            if self._vector_store_instance is None:
                self._vector_store_instance = InMemoryLangchainVectorStore(embedding_model)
            return self._vector_store_instance
        # Future: Add more backends like Chroma, FAISS, Pinecone, etc.
        raise ValueError(f"Unsupported vector store backend: {backend_type}")

    def get_document_loader(self) -> BaseDocumentLoader:
        """
        Factory method to create a document loader instance based on configuration.
        Currently supports LocalFileLoader.
        """
        # TODO: In future we can allow other backends, based on config.
        return LocalFileLoader()

    def get_text_splitter(self) -> BaseTextSplitter:
        """
        Factory method to create a text splitter instance based on configuration.
        Currently returns RecursiveSplitter.
        """
        return RecursiveSplitter()

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
        if vector_type == "opensearch":
            try:
                s = validate_settings_or_exit(OpenSearchSettings, "OpenSearch Settings")
                logger.info(f"     ↳ OPENSEARCH_HOST: {s.opensearch_host}")
                logger.info(f"     ↳ OPENSEARCH_VECTOR_INDEX: {s.opensearch_vector_index}")
                self._log_sensitive("OPENSEARCH_USER", s.opensearch_user)
                self._log_sensitive("OPENSEARCH_PASSWORD", s.opensearch_password)
            except Exception:
                logger.warning("⚠️ Failed to load OpenSearch settings — some variables may be missing.")

        metadata_type = self.config.metadata_storage.type
        logger.info(f"  🗃️ Metadata storage backend: {metadata_type}")

        content_type = self.config.content_storage.type
        logger.info(f"  📁 Content storage backend: {content_type}")

        knowledge_context_type = self.config.knowledge_context_storage.type
        logger.info(f"  📁 Knwoledge context storage backend: {knowledge_context_type}")

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
                default_path = DEFAULT_OUTPUT_PROCESSORS.get(category)
                if default_path:
                    cls = self._dynamic_import(default_path)
                else:
                    continue
            logger.info(f"    • {ext} → {cls.__name__}")

        logger.info("--------------------------------------------------")

    def get_knowledge_context_max_tokens(self) -> int:
        return self.config.knowledge_context_max_tokens
