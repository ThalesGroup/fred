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

import dataclasses
import inspect
import json
import json as _json
import logging
import pathlib
import shutil
import tempfile
import time
import uuid
from typing import Dict, List, Optional, Type

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.kpi import KPIActor, KPIWriter
from langchain_core.documents import Document
from pydantic import BaseModel

from knowledge_flow_backend.application_context import ApplicationContext, get_kpi_writer
from knowledge_flow_backend.common.structures import LibraryProcessorConfig, ProcessorConfig, Status
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, BaseTabularProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastTextOptions,
    FastTextResult,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_unstructured_text_processor import FastUnstructuredTextProcessingProcessor
from knowledge_flow_backend.core.processors.output.base_library_output_processor import LibraryOutputProcessor
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor
from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    BaseVectorStore,
)
from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService
from knowledge_flow_backend.features.scheduler.activities import input_process, output_process
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


class IngestionInput(BaseModel):
    tags: List[str] = []
    source_tag: str = "fred"


class ProcessingProgress(BaseModel):
    """
    Represents the progress of a file processing operation. It is used to report in
    real-time the status of the processing pipeline to the REST remote client.
    Attributes:
        step (str): The current step in the processing pipeline.
        filename (str): The name of the file being processed.
        status (str): The status of the processing operation.
        document_uid (Optional[str]): A unique identifier for the document, if available.
    """

    step: str
    filename: str
    status: Status
    error: Optional[str] = None
    document_uid: Optional[str] = None


def _dynamic_import_processor(class_path: str):
    """
    Lightweight dynamic import helper for processor classes.

    We keep this local to avoid exposing ApplicationContext internals while
    still allowing admins to assemble pipelines from known processor classes.
    """
    module_path, class_name = class_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def _derive_description(class_path: str) -> Optional[str]:
    """
    Attempt to build a concise, human-friendly description for a processor class.

    Prefers the first line of the class docstring; falls back to the class name
    when a docstring is not present.
    """
    try:
        cls = _dynamic_import_processor(class_path)
    except Exception:
        logger.debug("Unable to import %s to derive description", class_path, exc_info=True)
        return None

    explicit = getattr(cls, "description", None)
    if explicit:
        return str(explicit)

    getter = getattr(cls, "get_description", None)
    if callable(getter):
        try:
            value = getter()
            if value:
                return str(value)
        except Exception:
            logger.debug("get_description failed for %s", class_path, exc_info=True)

    doc = inspect.getdoc(cls) or ""
    if doc:
        first_line = doc.strip().splitlines()[0]
        if first_line:
            return first_line
    return cls.__name__


def _with_description(config: ProcessorConfig) -> ProcessorConfig:
    """
    Ensure ProcessorConfig instances always carry a description for UI display.
    """
    if config.description:
        return config

    description = _derive_description(config.class_path)
    if description:
        return config.model_copy(update={"description": description})
    return config


def _with_library_description(config: LibraryProcessorConfig) -> LibraryProcessorConfig:
    """
    Ensure LibraryProcessorConfig instances always carry a description for UI display.
    """
    if config.description:
        return config

    description = _derive_description(config.class_path)
    if description:
        return config.model_copy(update={"description": description})
    return config


class AvailableProcessorsResponse(BaseModel):
    """
    Describes the currently configured input and output processors that can be
    used to assemble processing pipelines.
    """

    input_processors: List[ProcessorConfig]
    output_processors: List[ProcessorConfig]
    library_output_processors: List[LibraryProcessorConfig]


class ProcessingPipelineDefinition(BaseModel):
    """
    Declarative definition of a processing pipeline.

    For now:
      - 'name' identifies the pipeline in the runtime registry.
      - 'input_processors' is optional; if omitted, defaults are used.
      - 'output_processors' must be provided as a mapping from suffix → list of class paths.
      - 'library_output_processors' is optional; if provided, these run at library scope.
    """

    name: str
    input_processors: Optional[List[ProcessorConfig]] = None
    output_processors: List[ProcessorConfig]
    library_output_processors: Optional[List[LibraryProcessorConfig]] = None


class PipelineAssignment(BaseModel):
    """
    Bind a processing pipeline to a library tag id.

    At runtime this populates ProcessingPipelineManager.tag_to_pipeline so that
    documents tagged with this library go through the selected pipeline.
    """

    library_tag_id: str
    pipeline_name: str


class ProcessingPipelineInfo(BaseModel):
    """
    Describes the effective processing pipeline for a library.

    Contains the pipeline name, whether it is the default for this library,
    and the flattened input/output processor configs per extension plus
    any library-level processors.
    """

    name: str
    is_default_for_library: bool
    input_processors: List[ProcessorConfig]
    output_processors: List[ProcessorConfig]
    library_output_processors: List[LibraryProcessorConfig]


def uploadfile_to_path(file: UploadFile) -> pathlib.Path:
    tmp_dir = tempfile.mkdtemp()
    filename = file.filename or "uploaded_file"
    tmp_path = pathlib.Path(tmp_dir) / filename
    with open(tmp_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    return tmp_path


def save_file_to_temp(source_file_path: pathlib.Path) -> pathlib.Path:
    """
    Copies the given local file into a new temp folder and returns the new path.
    """
    temp_dir = pathlib.Path(tempfile.mkdtemp()) / "input"
    temp_dir.mkdir(parents=True, exist_ok=True)

    target_path = temp_dir / source_file_path.name
    shutil.copyfile(source_file_path, target_path)
    logger.info(f"File copied to temporary location: {target_path}")
    return target_path


class IngestionController:
    """
    Controller for handling ingestion-related operations.
    This controller provides endpoints for uploading and processing documents.
    """

    def _build_fast_text_registry(self) -> Dict[str, Type[BaseFastTextProcessor]]:
        cfg = ApplicationContext.get_instance().get_config()
        registry: Dict[str, Type[BaseFastTextProcessor]] = {}
        if cfg.attachment_processors:
            for entry in cfg.attachment_processors:
                cls = _dynamic_import_processor(entry.class_path)
                if not issubclass(cls, BaseFastTextProcessor):
                    raise TypeError(f"{entry.class_path} is not a BaseFastTextProcessor")
                registry[entry.prefix.lower()] = cls
        if not registry:
            registry["*"] = FastUnstructuredTextProcessingProcessor
        return registry

    def _get_fast_text_processor(self, filename: str) -> BaseFastTextProcessor:
        ext = pathlib.Path(filename).suffix.lower()
        processor_class = self._fast_text_registry.get(ext) or self._fast_text_registry.get("*")
        if processor_class is None:
            raise HTTPException(status_code=400, detail=f"No fast text processor configured for '{ext or filename}'")
        class_path = f"{processor_class.__module__}.{processor_class.__name__}"
        if class_path not in self._fast_text_instances:
            self._fast_text_instances[class_path] = processor_class()
        return self._fast_text_instances[class_path]

    def __init__(self, router: APIRouter):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.service = IngestionService()
        self._fast_text_registry = self._build_fast_text_registry()
        self._fast_text_instances: Dict[str, BaseFastTextProcessor] = {}
        self.embedder = ApplicationContext.get_instance().get_embedder()
        self.vector_store: BaseVectorStore = ApplicationContext.get_instance().get_create_vector_store(self.embedder)
        logger.info("IngestionController initialized.")

        # ------------------------------------------------------------------
        # Processing pipeline management endpoints
        # ------------------------------------------------------------------

        @router.get(
            "/processing/pipelines/available-processors",
            tags=["Processing"],
            summary="List available input/output processors for pipelines",
            response_model=AvailableProcessorsResponse,
        )
        async def list_available_processors(
            user: KeycloakUser = Depends(get_current_user),
        ) -> AvailableProcessorsResponse:
            """
            Returns the processors currently configured in Fred that can be used
            to build processing pipelines.

            This is derived from the active configuration (input_processors and
            output_processors), falling back to default output processors when
            no explicit mapping is present.
            """
            app_context = ApplicationContext.get_instance()
            cfg = app_context.get_config()

            input_cfg = [_with_description(pc) for pc in cfg.input_processors]

            # For outputs: if explicit config exists, use it.
            # Otherwise, synthesise ProcessorConfig entries from the default pipeline.
            if cfg.output_processors:
                output_cfg = [_with_description(pc) for pc in cfg.output_processors]
            else:
                # Use the default pipeline to discover effective output processors
                from knowledge_flow_backend.core.processing_pipeline import ProcessingPipeline

                default_pipeline = ProcessingPipeline.build_default(app_context)
                output_cfg = []
                for suffix, procs in default_pipeline.output_processors.items():
                    for proc in procs:
                        class_path = f"{proc.__class__.__module__}.{proc.__class__.__name__}"
                        output_cfg.append(_with_description(ProcessorConfig(prefix=suffix, class_path=class_path)))

            library_output_cfg: List[LibraryProcessorConfig] = [_with_library_description(lp) for lp in cfg.library_output_processors or []]

            # Always expose the summarization output processor for markdown outputs,
            # so admins can choose to make summarization an explicit pipeline step.
            try:
                summary_class_path = "knowledge_flow_backend.core.processors.output.summarizer.summarization_output_processor.SummarizationOutputProcessor"
                # Avoid duplicates if it is already configured
                if not any(p.prefix.lower() == ".md" and p.class_path == summary_class_path for p in output_cfg):
                    output_cfg.append(
                        _with_description(ProcessorConfig(prefix=".md", class_path=summary_class_path)),
                    )
            except Exception:
                logger.exception("Failed to register SummarizationOutputProcessor in available processors list")

            # Expose a default library-level processor unless already present.
            try:
                toc_class_path = "knowledge_flow_backend.core.library_processors.library_toc_output_processor.LibraryTocOutputProcessor"
                if not any(p.class_path == toc_class_path for p in library_output_cfg):
                    library_output_cfg.append(_with_library_description(LibraryProcessorConfig(class_path=toc_class_path)))
            except Exception:
                logger.exception("Failed to register LibraryTocOutputProcessor in available processors list")

            return AvailableProcessorsResponse(
                input_processors=input_cfg,
                output_processors=output_cfg,
                library_output_processors=library_output_cfg,
            )

        @router.post(
            "/processing/pipelines",
            tags=["Processing"],
            summary="Register or update a processing pipeline (runtime only)",
        )
        async def register_processing_pipeline(
            definition: ProcessingPipelineDefinition,
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Register or update a named processing pipeline.

            Notes:
            - Pipelines are kept in-memory for now (no persistence).
            - Input processors are optional; when omitted, the default pipeline's
              input processors are reused.
            - Output processors must be valid classes importable as BaseOutputProcessor.
            """
            pipeline_manager = self.service.pipeline_manager

            from knowledge_flow_backend.core.processing_pipeline import ProcessingPipeline

            # Start from default pipeline, then override per definition.
            default_pipeline = pipeline_manager.default_pipeline

            input_map = dict(default_pipeline.input_processors)
            if definition.input_processors:
                for pc in definition.input_processors:
                    cls = _dynamic_import_processor(pc.class_path)
                    if not issubclass(cls, BaseMarkdownProcessor) and not issubclass(cls, BaseTabularProcessor):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Class {pc.class_path} is not a supported input processor.",
                        )
                    input_map[pc.prefix.lower()] = cls()

            output_map: dict[str, list[BaseOutputProcessor]] = {}
            for pc in definition.output_processors:
                cls = _dynamic_import_processor(pc.class_path)
                if not issubclass(cls, BaseOutputProcessor):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Class {pc.class_path} is not a BaseOutputProcessor.",
                    )
                output_map.setdefault(pc.prefix.lower(), []).append(cls())

            library_processors: list[LibraryOutputProcessor] = []
            for lp in definition.library_output_processors or []:
                cls = _dynamic_import_processor(lp.class_path)
                if not issubclass(cls, LibraryOutputProcessor):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Class {lp.class_path} is not a LibraryOutputProcessor.",
                    )
                library_processors.append(cls())

            pipeline = ProcessingPipeline(
                name=definition.name,
                input_processors=input_map,
                output_processors=output_map,
                library_output_processors=library_processors,
            )

            pipeline_manager.pipelines[definition.name] = pipeline

            return {"status": "ok", "name": definition.name}

        @router.post(
            "/processing/pipelines/assign-library",
            tags=["Processing"],
            summary="Assign a processing pipeline to a library tag (runtime only)",
        )
        async def assign_pipeline_to_library(
            assignment: PipelineAssignment,
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Assign an existing processing pipeline to a given library tag id.

            This updates the in-memory ProcessingPipelineManager.tag_to_pipeline map
            and affects subsequent ingestions for documents tagged with this library.
            """
            pipeline_manager = self.service.pipeline_manager

            if assignment.pipeline_name not in pipeline_manager.pipelines:
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{assignment.pipeline_name}' not found.",
                )

            pipeline_manager.tag_to_pipeline[assignment.library_tag_id] = assignment.pipeline_name

            return {"status": "ok", "library_tag_id": assignment.library_tag_id, "pipeline_name": assignment.pipeline_name}

        @router.get(
            "/processing/pipelines/library/{library_tag_id}",
            tags=["Processing"],
            summary="Get effective processing pipeline for a library tag",
            response_model=ProcessingPipelineInfo,
        )
        async def get_library_pipeline(
            library_tag_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ) -> ProcessingPipelineInfo:
            """
            Returns the pipeline currently associated with a library tag id.

            If no explicit pipeline is mapped to this tag, the default pipeline is returned
            and is_default_for_library is set to True.
            """
            pipeline_manager = self.service.pipeline_manager

            # Decide which pipeline name is in effect for this tag id
            mapped_name = pipeline_manager.tag_to_pipeline.get(library_tag_id)
            if mapped_name and mapped_name in pipeline_manager.pipelines:
                pipeline_name = mapped_name
                is_default = False
            else:
                pipeline_name = pipeline_manager.default_pipeline.name
                is_default = True

            pipeline = pipeline_manager.pipelines.get(pipeline_name, pipeline_manager.default_pipeline)

            # Reconstruct ProcessorConfig lists from instantiated processors
            input_cfg: List[ProcessorConfig] = []
            for prefix, proc in pipeline.input_processors.items():
                class_path = f"{proc.__class__.__module__}.{proc.__class__.__name__}"
                input_cfg.append(_with_description(ProcessorConfig(prefix=prefix, class_path=class_path)))

            output_cfg: List[ProcessorConfig] = []
            for prefix, procs in pipeline.output_processors.items():
                for proc in procs:
                    class_path = f"{proc.__class__.__module__}.{proc.__class__.__name__}"
                    output_cfg.append(_with_description(ProcessorConfig(prefix=prefix, class_path=class_path)))

            library_output_cfg: List[LibraryProcessorConfig] = []
            for proc in getattr(pipeline, "library_output_processors", []):
                class_path = f"{proc.__class__.__module__}.{proc.__class__.__name__}"
                library_output_cfg.append(_with_library_description(LibraryProcessorConfig(class_path=class_path)))

            return ProcessingPipelineInfo(
                name=pipeline_name,
                is_default_for_library=is_default,
                input_processors=input_cfg,
                output_processors=output_cfg,
                library_output_processors=library_output_cfg,
            )

        @router.post(
            "/upload-documents",
            tags=["Processing"],
            summary="Upload documents only — defer processing to backend (e.g., Temporal)",
        )
        async def upload_documents_sync(
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
            user: KeycloakUser = Depends(get_current_user),
        ) -> StreamingResponse:
            parsed_input = IngestionInput(**json.loads(metadata_json))
            tags = parsed_input.tags
            source_tag = parsed_input.source_tag

            preloaded_files = []
            for file in files:
                raw_path = uploadfile_to_path(file)
                input_temp_file = save_file_to_temp(raw_path)
                logger.info(f"File {file.filename} saved to temp storage at {input_temp_file}")
                preloaded_files.append((file.filename, input_temp_file))

            total = len(preloaded_files)

            async def event_stream():
                success = 0
                for filename, input_temp_file in preloaded_files:
                    current_step = "metadata extraction"
                    try:
                        output_temp_dir = input_temp_file.parent.parent
                        yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                        metadata = await self.service.extract_metadata(user, file_path=input_temp_file, tags=tags, source_tag=source_tag)
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                        current_step = "raw content saving"
                        yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                        self.service.save_input(user, metadata=metadata, input_dir=output_temp_dir / "input")
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                        current_step = "metadata saving"
                        yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                        await self.service.save_metadata(user, metadata=metadata)
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"
                        yield ProcessingProgress(step="Finished", filename=filename, status=Status.FINISHED, document_uid=metadata.document_uid).model_dump_json() + "\n"

                        success += 1

                    except Exception as e:
                        error_message = f"{type(e).__name__}: {str(e).strip() or 'No error message'}"
                        yield ProcessingProgress(step=current_step, status=Status.ERROR, error=error_message, filename=filename).model_dump_json() + "\n"

                overall_status = Status.SUCCESS if success == total else Status.ERROR
                yield json.dumps({"step": "done", "status": overall_status}) + "\n"

            return StreamingResponse(event_stream(), media_type="application/x-ndjson")

        @router.post(
            "/upload-process-documents",
            tags=["Processing"],
            summary="Upload and process documents immediately (end-to-end)",
            description="Ingest and process one or more documents synchronously in a single step.",
        )
        async def process_documents_sync(
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
            user: KeycloakUser = Depends(get_current_user),
            kpi: KPIWriter = Depends(get_kpi_writer),
        ) -> StreamingResponse:
            with kpi.timer(
                "api.request_latency_ms",
                dims={"route": "/upload-process-documents", "method": "POST"},
                actor=KPIActor(type="human", user_id=user.uid, groups=user.groups),
            ) as d:
                parsed_input = IngestionInput(**json.loads(metadata_json))
                tags = parsed_input.tags
                source_tag = parsed_input.source_tag

                preloaded_files = []
                for file in files:
                    raw_path = uploadfile_to_path(file)
                    input_temp_file = save_file_to_temp(raw_path)
                    logger.info(f"File {file.filename} saved to temp storage at {input_temp_file}")
                    preloaded_files.append((file.filename, input_temp_file))

                total = len(preloaded_files)

                async def event_stream():
                    success = 0
                    last_error: str | None = None
                    for filename, input_temp_file in preloaded_files:
                        file_started = time.perf_counter()
                        file_status = "error"
                        file_type = pathlib.Path(filename).suffix.lstrip(".") or None
                        try:
                            output_temp_dir = input_temp_file.parent.parent

                            current_step = "metadata extraction"
                            yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                            metadata = await self.service.extract_metadata(user, file_path=input_temp_file, tags=tags, source_tag=source_tag)
                            metadata_file_type = getattr(metadata, "file_type", None)
                            file_type = metadata_file_type or file_type
                            yield ProcessingProgress(step=current_step, status=Status.SUCCESS, filename=filename).model_dump_json() + "\n"

                            current_step = "input content saving"
                            yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                            self.service.save_input(user, metadata=metadata, input_dir=output_temp_dir / "input")
                            yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                            current_step = "input processing"
                            yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                            metadata = await input_process(user=user, input_file=input_temp_file, metadata=metadata)
                            yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                            current_step = "output processing"
                            file_to_process = FileToProcess(document_uid=metadata.document_uid, external_path=None, source_tag=source_tag, tags=tags, processed_by=user)
                            yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                            metadata = await output_process(file=file_to_process, metadata=metadata, accept_memory_storage=True)
                            yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"
                            yield ProcessingProgress(step="Finished", filename=filename, status=Status.FINISHED, document_uid=metadata.document_uid).model_dump_json() + "\n"
                            success += 1
                            file_status = "ok"

                        except Exception as e:
                            error_message = f"{type(e).__name__}: {str(e).strip() or 'No error message'}"
                            last_error = error_message
                            logger.exception("Ingestion error during '%s' for file '%s'", current_step, filename, exc_info=True)
                            yield ProcessingProgress(step=current_step, status=Status.ERROR, error=error_message, filename=filename).model_dump_json() + "\n"
                        finally:
                            duration_ms = (time.perf_counter() - file_started) * 1000.0
                            kpi.emit(
                                name="ingestion.document_duration_ms",
                                type="timer",
                                value=duration_ms,
                                unit="ms",
                                dims={"file_type": file_type, "status": file_status, "source": "api"},
                                actor=KPIActor(type="human", user_id=user.uid, groups=user.groups),
                            )
                    d["status"] = "ok" if success == total else "error"
                    overall_status = Status.SUCCESS if success == total else Status.ERROR
                    done_payload: dict = {"step": "done", "status": overall_status}
                    if last_error:
                        done_payload["error"] = last_error
                    yield json.dumps(done_payload) + "\n"

                return StreamingResponse(event_stream(), media_type="application/x-ndjson")

        @router.post(
            "/fast/text",
            tags=["Processing"],
            summary="Fast text extraction for a single file",
            description=(
                """
                Extract a compact text representation of a file without full ingestion.
                Supported: PDF, DOCX, CSV, PPTX, MD. Intended for agent use where fast, dependency-light text is needed.
            """
            ),
        )
        def fast_markdown(
            file: UploadFile = File(...),
            options_json: Optional[str] = Form(None, description="JSON string of FastTextOptions"),
            fmt: str = Query("json", alias="format", description="Response format: 'json' or 'text'"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            # Validate extension
            filename = file.filename or "uploaded"

            # Store to temp
            raw_path = uploadfile_to_path(file)

            # Parse options
            opts = FastTextOptions()
            if options_json:
                try:
                    payload = _json.loads(options_json)
                    if not isinstance(payload, dict):
                        raise ValueError("options_json must be an object")
                    allowed = {f.name for f in dataclasses.fields(FastTextOptions)}
                    filtered = {k: v for k, v in payload.items() if k in allowed}
                    opts = FastTextOptions(**filtered)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid options_json: {e}")

            # Extract
            try:
                logger.debug("[FAST TEXT] Extracting text for %s with options %s", filename, opts)
                result = self._get_fast_text_processor(filename).extract(raw_path, options=opts)
                logger.info(
                    "[FAST TEXT] user=%s file=%s format=%s chars=%s pages=%s  truncated=%s",
                    user.uid,
                    filename,
                    fmt,
                    result.total_chars,
                    result.page_count,
                    result.truncated,
                )
                if not result.text or result.total_chars == 0:
                    logger.warning(
                        "[FAST TEXT] EMPTY FILE user=%s file=%s format=%s (page_count=%s truncated=%s)",
                        user.uid,
                        filename,
                        fmt,
                        result.page_count,
                        result.truncated,
                    )
            except Exception as e:
                logger.error(f"[FAST TEXT] Extraction failed for {filename}: {e}", exc_info=True)
                raise HTTPException(status_code=400, detail=str(e))
            finally:
                # Best-effort cleanup of temp file; containing dir will be removed separately if needed
                try:
                    raw_path.unlink(missing_ok=True)
                    # remove parent temp dir if empty
                    parent = raw_path.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    logger.warning(f"Failed to clean up temporary file: {raw_path}")
                    pass

            if fmt.lower() == "text":
                return Response(content=result.text, media_type="text/plain; charset=utf-8")

            # Default JSON payload
            return {
                "document_name": result.document_name,
                "total_chars": result.total_chars,
                "truncated": result.truncated,
                "text": result.text,
                "pages": [{"page_no": p.page_no, "char_count": p.char_count, "markdown": p.text} for p in (result.pages or [])],
                "extras": result.extras or {},
            }

        @router.post(
            "/fast/ingest",
            tags=["Processing"],
            summary="Fast ingest of a single file (fast path for attachments)",
            description=(
                """
                Extract compact text via the fast processor and store it as vectors with user/session scoping.
                Skips heavy pandoc/Temporal paths.
            """
            ),
        )
        def fast_ingest(
            file: UploadFile = File(...),
            options_json: Optional[str] = Form(None, description="JSON string of FastTextOptions"),
            session_id: Optional[str] = Form(None, description="Optional chat session id for scoping"),
            scope: str = Form("session", description="Logical scope label, default 'session'"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Fast path for chat attachments:
            - use fast text extractor
            - store as a single vectorized document with user/session metadata
            """
            filename = file.filename or "uploaded"

            # Parse options
            opts = FastTextOptions()
            if options_json:
                try:
                    payload = _json.loads(options_json)
                    if not isinstance(payload, dict):
                        raise ValueError("options_json must be an object")
                    allowed = {f.name for f in dataclasses.fields(FastTextOptions)}
                    filtered = {k: v for k, v in payload.items() if k in allowed}
                    opts = FastTextOptions(**filtered)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid options_json: {e}")

            # Store to temp
            raw_path = uploadfile_to_path(file)

            # Extract fast text
            result: FastTextResult
            try:
                result = self._get_fast_text_processor(filename).extract(raw_path, options=opts)
                logger.info(
                    "[FAST TEXT][INGEST] user=%s file=%s chars=%s pages=%s truncated=%s",
                    user.uid,
                    filename,
                    result.total_chars,
                    result.page_count,
                    result.truncated,
                )
                text = result.text or ""
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
            finally:
                try:
                    raw_path.unlink(missing_ok=True)
                    parent = raw_path.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    logger.warning(f"Failed to clean up temporary file: {raw_path}")
                    pass

            docs: list[Document] = []
            document_uid = uuid.uuid4().hex

            if result.pages:
                # Ingest per-page to keep chunks smaller and recall higher.
                for p in result.pages:
                    chunk_uid = uuid.uuid4().hex
                    doc_meta = {
                        "document_uid": document_uid,
                        CHUNK_ID_FIELD: chunk_uid,
                        "file_name": filename,
                        "document_name": filename,
                        "title": filename,
                        "user_id": user.uid,
                        "session_id": session_id,
                        "scope": scope,
                        "retrievable": True,
                        "source": "fast_ingest",
                        "page": p.page_no,
                    }
                    docs.append(Document(page_content=p.text or "", metadata=doc_meta))
            else:
                # Single combined doc fallback
                if not text.strip():
                    text = "_(empty markdown extracted)_"
                chunk_uid = uuid.uuid4().hex
                doc_meta = {
                    "document_uid": document_uid,
                    CHUNK_ID_FIELD: chunk_uid,
                    "file_name": filename,
                    "document_name": filename,
                    "title": filename,
                    "user_id": user.uid,
                    "session_id": session_id,
                    "scope": scope,
                    "retrievable": True,
                    "source": "fast_ingest",
                }
                docs.append(Document(page_content=text, metadata=doc_meta))

            try:
                ids = self.vector_store.add_documents(docs)
                chunks = len(ids) if isinstance(ids, (list, tuple, set)) else len(docs)
                logger.info(
                    "[FAST TEXT][INGEST] Stored vectors doc_uid=%s chunks=%d user=%s session=%s scope=%s per_page=%s",
                    document_uid,
                    chunks,
                    user.uid,
                    session_id,
                    scope,
                    bool(result.pages),
                )
            except Exception:
                logger.exception("[FAST TEXT][INGEST] Failed to store vectors for %s", filename)
                raise HTTPException(status_code=500, detail="Failed to store vectors")

            return {
                "document_uid": document_uid,
                "chunks": chunks,
                "total_chars": result.total_chars,
                "truncated": result.truncated,
                "scope": scope,
            }

        @router.delete(
            "/fast/ingest/{document_uid}",
            tags=["Processing"],
            summary="Delete vectors for a fast ingested document",
            description="Remove vectors created via /fast/ingest (identified by document_uid).",
        )
        def delete_fast_ingest(
            document_uid: str,
            session_id: Optional[str] = Query(None, description="Optional session_id for scoped cleanup"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                logger.info(
                    "[FAST TEXT][INGEST][DELETE] user=%s doc_uid=%s session=%s backend=%s",
                    user.uid,
                    document_uid,
                    session_id,
                    self.vector_store.__class__.__name__,
                )
                self.vector_store.delete_vectors_for_document(document_uid=document_uid)
                logger.info(
                    "[FAST TEXT][INGEST] Deleted vectors for doc_uid=%s user=%s session=%s",
                    document_uid,
                    user.uid,
                    session_id,
                )
            except Exception:
                logger.exception(
                    "[FAST TEXT][INGEST] Failed to delete vectors for doc_uid=%s",
                    document_uid,
                )
                raise HTTPException(status_code=500, detail="Failed to delete vectors")
            return {"status": "ok", "document_uid": document_uid, "session_id": session_id}
