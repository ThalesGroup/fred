# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import importlib
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Type
from uuid import UUID

from fred_core.kpi import BaseKPIWriter, build_kpi_writer
from fred_core.model import http_clients
from fred_knowledge.models import DocumentModels
from fred_knowledge.text.base_text_splitter import BaseTextSplitter
from fred_knowledge.text.semantic_splitter import SemanticSplitter
from fred_knowledge.vector.base_vector_store import BaseVectorStore
from fred_knowledge.vector.factory import build_vector_store
from fred_sdk.contracts.weaver import InferenceAdmission
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from knowledge_flow_worker.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_worker.common.structures import Configuration
from knowledge_flow_worker.core.processors.input.common.base_input_processor import BaseInputProcessor, BaseTabularProcessor
from knowledge_flow_worker.core.processors.input.fast_text_processor.base_fast_text_processor import BaseFastTextProcessor
from knowledge_flow_worker.core.processors.output.base_output_processor import BaseOutputProcessor

if TYPE_CHECKING:
    from knowledge_flow_worker.features.manager_processing.persistence import LocalTabularArtifacts
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_PROCESSORS = {
    "markdown": "knowledge_flow_worker.core.processors.output.vectorization_processor.vectorization_processor.VectorizationProcessor",
    "tabular": "knowledge_flow_worker.core.processors.output.tabular_processor.tabular_processor.TabularProcessor",
    "spreadsheet": "knowledge_flow_worker.core.processors.output.excel_processor.excel_table_registration_processor.ExcelTableRegistrationProcessor",
}

# Mapping file extensions to categories.
# "spreadsheet" documents produce a markdown preview (output.md) plus N Parquet
# tables: they are PREVIEW_READY like markdown files and SQL_INDEXED like
# tabular files, but never vectorized.
EXTENSION_CATEGORY = {
    ".pdf": "markdown",
    ".docx": "markdown",
    ".pptx": "markdown",
    ".msg": "markdown",
    ".eml": "markdown",
    ".txt": "markdown",
    ".md": "markdown",
    ".csv": "tabular",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".xlsm": "spreadsheet",
    ".duckdb": "duckdb",
    ".jsonl": "markdown",
    # Image extensions - processed as markdown with metadata
    ".png": "markdown",
    ".jpg": "markdown",
    ".jpeg": "markdown",
    ".gif": "markdown",
    ".bmp": "markdown",
    ".svg": "markdown",
    ".webp": "markdown",
    ".ico": "markdown",
}


def get_configuration() -> Configuration:
    """
    Retrieves the global application configuration.

    Returns:
        Configuration: The singleton application configuration.
    """
    return get_app_context().configuration


def get_kpi_writer() -> BaseKPIWriter:
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


def _validate_pdf_dependencies(class_path: str, selection: str, extractor: str = "docling") -> None:
    prefix = "knowledge_flow_worker.core.processors.input."
    if class_path == prefix + "lightweight_markdown_processor.lite2_pdf_to_md_processor.LitePdfMarkdownProcessor" or (
        class_path == prefix + "pdf_markdown_processor.pdf_markdown_processor.PdfMarkdownProcessor" and extractor == "pymupdf"
    ):
        from knowledge_flow_worker.core.processors.input.pdf_markdown_processor.optional_pymupdf import require_pymupdf

        require_pymupdf(selection)


def validate_profile_input_processor_config(config: Configuration):
    """Ensure all profile input processor classes can be imported and subclass BaseInputProcessor."""
    default_profile_cfg = config.processing.get_profile_config(config.processing.default_profile)
    if not default_profile_cfg.input_processors:
        raise ValueError(
            f"processing.profiles.{config.processing.default_profile.value}.input_processors must not be empty",
        )

    for profile_name in ("fast", "medium", "rich"):
        profile_cfg = config.processing.get_profile_config(profile_name)
        seen_suffixes: set[str] = set()
        for entry in profile_cfg.input_processors:
            suffix = entry.suffix.lower()
            if suffix in seen_suffixes:
                raise ValueError(
                    f"Duplicate input processor suffix '{suffix}' in processing.profiles.{profile_name}.input_processors",
                )
            seen_suffixes.add(suffix)

            _validate_pdf_dependencies(entry.class_path, f"processing.profiles.{profile_name} ({entry.class_path}, pdf.extractor={profile_cfg.pdf.extractor})", profile_cfg.pdf.extractor)
            module_path, class_name = entry.class_path.rsplit(".", 1)
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                if not issubclass(cls, BaseInputProcessor):
                    raise TypeError(f"{entry.class_path} is not a subclass of BaseInputProcessor")
                logger.debug(
                    "Validated profile input processor: %s for profile=%s suffix=%s",
                    entry.class_path,
                    profile_name,
                    suffix,
                )
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
            logger.debug(f"Validated output processor: {entry.class_path} for prefix: {entry.suffix}")
        except (ImportError, AttributeError, TypeError) as e:
            raise ImportError(f"Output Processor '{entry.class_path}' could not be loaded: {e}")


def validate_attachment_processor_config(config: Configuration):
    """Ensure all attachment fast-text processor classes can be imported and subclass BaseFastTextProcessor."""
    if not config.attachment_processors:
        return
    for entry in config.attachment_processors:
        module_path, class_name = entry.class_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            if not issubclass(cls, BaseFastTextProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseFastTextProcessor")
            logger.debug("Validated attachment processor: %s for prefix: %s", entry.class_path, entry.suffix)
        except (ImportError, AttributeError, TypeError) as e:
            raise ImportError(f"Attachment Processor '{entry.class_path}' could not be loaded: {e}")


class ApplicationContext:
    _instance: Optional["ApplicationContext"] = None

    def __init__(self, configuration: Configuration):
        if ApplicationContext._instance is not None:
            return
        self.configuration = configuration
        self._input_processor_instances: Dict[str, BaseInputProcessor] = {}
        self._output_processor_instances: Dict[str, BaseOutputProcessor] = {}
        self._vector_store_instance: BaseVectorStore | None = None
        self._content_store_instance: "LocalTabularArtifacts | None" = None
        # The stage's admitted models: indexing installs its embedding, extraction its vision.
        self._embedding: tuple[InferenceAdmission, Embeddings] | None = None
        self._vision: tuple[InferenceAdmission, BaseChatModel] | None = None
        self._document_models = DocumentModels(configuration.inference_credentials)
        self._kpi_writer: BaseKPIWriter | None = None
        self._corpus_lock = threading.Lock()
        self._corpus_stores: dict[tuple, BaseVectorStore] = {}
        validate_profile_input_processor_config(configuration)
        validate_output_processor_config(configuration)
        validate_attachment_processor_config(configuration)
        self.input_processor_registry = self._load_input_processor_registry()
        self.output_processor_registry = self._load_output_processor_registry()
        ApplicationContext._instance = self

    async def shutdown(self) -> None:
        await http_clients.async_shutdown_shared_clients()

    def is_tabular_file(self, file_name: str) -> bool:
        """
        Returns True if the file is handled by a tabular input processor.
        This allows detecting if a file should produce a dataset-centric
        Parquet artifact for the tabular runtime.
        """
        ext = Path(file_name).suffix.lower()
        try:
            processor = self.get_input_processor_instance(ext)
            return isinstance(processor, BaseTabularProcessor)
        except ValueError:
            return False

    def is_spreadsheet_file(self, file_name: str) -> bool:
        """
        Returns True if the file belongs to the "spreadsheet" category.
        Spreadsheet documents keep the markdown preview flow (output.md) but
        route their output stage to per-table Parquet registration
        (SQL_INDEXED) instead of vectorization.
        """
        ext = Path(file_name).suffix.lower()
        return EXTENSION_CATEGORY.get(ext) == "spreadsheet"

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
            self._output_processor_instances[class_path] = processor_class(context=self) if getattr(self, "_inject_processor_context", False) else processor_class()

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
        registry: Dict[str, Type[BaseInputProcessor]] = {}
        default_profile = self.configuration.processing.default_profile
        profile_cfg = self.configuration.processing.get_profile_config(default_profile)

        for entry in profile_cfg.input_processors:
            cls = self._dynamic_import(entry.class_path)
            if not issubclass(cls, BaseInputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseProcessor")
            suffix = entry.suffix.lower()
            logger.debug(
                "Loaded input processor: %s for default profile=%s suffix=%s",
                entry.class_path,
                default_profile.value,
                suffix,
            )
            registry[suffix] = cls

        if not registry:
            raise ValueError(
                f"No input processors configured for default profile '{default_profile.value}'",
            )
        return registry

    def _load_output_processor_registry(self) -> Dict[str, Type[BaseOutputProcessor]]:
        registry = {}
        if not self.configuration.output_processors:
            return registry
        for entry in self.configuration.output_processors:
            cls = self._dynamic_import(entry.class_path)
            if not issubclass(cls, BaseOutputProcessor):
                raise TypeError(f"{entry.class_path} is not a subclass of BaseOutputProcessor")
            logger.debug(f"Loaded output processor: {entry.class_path} for prefix: {entry.suffix}")
            registry[entry.suffix.lower()] = cls
        return registry

    def get_config(self) -> Configuration:
        """
        Get the application configuration. This corresponds to the initial YAML file
        loaded at startup.
        """
        return self.configuration

    def _get_input_processor_class(self, extension: str) -> Optional[Type[BaseInputProcessor]]:
        """
        Get the input processor class for a given file extension. The mapping is
        resolved from processing.default_profile.input_processors.
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

    def get_content_store(self) -> "LocalTabularArtifacts":
        """Return the attempt-local writer installed by scoped_pipeline."""
        if self._content_store_instance is None:
            raise RuntimeError("Tabular artifacts require a manager processing attempt")
        return self._content_store_instance

    def admit_models(self, models) -> None:
        """Install one stage's admitted models (a manager-processing `StageModels`)."""
        self._embedding = (models.embedding, self._document_models.embeddings(models.embedding)) if models.embedding else None
        self._vision = (models.vision, self._document_models.chat(models.vision)) if models.vision else None

    def get_embedder(self) -> Embeddings:
        """The corpus embedding model the Control Plane admitted for this indexing stage."""
        if self._embedding is None:
            raise RuntimeError("No embedding model was admitted for this stage")
        return self._embedding[1]

    def get_vision(self) -> tuple[BaseChatModel, str] | None:
        """The organization's admitted image-description model and its name, if chosen."""
        if self._vision is None:
            return None
        admission, model = self._vision
        return model, admission.selection.key.upstream_model_id

    def get_vector_store(self) -> BaseVectorStore:
        """The attempt-scoped vector writer installed by scoped_pipeline."""
        if self._vector_store_instance is not None:
            return self._vector_store_instance
        raise ValueError("Vector store is not initialized. Use get_create_vector_store() instead.")

    def get_create_vector_store(self, embedding_model: Embeddings, *, read_only: bool = False) -> BaseVectorStore:
        """The attempt-scoped vector writer; only a processing attempt installs one."""
        if self._vector_store_instance is not None:
            return self._vector_store_instance
        raise ValueError("Vector writes require a manager processing attempt")

    def get_corpus_store(self, organization_id: UUID) -> BaseVectorStore:
        """The organization's corpus index, cached per process and admitted client.

        Indexing writes with the admitted embedding model, creating the index with its
        dimension. Without one, the store only deletes or flags existing vectors. Copies
        made by scoped_pipeline share this cache: the key carries the admission's client
        identity, so a new source revision or connection never reuses an older client."""
        settings = self.configuration.manager_processing
        if settings is None:
            raise ValueError("Manager processing is not configured")
        admission = self._embedding[0] if self._embedding else None
        key = (organization_id, DocumentModels.identity(admission) if admission else None)
        with self._corpus_lock:
            if key not in self._corpus_stores:
                instance = build_vector_store(
                    self._embedding[1] if self._embedding else None,
                    settings.vector_store,
                    organization_id=organization_id,
                    embedding_model_name=admission.selection.key.upstream_model_id if admission else "none",
                    opensearch_config=self.configuration.storage.opensearch,
                    postgres_config=self.configuration.storage.postgres,
                    kpi=self.get_kpi_writer(),
                    splitter=self.get_text_splitter(),
                )
                instance.strict_operations = True
                self._corpus_stores[key] = instance
            return self._corpus_stores[key]

    def get_kpi_writer(self) -> BaseKPIWriter:
        if self._kpi_writer is not None:
            return self._kpi_writer

        self._kpi_writer = build_kpi_writer(
            kpi_config=self.configuration.observability.kpi,
            opensearch_config=self.configuration.storage.opensearch,
            service_name="knowledge-flow",
            log_level=self.configuration.app.log_level,
        )
        return self._kpi_writer

    def get_text_splitter(self) -> BaseTextSplitter:
        """
        Factory method to create a text splitter instance based on configuration.
        Returns the semantic Markdown splitter for the active processing profile.
        """
        profile = get_current_processing_profile()
        profile_cfg = self.configuration.processing.get_profile_config(profile)
        splitter_cfg = profile_cfg.text_splitter
        return SemanticSplitter(
            chunk_size=splitter_cfg.chunk_size,
            chunk_overlap=splitter_cfg.chunk_overlap,
            preserve_tables=splitter_cfg.preserve_tables,
        )
