# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Persistence adapter used by the existing push activities and ingestion pipeline."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast, get_args
from uuid import NAMESPACE_URL, UUID, uuid5

from fred_core.documents.document_structures import DocumentMetadata, FileInfo, Identity, ProcessingStage, ProcessingStatus, SourceInfo, SourceType
from fred_core.tasks.models import IngestionProcessingProfile
from temporalio import activity, exceptions

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.processing_profile_context import processing_profile_scope
from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService
from knowledge_flow_backend.features.manager_processing.artifacts import Artifacts
from knowledge_flow_backend.features.manager_processing.client import ManagerClient, ManagerError, raise_permanent_failure
from knowledge_flow_backend.features.manager_processing.contracts import Claim, Commit, Descriptor, Failure, FailureCode, Stage, Work
from knowledge_flow_backend.features.manager_processing.persistence import scoped_pipeline


class ManagedIngestionService(IngestionService):
    def __init__(self, descriptor: Descriptor, source: str):
        # Deliberately avoid IngestionService's legacy MetadataService/content singleton.
        self.context = ApplicationContext.get_instance()
        self.descriptor = descriptor
        self.source = source
        settings = self.context.configuration.manager_processing
        if settings is None or not settings.enabled:
            raise ManagerError("worker_failed", permanent=True)
        self.settings = settings
        self.artifacts = Artifacts(self.settings)
        self.output_dir = None
        self.vectors = None
        self.output_finished = False
        self.failure_code: FailureCode = "indexing_failed" if descriptor.stage == "indexing" else "extraction_failed"

    @property
    def extraction_context(self) -> str:
        return self.descriptor.model_dump_json()

    @property
    def already_committed(self) -> bool:
        return self.descriptor.committed is not None

    async def get_metadata(self, user, document_uid):
        d = self.descriptor
        if user.uid != d.actor or document_uid != str(d.work.document_id):
            raise exceptions.ApplicationError("manager identity mismatch", non_retryable=True)
        metadata = DocumentMetadata(
            identity=Identity(document_uid=document_uid, document_name=d.name, title=None, uploaded_by=d.actor),
            source=SourceInfo(source_type=SourceType.PUSH, source_tag=self.source, pull_location=None),
            file=FileInfo(file_size_bytes=d.size, mime_type=d.mime, sha256=d.work.original_sha256),
        )
        metadata.processing.profile = IngestionProcessingProfile(d.work.profile)
        metadata.mark_stage_done(ProcessingStage.RAW_AVAILABLE)
        if not self.already_committed:
            try:
                await asyncio.to_thread(self._prepare)
            except Exception as exc:
                self.record_failure(exc)
                await asyncio.to_thread(self._abandon)
                raise_permanent_failure(exc)
                raise
        return metadata

    def _prepare(self):
        with TemporaryDirectory(prefix="manager-policy-") as temporary:
            directory = Path(temporary)
            (directory / "policy.json").write_text(json.dumps(self.descriptor.profile_settings))
            self._commit(directory)

    def _commit(self, output: Path, metadata: DocumentMetadata | None = None):
        d = self.descriptor
        count = self.vectors.count if self.vectors else 0
        rows = metadata.file.row_count if metadata else None
        if metadata is not None:
            (output / "metadata.json").write_text(metadata.model_dump_json())
        manifest = self.artifacts.publish(d, output, chunks=count, vectors=count, rows=rows)
        manifest.vector_ordinals = self.vectors.ordinals if self.vectors else []
        with ManagerClient(self.settings) as client:
            client.post(f"/document-processing/{d.work.processing_id}/commit", Commit(work=d.work, stage=d.stage, manifest=manifest))

    def get_local_copy(self, user, metadata, target_dir: Path) -> Path:
        d = self.descriptor
        if metadata.document_uid != str(d.work.document_id) or user.uid != d.actor:
            raise ManagerError("access_changed", permanent=True)
        if d.size + d.max_output_bytes > self.settings.temporary_bytes:
            raise ManagerError("capacity_exceeded", permanent=True)
        source = target_dir / "input" / d.name
        with ManagerClient(self.settings) as client:
            client.original(d, source)
        self.artifacts.restore(d, target_dir / "output")
        return target_dir

    def save_output(self, user, metadata, output_dir):
        self._commit(output_dir, metadata)
        metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)

    async def persist_progress(self, user, metadata):
        if any(status == ProcessingStatus.FAILED for status in metadata.processing.stages.values()):
            await asyncio.to_thread(self._abandon)
        elif self.output_finished and self.output_dir is not None:
            await asyncio.to_thread(self._commit, self.output_dir, metadata)
        return True

    def record_failure(self, error: BaseException | None):
        # Only exact stable codes cross the callback boundary; provider diagnostics stay private.
        codes = get_args(FailureCode)
        seen = set()
        while error is not None and id(error) not in seen:
            seen.add(id(error))
            if str(error) in codes:
                self.failure_code = cast(FailureCode, str(error))
                return
            error = error.__cause__ or error.__context__

    def _abandon(self):
        d = self.descriptor
        code = self.failure_code
        with ManagerClient(self.settings) as client:
            client.post(f"/document-processing/{d.work.processing_id}/abandon", Failure(work=d.work, stage=d.stage, generation=d.generation, code=code))

    def process_output(self, user, input_file_name, output_dir, input_file_metadata, profile=None):
        with processing_profile_scope(profile):
            self.pipeline_manager, self.vectors = scoped_pipeline(self.context, self.descriptor, output_dir, self.artifacts, include_output=True)
            result = super().process_output(user, input_file_name, output_dir, input_file_metadata, profile)
            if self.context.is_tabular_file(input_file_metadata.document_name):
                import duckdb

                from knowledge_flow_backend.features.content.content_service import ContentService

                artifact = (result.extensions or {})["tabular_v1"]
                parquet = output_dir / artifact["object_key"]
                with duckdb.connect(":memory:") as connection:
                    frame = connection.read_parquet(str(parquet)).limit(200).df()
                (output_dir / "output.md").write_text(ContentService._dataframe_to_markdown_preview(frame))
        self.output_dir = output_dir
        self.output_finished = True
        return result


async def manager_service(source: str | None, stage: Stage, *, file=None):
    if source is None or not source.startswith("manager:"):
        return None
    try:
        _, installation, operation = source.split(":")
        installation = UUID(installation)
        operation = UUID(operation)
        context = ApplicationContext.get_instance()
        settings = context.configuration.manager_processing
        if settings is None or not settings.enabled:
            raise ValueError("manager processing disabled")
        info = activity.info()
        activity_id = uuid5(NAMESPACE_URL, f"{info.workflow_id}/{info.workflow_run_id}/{info.activity_id}")
        execution = uuid5(NAMESPACE_URL, f"{info.workflow_id}/{info.workflow_run_id}/{info.activity_id}/{info.attempt}")

        def claim():
            with ManagerClient(settings) as client:
                work = Work.model_validate(client.get(f"/document-processing/{operation}/work"))
                if work.installation_id != installation:
                    raise ManagerError("integrity_failure", permanent=True)
                descriptor = Descriptor.model_validate(
                    client.post(f"/document-processing/{operation}/claim", Claim(work=work, stage=stage, execution_id=execution, activity_id=activity_id, attempt=info.attempt))
                )
                from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

                if file is not None and file != FileToProcess.model_validate(descriptor.file):
                    raise ManagerError("integrity_failure", permanent=True)
                return descriptor

        descriptor = await asyncio.to_thread(claim)
        return ManagedIngestionService(descriptor, source)
    except ManagerError as error:
        raise exceptions.ApplicationError(error.code, non_retryable=error.permanent) from None
    except (ValueError, KeyError):
        raise exceptions.ApplicationError("invalid manager document source", non_retryable=True) from None
