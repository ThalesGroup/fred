import logging
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List

from knowledge_flow_backend.application_context import EXTENSION_CATEGORY, ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.processors.input.common.base_input_processor import (
    BaseInputProcessor,
    BaseMarkdownProcessor,
    BaseTabularProcessor,
    InputConversionError,
)
from knowledge_flow_backend.core.processors.output.base_library_output_processor import LibraryOutputProcessor
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor

logger = logging.getLogger(__name__)


@dataclass
class ProcessingPipeline:
    """
    Library-aware ingestion pipeline.

    For now this is instantiated once as the default pipeline and mirrors
    the existing behaviour driven by configuration.input_processors and
    configuration.output_processors.

    Later, additional pipelines (e.g. 'CIR') can be created and associated
    with libraries without changing the core ingestion logic.
    """

    name: str
    input_processors: Dict[str, BaseInputProcessor] = field(default_factory=dict)
    output_processors: Dict[str, List[BaseOutputProcessor]] = field(default_factory=dict)
    library_output_processors: List[LibraryOutputProcessor] = field(default_factory=list)

    @classmethod
    def build_default(cls, context: ApplicationContext) -> "ProcessingPipeline":
        """
        Build the default pipeline from the existing configuration.

        This preserves current behaviour:
        - One input processor per extension (from configuration.input_processors).
        - One output processor per extension (or defaulted via EXTENSION_CATEGORY).
        - Optional library-level processors (if configured).
        """
        input_processors: Dict[str, BaseInputProcessor] = {}
        output_processors: Dict[str, List[BaseOutputProcessor]] = {}
        library_output_processors: List[LibraryOutputProcessor] = []

        for ext in EXTENSION_CATEGORY.keys():
            try:
                inp = context.get_input_processor_instance(ext)
                input_processors[ext] = inp
            except ValueError:
                logger.debug("No input processor configured for extension %s; skipping in default pipeline.", ext)
                continue

            try:
                out_proc = context.get_output_processor_instance(ext)
                output_processors[ext] = [out_proc]
            except ValueError:
                logger.debug("No output processor configured for extension %s; skipping output pipeline.", ext)

        # Instantiate configured library-level processors if any
        cfg = context.get_config()
        for entry in cfg.library_output_processors or []:
            try:
                module_path, class_name = entry.class_path.rsplit(".", 1)
                module = __import__(module_path, fromlist=[class_name])
                cls_ref = getattr(module, class_name)
                if not issubclass(cls_ref, LibraryOutputProcessor):
                    raise TypeError(f"{entry.class_path} is not a LibraryOutputProcessor")
                library_output_processors.append(cls_ref())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to instantiate library output processor %s: %s", entry.class_path, exc)

        logger.info("[PROCESSOR][LIBRARY] Default LibraryProcessingPipeline built with extensions: %s", sorted(input_processors.keys()))
        return cls(
            name="default",
            input_processors=input_processors,
            output_processors=output_processors,
            library_output_processors=library_output_processors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_markdown_processor_result(
        *,
        input_path: pathlib.Path,
        processor_name: str,
        processor_result: object | None,
    ) -> None:
        """
        Backward-compatible guard for legacy processors that still return
        {"status": "error"} instead of raising.
        """
        if not isinstance(processor_result, dict):
            return

        status_raw = processor_result.get("status")
        if not isinstance(status_raw, str):
            return
        status = status_raw.strip().lower()
        if status not in {"error", "failed", "failure"}:
            return

        message_raw = processor_result.get("message")
        message = str(message_raw).strip() if message_raw is not None else ""
        suffix = f": {message}" if message else ""
        raise InputConversionError(f"Input processor '{processor_name}' reported status='{status}' for '{input_path.name}'{suffix}")

    @staticmethod
    def _validate_preview_output(
        *,
        output_dir: pathlib.Path,
        input_path: pathlib.Path,
        processor_name: str,
    ) -> None:
        """
        Ensure the input stage produced a non-empty preview file.
        """
        preview_candidates = ("output.md", "table.csv", "output.txt")
        for candidate_name in preview_candidates:
            candidate = output_dir / candidate_name
            if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
                return

        details: list[str] = []
        generated_files = sorted(item.name for item in output_dir.iterdir() if item.is_file()) if output_dir.exists() else []
        if generated_files:
            details.append(f"generated_files={generated_files}")

        details_suffix = f" ({'; '.join(details)})" if details else ""
        raise ValueError(f"Input processor '{processor_name}' failed to generate a non-empty preview for '{input_path.name}' in '{output_dir}'. Expected one of {preview_candidates}.{details_suffix}")

    def _get_input_processor(self, suffix: str) -> BaseInputProcessor:
        suffix = suffix.lower()
        if suffix in self.input_processors:
            return self.input_processors[suffix]
        raise ValueError(f"No input processor configured for extension '{suffix}' in pipeline '{self.name}'")

    def _get_output_pipeline(self, suffix: str) -> List[BaseOutputProcessor]:
        suffix = suffix.lower()
        if suffix in self.output_processors:
            return self.output_processors[suffix]
        return []

    # ------------------------------------------------------------------
    # Public API used by IngestionService
    # ------------------------------------------------------------------

    def process_input(self, input_path: pathlib.Path, output_dir: pathlib.Path, metadata: DocumentMetadata) -> None:
        """
        Run the input stage for a document.

        This mirrors IngestionService.process_input but goes through the
        library pipeline so that different pipelines can override this
        behaviour later.
        """
        suffix = input_path.suffix.lower()
        processor = self._get_input_processor(suffix)

        output_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(processor, BaseMarkdownProcessor):
            result = processor.convert_file_to_markdown(input_path, output_dir, metadata.document_uid)
            self._validate_markdown_processor_result(
                input_path=input_path,
                processor_name=processor.__class__.__name__,
                processor_result=result,
            )
            self._validate_preview_output(
                output_dir=output_dir,
                input_path=input_path,
                processor_name=processor.__class__.__name__,
            )
        elif isinstance(processor, BaseTabularProcessor):
            df = processor.convert_file_to_table(input_path)
            df.to_csv(output_dir / "table.csv", index=False)
            self._validate_preview_output(
                output_dir=output_dir,
                input_path=input_path,
                processor_name=processor.__class__.__name__,
            )
        else:
            raise RuntimeError(f"Unknown input processor type for: {input_path}")

    def process_output(self, input_file_name: str, output_dir: pathlib.Path, input_file_metadata: DocumentMetadata) -> DocumentMetadata:
        """
        Run the output stage for a document through a pipeline of processors.

        For now, the default pipeline contains a single processor (vectorization or
        tabular), but the structure supports multiple processors per extension.
        """
        suffix = pathlib.Path(input_file_name).suffix.lower()
        processors = self._get_output_pipeline(suffix)

        if not processors:
            raise ValueError(f"No output processors configured for extension '{suffix}'")

        if not output_dir.exists():
            raise ValueError(f"Output directory {output_dir} does not exist")
        if not output_dir.is_dir():
            raise ValueError(f"Output directory {output_dir} is not a directory")
        if not any(output_dir.glob("*.*")):
            raise ValueError(f"Output directory {output_dir} does not contain output files")

        file_to_process = next(output_dir.glob("*.*"))
        if file_to_process.suffix.lower() not in [".md", ".csv", ".duckdb"]:
            raise ValueError(f"Output file {file_to_process} is not a markdown, csv or duckdb file")
        if file_to_process.stat().st_size == 0:
            raise ValueError(f"Output file {file_to_process} is empty")

        file_to_process_abs_str = str(file_to_process.resolve())
        metadata = input_file_metadata

        for proc in processors:
            logger.debug("Running output processor %s for %s", proc.__class__.__name__, file_to_process_abs_str)
            metadata = proc.process(file_path=file_to_process_abs_str, metadata=metadata)

        return metadata
