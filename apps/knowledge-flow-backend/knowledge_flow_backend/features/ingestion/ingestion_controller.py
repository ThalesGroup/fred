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
import json
import json as _json
import logging
import pathlib
import shutil
import tempfile
import time
import uuid
from typing import Dict, List, Optional, Type

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from fred_core import KeycloakUser, TeamMetadataStore, get_current_user
from fred_core.common.team_id import TeamId
from fred_core.kpi import KPIActor, KPIWriter
from fred_core.scheduler import SchedulerBackend
from langchain_core.documents import Document
from pydantic import BaseModel

from knowledge_flow_backend.application_context import ApplicationContext, get_kpi_writer
from knowledge_flow_backend.common.structures import (
    IngestionProcessingProfile,
    Status,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastTextOptions,
    FastTextResult,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_csv_processor import (
    FastLiteCsvProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_docx_processor import (
    FastLiteDocxProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor import (
    FastLiteImageProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pdf_processor import FastLitePdfProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pptx_processor import (
    FastLitePptxProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_plain_text_processor import (
    FastPlainTextProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_spreadsheet_processor import (
    FastSpreadsheetProcessor,
)
from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    BaseVectorStore,
)
from knowledge_flow_backend.features.filesystem.workspace_storage_service import (
    WorkspaceStorageService,
)
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.scheduler.activities import output_process
from knowledge_flow_backend.features.scheduler.push_files_activities import push_input_process
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    FileToProcess,
    FileToProcessWithoutUser,
)

logger = logging.getLogger(__name__)

STEP_UPLOAD_PREPARATION = "upload preparation"
STEP_QUEUED_FOR_PROCESSING = "queued for processing"
STEP_PROCESSING = "processing"
STEP_FINISHED = "Finished"


class IngestionInput(BaseModel):
    tags: List[str] = []
    source_tag: str = "fred"
    profile: IngestionProcessingProfile | None = None


class ProcessingProgress(BaseModel):
    """
    Represents the progress of a file processing operation. It is used to report in
    real-time the status of the processing pipeline to the REST remote client.
    Attributes:
        step (str): The current step in the processing pipeline.
        filename (str): The name of the file being processed.
        status (str): The status of the processing operation.
        document_uid (Optional[str]): A unique identifier for the document, if available.

    Steps are emitted as high-level phases:
        - upload preparation
        - queued for processing
        - processing
        - Finished
    """

    step: str
    filename: str
    status: Status
    error: Optional[str] = None
    document_uid: Optional[str] = None
    task_id: Optional[str] = None


def _dynamic_import_processor(class_path: str):
    """
    Lightweight dynamic import helper for processor classes.

    We keep this local to avoid exposing ApplicationContext internals while
    still allowing admins to assemble pipelines from known processor classes.
    """
    module_path, class_name = class_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def uploadfile_to_path(file: UploadFile) -> pathlib.Path:
    """
    Persist one uploaded file into a single temporary work directory.

    Why this exists:
    - Large uploads should be written once to disk and then reused by the rest
      of the ingestion pipeline.
    - Keeping the file under `<temp>/input/` preserves the existing workdir
      layout expected by downstream processors.

    How to use:
    - Pass the FastAPI `UploadFile`.
    - The returned path always points to `<temp>/input/<filename>`.
    """
    tmp_dir = pathlib.Path(tempfile.mkdtemp()) / "input"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "uploaded_file"
    tmp_path = tmp_dir / filename
    with open(tmp_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    return tmp_path


def cleanup_uploaded_temp_file(file_path: pathlib.Path) -> None:
    """
    Remove one temporary upload work directory created by `uploadfile_to_path`.

    Why this exists:
    - End-to-end ingestion persists uploads into the shared content store, so
      the API-side temporary workdir should be deleted once that hand-off or
      synchronous processing path finishes.
    - Keeping one cleanup helper avoids duplicating slightly different `/tmp`
      deletion logic across ingestion endpoints.

    How to use:
    - Pass the exact path returned by `uploadfile_to_path(...)`.
    - The helper removes the parent temporary workdir recursively with
      best-effort logging and never raises on cleanup failures.

    Example:
    - `cleanup_uploaded_temp_file(uploadfile_to_path(file))`
    """
    temp_root = file_path.parent.parent
    try:
        if temp_root.exists():
            shutil.rmtree(temp_root)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to clean up temporary upload workdir: %s", temp_root, exc_info=True)


class IngestionController:
    """
    Controller for handling ingestion-related operations.
    This controller provides endpoints for uploading and processing documents.
    """

    def _build_fast_text_registry(self) -> Dict[str, Type[BaseFastTextProcessor]]:
        cfg = ApplicationContext.get_instance().get_config()
        registry: Dict[str, Type[BaseFastTextProcessor]] = {}
        if cfg.attachment_processors:
            # Watch out this makes it possible to configure arbitrary class paths, but since this is an admin-level config and we require the classes to be a known base type.
            # More importantly the processors in action here must absolutely be fast and lightweight, so we don't want to allow arbitrary processor classes that might do heavy
            # processing or have large dependencies. These fast processors re used whenever user attach files to their conversations, so they need to be optimized for speed and low resource usage
            # to keep the user experience smooth.
            for entry in cfg.attachment_processors:
                cls = _dynamic_import_processor(entry.class_path)
                if not issubclass(cls, BaseFastTextProcessor):
                    raise TypeError(f"{entry.class_path} is not a BaseFastTextProcessor")
                suffix = entry.suffix.lower()
                if suffix.startswith("*."):
                    suffix = suffix[1:]
                registry[suffix] = cls
        if not registry:
            registry[".pdf"] = FastLitePdfProcessor
            registry[".docx"] = FastLiteDocxProcessor
            registry[".pptx"] = FastLitePptxProcessor
            registry[".csv"] = FastLiteCsvProcessor
            registry[".txt"] = FastPlainTextProcessor
            registry[".md"] = FastPlainTextProcessor
            registry[".xlsx"] = FastSpreadsheetProcessor
            registry[".xls"] = FastSpreadsheetProcessor
            registry[".xlsm"] = FastSpreadsheetProcessor
            registry[".png"] = FastLiteImageProcessor
            registry[".jpg"] = FastLiteImageProcessor
            registry[".jpeg"] = FastLiteImageProcessor
            registry[".gif"] = FastLiteImageProcessor
            registry[".bmp"] = FastLiteImageProcessor
            registry[".svg"] = FastLiteImageProcessor
            registry[".webp"] = FastLiteImageProcessor
            registry[".ico"] = FastLiteImageProcessor
        logger.info(f"[INGESTION][FAST TEXT] Fast text processor registry: {registry}")
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

    def _preload_uploaded_files(self, files: List[UploadFile]) -> list[tuple[str, pathlib.Path]]:
        preloaded_files: list[tuple[str, pathlib.Path]] = []
        for file in files:
            filename = file.filename or "uploaded_file"
            input_temp_file = uploadfile_to_path(file)
            logger.info(f"File {filename} saved to temp storage at {input_temp_file}")
            preloaded_files.append((filename, input_temp_file))
        return preloaded_files

    def _scheduler_backend(self) -> SchedulerBackend:
        if self.scheduler_task_service is None:
            return SchedulerBackend.MEMORY
        return ApplicationContext.get_instance().get_scheduler_backend()

    @staticmethod
    def _format_exception_message(exc: Exception) -> str:
        return f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"

    @staticmethod
    def _progress_event(
        *,
        step: str,
        status: Status,
        filename: str,
        document_uid: Optional[str] = None,
        error: Optional[str] = None,
    ) -> str:
        return (
            ProcessingProgress(
                step=step,
                status=status,
                filename=filename,
                document_uid=document_uid,
                error=error,
            ).model_dump_json()
            + "\n"
        )

    async def _store_fast_vectors(self, *, document_uid: str, docs: list[Document]) -> tuple[str, int]:
        payload = {"documents": [{"page_content": d.page_content, "metadata": d.metadata} for d in docs]}
        if self.scheduler_task_service is None:
            ids = self.vector_store.add_documents(docs)
            chunks = len(ids) if isinstance(ids, (list, tuple, set)) else len(docs)
            return SchedulerBackend.MEMORY.value, chunks

        result = await self.scheduler_task_service.store_fast_vectors(payload=payload)
        chunks = int((result or {}).get("chunks", len(docs)))
        return self._scheduler_backend().value, chunks

    async def _delete_fast_vectors(self, *, document_uid: str) -> str:
        if self.scheduler_task_service is None:
            self.vector_store.delete_vectors_for_document(document_uid=document_uid)
            return SchedulerBackend.MEMORY.value

        await self.scheduler_task_service.delete_fast_vectors(payload={"document_uid": document_uid})
        return self._scheduler_backend().value

    async def _delete_fast_ingest_artifacts(
        self,
        *,
        user: KeycloakUser,
        document_uid: str,
        storage_key: str | None,
    ) -> str:
        """
        Delete one fast-ingested document plus its optional uploaded source file.

        Why this exists:
        - chat attachments need a single cleanup path that removes both the
          retrieval artifacts and the uploaded object from user storage

        How to use:
        - call from the DELETE `/fast/delete/{document_uid}` route
        - pass `storage_key` when the attachment originated from
          `/storage/user/upload`
        """

        scheduler_backend = await self._delete_fast_vectors(document_uid=document_uid)
        if storage_key:
            await self.workspace_storage_service.delete_user_file(user, storage_key)
        return scheduler_backend

    async def _check_quota_before_upload(self, files: List[UploadFile], tags: List[str], user: KeycloakUser) -> None:
        if not tags:
            return

        total_upload_size = 0
        for f in files:
            file_size = getattr(f, "size", None)
            if file_size is not None:
                total_upload_size += file_size
            else:
                f.file.seek(0, 2)
                total_upload_size += f.file.tell()
                f.file.seek(0)

        if total_upload_size <= 0:
            return

        tag_store = ApplicationContext.get_instance().get_tag_store()
        rebac = ApplicationContext.get_instance().get_rebac_engine()

        team_ids: set[str] = set()
        user_ids: set[str] = set()
        for tag_id in tags:
            tag = await tag_store.get_tag_by_id(tag_id)
            if not tag or not tag.owner_id:
                continue

            resolved_for_tag: list[str] = []
            try:
                from fred_core import RebacDisabledResult, RebacReference, RelationType, Resource

                subjects = await rebac.lookup_subjects(RebacReference(type=Resource.TAGS, id=tag.id), RelationType.OWNER, Resource.TEAM)
                if not isinstance(subjects, RebacDisabledResult) and subjects:
                    for sub in subjects:
                        resolved_for_tag.append(sub.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not resolve team owners via ReBAC for tag '%s'; falling back to team metadata lookup: %s",
                    tag.id,
                    exc,
                )

            if not resolved_for_tag:
                try:
                    engine = ApplicationContext.get_instance().get_pg_async_engine()
                    store = TeamMetadataStore(engine)
                    meta = await store.get_by_team_id(TeamId(tag.owner_id))
                    if meta is not None:
                        resolved_for_tag.append(tag.owner_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Could not confirm team ownership for tag '%s' via team metadata lookup: %s",
                        tag.id,
                        exc,
                    )

            if resolved_for_tag:
                for t_id in resolved_for_tag:
                    if t_id.startswith("personal-"):
                        user_ids.add(t_id[len("personal-") :])
                    else:
                        team_ids.add(t_id)
            else:
                owner_id = tag.owner_id
                if owner_id == "personal" or owner_id is None:
                    owner_id = user.uid
                elif owner_id.startswith("personal-"):
                    owner_id = owner_id[len("personal-") :]
                user_ids.add(owner_id)

        cfg = ApplicationContext.get_instance().get_config()

        if team_ids:
            default_limit = cfg.app.default_team_max_resources_storage_size
            engine = ApplicationContext.get_instance().get_pg_async_engine()
            store = TeamMetadataStore(engine)
            for team_id in team_ids:
                allowed, current, max_size = await store.check_quota(TeamId(team_id), total_upload_size, default_limit=default_limit)
                if not allowed:
                    limit_str = f"{max_size} bytes" if max_size else "unlimited"
                    raise HTTPException(
                        status_code=400,
                        detail=f"Storage quota exceeded for team '{team_id}': limit is {limit_str}, current usage is {current} bytes, attempting to upload {total_upload_size} bytes.",
                    )

        personal_limit = cfg.app.personal_max_resources_storage_size
        if user_ids and personal_limit is not None and personal_limit > 0:
            from uuid import UUID

            from fred_core import get_user_store

            user_store = get_user_store()
            for user_id_str in user_ids:
                try:
                    user_uuid = UUID(user_id_str)
                    user_row = await user_store.find_user_by_id(user_uuid)
                    current = user_row.current_resources_storage_size or 0 if user_row else 0
                except (ValueError, Exception):  # noqa: BLE001
                    current = 0

                if current + total_upload_size > personal_limit:
                    limit_str = f"{personal_limit} bytes"
                    raise HTTPException(
                        status_code=400,
                        detail=f"Storage quota exceeded for personal space: limit is {limit_str}, current usage is {current} bytes, attempting to upload {total_upload_size} bytes.",
                    )

    async def _stream_upload_process(
        self,
        *,
        preloaded_files: list[tuple[str, pathlib.Path]],
        user: KeycloakUser,
        tags: list[str],
        source_tag: str,
        profile: IngestionProcessingProfile,
        scheduler_task_service: IngestionTaskService | None,
        background_tasks: BackgroundTasks | None,
        kpi: KPIWriter,
        kpi_actor: KPIActor,
        timer_dims: dict,
    ):
        success = 0
        last_error: str | None = None
        total = len(preloaded_files)
        scheduled_candidates: list[tuple[str, str, str | None, str | None]] = []

        for filename, input_temp_file in preloaded_files:
            file_started = time.perf_counter()
            file_status = "error"
            file_type = pathlib.Path(filename).suffix.lstrip(".") or None
            current_step = STEP_UPLOAD_PREPARATION
            try:
                output_temp_dir = input_temp_file.parent.parent

                yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                metadata = await self.service.extract_metadata(
                    user,
                    file_path=input_temp_file,
                    tags=tags,
                    source_tag=source_tag,
                    profile=profile,
                )
                metadata_file_type = getattr(metadata, "file_type", None)
                file_type = metadata_file_type or file_type
                self.service.save_input(user, metadata=metadata, input_dir=output_temp_dir / "input")

                if scheduler_task_service is None:
                    yield (
                        ProcessingProgress(
                            step=current_step,
                            status=Status.SUCCESS,
                            filename=filename,
                            document_uid=metadata.document_uid,
                        ).model_dump_json()
                        + "\n"
                    )

                    current_step = STEP_PROCESSING
                    yield ProcessingProgress(step=current_step, status=Status.IN_PROGRESS, filename=filename).model_dump_json() + "\n"
                    metadata = await push_input_process(user=user, metadata=metadata, input_file=str(input_temp_file), profile=profile)
                    file_to_process = FileToProcess(
                        document_uid=metadata.document_uid,
                        external_path=None,
                        source_tag=source_tag,
                        tags=tags,
                        profile=profile,
                        processed_by=user,
                    )
                    metadata = await output_process(file=file_to_process, metadata=metadata, accept_memory_storage=True)
                    yield (
                        ProcessingProgress(
                            step=current_step,
                            status=Status.SUCCESS,
                            filename=filename,
                            document_uid=metadata.document_uid,
                        ).model_dump_json()
                        + "\n"
                    )
                    yield (
                        ProcessingProgress(
                            step=STEP_FINISHED,
                            status=Status.FINISHED,
                            filename=filename,
                            document_uid=metadata.document_uid,
                        ).model_dump_json()
                        + "\n"
                    )
                    success += 1
                    file_status = "ok"
                else:
                    await self.service.save_metadata(user, metadata=metadata)

                    # OPS-04: create a task_run row so SSE events can be tracked
                    file_task_id: Optional[str] = None
                    try:
                        task_svc = ApplicationContext.get_instance().get_task_service()
                        if task_svc is not None:
                            from fred_core.tasks.models import StartIngestionParams, StartIngestionRequest, TaskTarget

                            req = StartIngestionRequest(params=StartIngestionParams(resource_ids=[metadata.document_uid]))
                            # Set the target at creation so the document row's indicator survives a
                            # reload even when no worker is running to emit the first event.
                            target = TaskTarget(
                                type="document",
                                id=metadata.document_uid,
                                label=metadata.document_name or metadata.document_uid,
                            )
                            resp = await task_svc.start(req, created_by=user.uid, target=target)
                            file_task_id = resp.task_id
                    except Exception:
                        logger.warning("OPS-04: could not create task_run for %s — tray tracking disabled", filename, exc_info=True)

                    yield (
                        ProcessingProgress(
                            step=current_step,
                            status=Status.SUCCESS,
                            filename=filename,
                            document_uid=metadata.document_uid,
                            task_id=file_task_id,
                        ).model_dump_json()
                        + "\n"
                    )

                    scheduled_candidates.append((filename, metadata.document_uid, file_type, file_task_id))
                    file_status = "queued"
            except Exception as e:
                error_message = self._format_exception_message(e)
                last_error = error_message
                logger.exception("Ingestion error during '%s' for file '%s'", current_step, filename, exc_info=True)
                yield self._progress_event(step=current_step, status=Status.FAILED, filename=filename, error=error_message)
            finally:
                cleanup_uploaded_temp_file(input_temp_file)
                duration_ms = (time.perf_counter() - file_started) * 1000.0
                kpi.emit(
                    name="ingestion.document_duration_ms",
                    type="timer",
                    value=duration_ms,
                    unit="ms",
                    dims={"file_type": file_type, "status": file_status, "source": "api"},
                    actor=kpi_actor,
                )

        if scheduler_task_service is not None and scheduled_candidates:
            current_step = STEP_QUEUED_FOR_PROCESSING
            try:
                files_to_schedule = [
                    FileToProcessWithoutUser(
                        source_tag=source_tag,
                        tags=tags,
                        document_uid=document_uid,
                        display_name=filename,
                        profile=profile,
                        task_id=task_id,
                    )
                    for filename, document_uid, _, task_id in scheduled_candidates
                ]
                scheduler_background_tasks = background_tasks
                # For streaming responses, FastAPI BackgroundTasks run only after
                # the stream completes; this would prevent live progress updates
                # with the in-memory scheduler.
                if self._scheduler_backend() == SchedulerBackend.MEMORY:
                    scheduler_background_tasks = None
                _, handle = await scheduler_task_service.submit_documents(
                    user=user,
                    pipeline_name="upload_ui_async",
                    files=files_to_schedule,
                    background_tasks=scheduler_background_tasks,
                )
                workflow_id = handle.workflow_id
                logger.info("Queued scheduler workflow %s from /upload-process-documents", handle.workflow_id)
                # OPS-04 reconciliation: bind each task to the workflow that backs it,
                # so a task stuck pending (e.g. worker down past the workflow timeout)
                # can be reconciled against Temporal's verdict instead of hanging.
                bind_task_svc = ApplicationContext.get_instance().get_task_service()
                if bind_task_svc is not None and workflow_id:
                    for _bf, _bd, _bt, bind_task_id in scheduled_candidates:
                        if not bind_task_id:
                            continue
                        try:
                            await bind_task_svc.bind_execution(bind_task_id, execution_id=workflow_id)
                        except Exception:
                            logger.warning("OPS-04: could not bind task %s to workflow %s", bind_task_id, workflow_id, exc_info=True)
                for filename, document_uid, _, task_id in scheduled_candidates:
                    yield (
                        json.dumps(
                            {
                                "step": current_step,
                                "status": Status.SUCCESS,
                                "filename": filename,
                                "document_uid": document_uid,
                                "workflow_id": workflow_id,
                            }
                        )
                        + "\n"
                    )
                # Emit queued processing status so the UI can track via SSE task events.
                for filename, document_uid, _, task_id in scheduled_candidates:
                    yield (
                        ProcessingProgress(
                            step=STEP_PROCESSING,
                            status=Status.IN_PROGRESS,
                            filename=filename,
                            document_uid=document_uid,
                            task_id=task_id,
                        ).model_dump_json()
                        + "\n"
                    )
                success += len(scheduled_candidates)
            except Exception as e:
                error_message = self._format_exception_message(e)
                last_error = error_message
                logger.exception("Scheduler submission failed for /upload-process-documents", exc_info=True)
                # The workflow was never created: durably fail each task so it cannot
                # stay "pending in the tray" with no execution behind it.
                fail_task_svc = ApplicationContext.get_instance().get_task_service()
                for filename, _, _, task_id in scheduled_candidates:
                    yield self._progress_event(step=current_step, status=Status.FAILED, error=error_message, filename=filename)
                    if fail_task_svc is not None and task_id:
                        try:
                            await fail_task_svc.fail_task(task_id, f"Scheduling failed: {error_message}")
                        except Exception:
                            logger.warning("OPS-04: could not fail task %s after submission failure", task_id, exc_info=True)

        timer_dims["status"] = "ok" if success == total else "error"
        overall_status = Status.SUCCESS if success == total else Status.FAILED
        done_payload: dict = {"step": "done", "status": overall_status}
        if last_error:
            done_payload["error"] = last_error
        yield json.dumps(done_payload) + "\n"

    def __init__(self, router: APIRouter):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.service = get_ingestion_service()
        self.workspace_storage_service = WorkspaceStorageService()
        self._fast_text_registry = self._build_fast_text_registry()
        self._fast_text_instances: Dict[str, BaseFastTextProcessor] = {}
        self.embedder = ApplicationContext.get_instance().get_embedder()
        self.vector_store: BaseVectorStore = ApplicationContext.get_instance().get_create_vector_store(self.embedder)
        scheduler_cfg = ApplicationContext.get_instance().get_config().scheduler
        processing_cfg = ApplicationContext.get_instance().get_config().processing
        max_parallelism = ApplicationContext.get_instance().get_config().scheduler.temporal.ingestion_workflow_parallelism
        self.scheduler_task_service: IngestionTaskService | None = None
        if scheduler_cfg.enabled:
            self.scheduler_task_service = IngestionTaskService(
                scheduler_config=scheduler_cfg,
                processing_config=processing_cfg,
                metadata_service=self.service.metadata_service,
                max_parallelism=max_parallelism,
            )
        logger.info("IngestionController initialized.")

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
            profile = parsed_input.profile or ApplicationContext.get_instance().get_config().processing.default_profile

            await self._check_quota_before_upload(files, tags, user)

            preloaded_files = self._preload_uploaded_files(files)

            total = len(preloaded_files)

            async def event_stream():
                success = 0
                for filename, input_temp_file in preloaded_files:
                    current_step = STEP_UPLOAD_PREPARATION
                    try:
                        yield self._progress_event(step=current_step, status=Status.IN_PROGRESS, filename=filename)
                        metadata = await self.service.extract_metadata(
                            user,
                            file_path=input_temp_file,
                            tags=tags,
                            source_tag=source_tag,
                            profile=profile,
                        )
                        output_temp_dir = input_temp_file.parent.parent
                        self.service.save_input(user, metadata=metadata, input_dir=output_temp_dir / "input")
                        await self.service.save_metadata(user, metadata=metadata)
                        yield self._progress_event(
                            step=current_step,
                            status=Status.SUCCESS,
                            filename=filename,
                            document_uid=metadata.document_uid,
                        )
                        yield self._progress_event(
                            step=STEP_FINISHED,
                            status=Status.FINISHED,
                            filename=filename,
                            document_uid=metadata.document_uid,
                        )

                        success += 1

                    except Exception as e:
                        error_message = self._format_exception_message(e)
                        yield self._progress_event(
                            step=current_step,
                            status=Status.FAILED,
                            filename=filename,
                            error=error_message,
                        )
                    finally:
                        cleanup_uploaded_temp_file(input_temp_file)

                overall_status = Status.SUCCESS if success == total else Status.FAILED
                yield json.dumps({"step": "done", "status": overall_status}) + "\n"

            return StreamingResponse(event_stream(), media_type="application/x-ndjson")

        @router.post(
            "/upload-process-documents",
            tags=["Processing"],
            summary="Upload and process documents immediately (end-to-end)",
            description="Ingest and process one or more documents synchronously in a single step.",
        )
        async def process_documents_sync(
            background_tasks: BackgroundTasks,
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
            user: KeycloakUser = Depends(get_current_user),
            kpi: KPIWriter = Depends(get_kpi_writer),
        ) -> StreamingResponse:
            kpi_actor = KPIActor(type="human", user_id=user.uid, groups=user.groups)
            with kpi.timer(
                "api.request_latency_ms",
                dims={"route": "/upload-process-documents", "method": "POST"},
                actor=kpi_actor,
            ) as d:
                parsed_input = IngestionInput(**json.loads(metadata_json))
                tags = parsed_input.tags
                source_tag = parsed_input.source_tag
                profile = parsed_input.profile or ApplicationContext.get_instance().get_config().processing.default_profile

                await self._check_quota_before_upload(files, tags, user)

                preloaded_files = self._preload_uploaded_files(files)
                event_stream = self._stream_upload_process(
                    preloaded_files=preloaded_files,
                    user=user,
                    tags=tags,
                    source_tag=source_tag,
                    profile=profile,
                    scheduler_task_service=self.scheduler_task_service,
                    background_tasks=background_tasks if self.scheduler_task_service is not None else None,
                    kpi=kpi,
                    kpi_actor=kpi_actor,
                    timer_dims=d,
                )

                return StreamingResponse(event_stream, media_type="application/x-ndjson")

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
            opts.fast = True

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
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "fast_text_empty_extraction",
                            "message": f"No text could be extracted from {filename}.",
                        },
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"[FAST TEXT] Extraction failed for {filename}: {e}", exc_info=True)
                raise HTTPException(status_code=400, detail=str(e))
            finally:
                cleanup_uploaded_temp_file(raw_path)

            if fmt.lower() == "text":
                return Response(content=result.text, media_type="text/plain; charset=utf-8")
            logger.info(f"[FAST TEXT] Returning JSON result for {filename} with text length {len(result.text or '')}")
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
                Uses scheduler backend from configuration (memory or temporal) for vector storage.
                Returns vector ingest metadata and a compact summary for UI previews.
            """
            ),
        )
        async def fast_ingest(
            file: UploadFile = File(...),
            options_json: Optional[str] = Form(None, description="JSON string of FastTextOptions"),
            session_id: Optional[str] = Form(None, description="Optional chat session id for scoping"),
            scope: str = Form("session", description="Logical scope label, default 'session'"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Why this exists:
            - Chat attachments need a lightweight ingestion path that stays responsive for the UI.
            - The route extracts compact text, splits oversized payloads, then stores session-scoped vectors.

            How to use:
            - Upload one file plus optional `options_json`, `session_id`, and `scope`.
            - The handler extracts text with the fast attachment processor, chunks it for embeddings, and returns summary metadata for the UI.
            """
            filename = file.filename or "uploaded"

            # Parse options
            opts = FastTextOptions()
            include_summary = True
            summary_max_chars: Optional[int] = 12_000
            if options_json:
                try:
                    payload = _json.loads(options_json)
                    if not isinstance(payload, dict):
                        raise ValueError("options_json must be an object")
                    include_summary = bool(payload.get("include_summary", True))
                    summary_max_chars_raw = payload.get("summary_max_chars", 12_000)
                    if summary_max_chars_raw is None:
                        summary_max_chars = None
                    else:
                        summary_max_chars = int(summary_max_chars_raw)
                        if summary_max_chars <= 0:
                            summary_max_chars = None
                    allowed = {f.name for f in dataclasses.fields(FastTextOptions)}
                    filtered = {k: v for k, v in payload.items() if k in allowed}
                    opts = FastTextOptions(**filtered)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid options_json: {e}")
            opts.fast = True

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
                if not text.strip() and not result.pages:
                    logger.warning(
                        "[FAST TEXT][INGEST] EMPTY FILE user=%s file=%s (page_count=%s truncated=%s)",
                        user.uid,
                        filename,
                        result.page_count,
                        result.truncated,
                    )
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "fast_text_empty_extraction",
                            "message": f"No text could be extracted from {filename}.",
                        },
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
            finally:
                cleanup_uploaded_temp_file(raw_path)

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
                scheduler_backend, chunks = await self._store_fast_vectors(document_uid=document_uid, docs=docs)
                logger.info(
                    "[FAST TEXT][INGEST] Stored vectors backend=%s doc_uid=%s chunks=%d user=%s session=%s scope=%s per_page=%s",
                    scheduler_backend,
                    document_uid,
                    chunks,
                    user.uid,
                    session_id,
                    scope,
                    bool(result.pages),
                )
            except HTTPException:
                raise
            except Exception:
                logger.exception("[FAST TEXT][INGEST] Failed to store vectors for %s", filename)
                raise HTTPException(status_code=500, detail="Failed to store vectors")

            summary_md = ""
            summary_truncated = False
            if include_summary:
                summary_md = (result.text or "").replace("\x00", "").strip()
                if not summary_md:
                    summary_md = "_(No summary returned by Knowledge Flow)_"
                elif summary_max_chars is not None and len(summary_md) > summary_max_chars:
                    summary_md = summary_md[:summary_max_chars].rstrip() + "\n…"
                    summary_truncated = True

            return {
                "document_uid": document_uid,
                "chunks": chunks,
                "total_chars": result.total_chars,
                "truncated": result.truncated,
                "scope": scope,
                "summary_md": summary_md,
                "summary_chars": len(summary_md),
                "summary_truncated": summary_truncated,
            }

        @router.delete(
            "/fast/delete/{document_uid}",
            tags=["Processing"],
            summary="Delete artifacts for a fast-ingested document",
            description="Remove fast-ingest vectors and any associated user-storage upload for one attachment.",
        )
        async def delete_fast_artifacts(
            document_uid: str,
            session_id: Optional[str] = Query(None, description="Optional session_id for scoped cleanup"),
            storage_key: Optional[str] = Query(
                None,
                description="Optional user-storage key to delete alongside the fast-ingest artifacts.",
            ),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                logger.info(
                    "[FAST TEXT][INGEST][DELETE] user=%s doc_uid=%s session=%s storage_key=%s backend=%s",
                    user.uid,
                    document_uid,
                    session_id,
                    storage_key,
                    self._scheduler_backend(),
                )
                await self._delete_fast_ingest_artifacts(
                    user=user,
                    document_uid=document_uid,
                    storage_key=storage_key,
                )
                logger.info(
                    "[FAST TEXT][INGEST] Deleted artifacts for doc_uid=%s user=%s session=%s storage_key=%s",
                    document_uid,
                    user.uid,
                    session_id,
                    storage_key,
                )
            except Exception:
                logger.exception(
                    "[FAST TEXT][INGEST] Failed to delete artifacts for doc_uid=%s",
                    document_uid,
                )
                raise HTTPException(status_code=500, detail="Failed to delete fast-ingest artifacts")
            return {
                "status": "ok",
                "document_uid": document_uid,
                "session_id": session_id,
                "storage_key": storage_key,
            }
