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

import asyncio
import dataclasses
import json
import json as _json
import logging
import pathlib
import shutil
import tempfile
import time
import uuid
from typing import Dict, List, Literal, Optional, Type

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from fred_core import (
    ORGANIZATION_ID,
    AuthorizationError,
    DocumentPermission,
    KeycloakUser,
    OrganizationPermission,
    RebacEngine,
    Resource,
    TagPermission,
    TeamMetadataStore,
    TeamPermission,
    get_current_user,
)
from fred_core.common.team_id import TeamId
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.kpi import KPIActor, KPIWriter
from fred_core.scheduler import SchedulerBackend
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext, get_kpi_writer, get_rebac_engine
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
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_doc_processor import (
    FastLiteDocProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_docx_processor import (
    FastLiteDocxProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor import (
    FastLiteImageProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_odt_processor import (
    FastLiteOdtProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pdf_processor import FastLitePdfProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_ppt_processor import (
    FastLitePptProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pptx_processor import (
    FastLitePptxProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_plain_text_processor import (
    FastPlainTextProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_spreadsheet_processor import (
    FastSpreadsheetProcessor,
)
from knowledge_flow_backend.core.processors.output.tabular_processor.tabular_processor import TabularProcessor
from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    BaseVectorStore,
)
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.scheduler.activities import output_process
from knowledge_flow_backend.features.scheduler.push_files_activities import push_input_process
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    FileToProcess,
    FileToProcessWithoutUser,
)
from knowledge_flow_backend.features.tabular.artifacts import FAST_INGEST_SOURCE_TAG, document_artifact_prefix, read_tabular_artifact

logger = logging.getLogger(__name__)


async def _authorize_fast_ingest_delete(rebac: RebacEngine, user: KeycloakUser, document_uid: str, vector_store: BaseVectorStore) -> bool:
    """Authorize a fast-ingest artifact delete. Returns whether the caller was
    authorized via the platform-admin bypass rather than by owning the
    document — the caller must thread this into every subsequent per-document
    ownership check for this request (`_delete_attachment_tabular_dataset`),
    not just this endpoint's own gate, or a platform-driven delete on
    someone else's document silently no-ops downstream instead of acting.

    A platform service principal holding org-level ``can_manage_platform`` — e.g.
    the control-plane lifecycle worker erasing a session's fast-ingest attachments
    at window expiry — bypasses the per-document ownership check. Authentication is
    still enforced by the endpoint dependency (``get_current_user``); only the
    ownership check is waived for that principal. Reuses the AUTHZ-01
    ``can_manage_platform`` permission — no second bypass is forked.

    Everyone else must own the document. Fast-ingested (session-scoped) documents
    carry no ``parent`` tag and no ReBAC tuple at all — they were deliberately left
    "resource-less" and authentication-gated, so a ``DocumentPermission.DELETE``
    ReBAC check can never resolve to True for them, denying even the uploader.
    Ownership is instead proven the same way ``summarize_document`` already
    proves it for reads on this same document class: via the chunk's own
    ``scope``/``user_id`` metadata (``base_vector_store.may_delete_session_document``),
    which also allows a document with no chunks left at all — so a retry after
    an earlier attempt already deleted the vectors but failed on a later
    cleanup step can still converge instead of being denied forever.

    A CSV attachment (ATTACH-TAB-01) never has vector chunks at all — the
    text-chunk preview is skipped for it entirely, by design — so the
    chunk-based check above would treat "zero chunks" as a safe retry for
    *every* CSV attachment uid, not just this caller's own, silently
    returning success to a non-owner instead of denying them. Checked first,
    ahead of the chunk-based fallback: a document with a `tabular_v1`
    artifact is authorized purely by `uploaded_by` match, the same test
    `TabularService._resolve_owned_attachment_dataset` uses, never falling
    through to the chunk-count check at all for this document class.

    A TAGGED document is refused outright, before either bypass runs at all
    (P1, codex review) — this is deliberately broader than "skip the
    tabular-ownership branch": the chunk-based fallback's "zero chunks =
    safe retry" semantics were written for the genuinely resource-less
    fast-ingest document class and don't check `source_tag` at all, so
    without this guard *any* tagged document with zero vector chunks — the
    default for every CSV/tabular corpus document platform-wide,
    `pointer_chunks_enabled` being off everywhere shipped — would pass this
    endpoint's authorization for *any* authenticated user, tagged or not,
    owner or not. Combined with an operator-configured `document_sources`
    entry literally named "fast_ingest" (nothing reserves that string), the
    narrower tabular-ownership branch above would otherwise let that
    document's original uploader delete it even after losing their real
    ReBAC `DocumentPermission.DELETE` (e.g. removed from the owning team) —
    a tagged document already has its own ReBAC-based protection this
    endpoint doesn't check, and must never be treated as resource-less
    however its `source_tag` happens to read.
    """
    if await rebac.has_user_permission(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID):
        return True
    metadata = await ApplicationContext.get_instance().get_metadata_store().get_metadata_by_uid(document_uid)
    if metadata is not None and metadata.tags.tag_ids:
        raise AuthorizationError(user.uid, DocumentPermission.DELETE.value, Resource.DOCUMENTS)
    if metadata is not None and metadata.source_tag == FAST_INGEST_SOURCE_TAG and read_tabular_artifact(metadata) is not None:
        if metadata.identity.uploaded_by == user.uid:
            return False
        raise AuthorizationError(user.uid, DocumentPermission.DELETE.value, Resource.DOCUMENTS)
    if await asyncio.to_thread(vector_store.may_delete_session_document, document_uid, user.uid):
        return False
    raise AuthorizationError(user.uid, DocumentPermission.DELETE.value, Resource.DOCUMENTS)


STEP_UPLOAD_PREPARATION = "upload preparation"
STEP_QUEUED_FOR_PROCESSING = "queued for processing"
STEP_PROCESSING = "processing"
STEP_FINISHED = "Finished"


class IngestionInput(BaseModel):
    tags: List[str] = []
    source_tag: str = "fred"
    profile: IngestionProcessingProfile | None = None


class QuotaPrecheckRequest(BaseModel):
    """A declared upload batch to check against storage quota BEFORE any byte
    is uploaded (#2360). Sizes come from the client (`File.size`) and can lie —
    the post-receive check in the upload endpoints stays the enforcement point;
    this is a UX/bandwidth optimization that lets the caller reject a whole
    batch up front instead of file by file after transfer.

    `team_id` covers destinations whose tags don't exist yet at precheck time
    (a folder dropped at a team corpus root); "personal" means no team.
    """

    tags: List[str] = []
    team_id: Optional[str] = None
    total_size: int = Field(..., ge=0)


class QuotaPrecheckResponse(BaseModel):
    """Verdict for a quota precheck; scope/owner/current/limit are only set on
    denial (the numbers of the first owner whose quota the batch would blow)."""

    allowed: bool
    scope: Optional[Literal["team", "personal"]] = None
    owner_id: Optional[str] = None
    current: Optional[int] = None
    limit: Optional[int] = None


class FastIngestResponse(BaseModel):
    """Result of one fast-ingested chat attachment (`POST /fast/ingest`).

    `tabular_available` is `True` only for a `.csv` attachment (ATTACH-TAB-01)
    — non-CSV attachments never attempt a tabular build. It's never `False`
    on a 200: a failed tabular build rejects the whole upload (422) rather
    than returning a degraded success, since a CSV attachment has no vector
    chunks to fall back to (DESIGN.md, "Session-Scoped Attachment Datasets").
    """

    document_uid: str
    chunks: int
    total_chars: int
    truncated: bool
    scope: str
    summary_md: str
    summary_chars: int
    summary_truncated: bool
    tabular_available: bool


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


def upload_basename(raw_filename: str | None) -> str:
    """Leaf name of a client-supplied upload filename.

    Browsers upload a file picked out of a folder (a `webkitdirectory` input or
    a dropped directory) under its RELATIVE path as the multipart filename, and
    a hostile client can send `../` segments outright — the raw value must never
    reach a filesystem path.
    """
    leaf = (raw_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return leaf if leaf not in ("", ".", "..") else "uploaded_file"


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
    tmp_path = tmp_dir / upload_basename(file.filename)
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
            registry[".doc"] = FastLiteDocProcessor
            registry[".odt"] = FastLiteOdtProcessor
            registry[".pptx"] = FastLitePptxProcessor
            registry[".ppt"] = FastLitePptProcessor
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
            filename = upload_basename(file.filename)
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

    async def _build_attachment_tabular_dataset(
        self,
        *,
        user: KeycloakUser,
        document_uid: str,
        filename: str,
        raw_path: pathlib.Path,
    ) -> None:
        """
        Build a SQL-queryable `tabular_v1` dataset for one CSV chat attachment.

        Why this exists:
        - Chat-attached CSVs get the same DuckDB/Parquet dataset corpus CSV
          ingestion produces, so the tabular tools can answer precise
          questions (counts, filters, aggregates) the fast-text markdown
          preview cannot (DESIGN.md, "Session-Scoped Attachment Datasets").

        How to use:
        - Call with the raw upload path, before it is cleaned up.
        - Raises on failure — deliberately not best-effort. CSV attachments
          skip vector-chunking entirely (DESIGN.md, "Session-Scoped
          Attachment Datasets"), so there is no fallback retrieval path left
          if this fails; the caller must reject the upload rather than
          accept an attachment the agent can neither search nor query,
          exactly like the "no text could be extracted" empty-file check
          above.
        - Reuses `document_uid` from the fast-ingest vector chunks so the one
          bracketed id the agent is given works for both search and SQL.
        - Persists metadata with no tags, so no ReBAC tuple is created —
          `TabularService._resolve_owned_attachment_dataset` authorizes this
          document class by ownership metadata instead.
        - Builds `DocumentMetadata` directly rather than going through
          `IngestionService.extract_metadata()`/`process_metadata()`: those
          assume a corpus document. `extract_metadata()`'s versioning step
          scans the whole metadata catalog for a same-named document and
          raises if one exists — folder semantics that make no sense for an
          untagged, session-scoped attachment. `process_metadata()` also
          requires `source_tag` to resolve against the operator-configured
          `document_sources` registry (`resolve_source_type`), which a chat
          attachment was never meant to be a member of.
        """
        metadata = DocumentMetadata(
            identity=Identity(document_name=filename, document_uid=document_uid, title=filename, uploaded_by=user.uid),
            source=SourceInfo(source_type=SourceType.PUSH, source_tag=FAST_INGEST_SOURCE_TAG),  # type: ignore[reportCallIssue]  # basedpyright doesn't recognize Field(None, ...) positional defaults as satisfying SourceInfo's synthesized __init__; pull_location genuinely defaults to None (document_structures.py) -- same false positive as scripts/seed_synthetic_corpus.py:119
            file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
            tags=Tagging(tag_ids=[]),
        )
        await asyncio.to_thread(self._tabular_processor.process, str(raw_path), metadata, emit_pointer_chunk=False)
        await self.service.metadata_service.save_document_metadata(user, metadata)

    async def _delete_fast_ingest_artifacts(
        self,
        *,
        user: KeycloakUser,
        document_uid: str,
        storage_key: str | None,
        is_platform_bypass: bool,
    ) -> str:
        """
        Delete one fast-ingested document's retrieval artifacts.

        Why this exists:
        - chat attachments need a single cleanup path for the retrieval artifacts

        How to use:
        - call from the DELETE `/fast/delete/{document_uid}` route
        - `is_platform_bypass` must be the value `_authorize_fast_ingest_delete`
          already returned for this same request — e.g. scheduled conversation
          erasure (CTRLP-12) authenticates as a minted platform service
          bearer, never as the document's own uploader, so the tabular
          cleanup below must honor the same bypass its caller was already
          granted instead of re-deriving ownership and silently no-oping.

        Note: `storage_key` is accepted for backward-compatible call sites but ignored —
        chat attachments no longer store a raw copy in workspace storage (FILES-04).
        """

        del storage_key
        backend = await self._delete_fast_vectors(document_uid=document_uid)
        await self._delete_attachment_tabular_dataset(user=user, document_uid=document_uid, is_platform_bypass=is_platform_bypass)
        return backend

    async def _delete_attachment_tabular_dataset(self, *, user: KeycloakUser, document_uid: str, is_platform_bypass: bool) -> None:
        """
        Best-effort cleanup of one attachment's tabular dataset, if it has one.

        Why this exists:
        - `_build_attachment_tabular_dataset` persists a metadata record and a
          Parquet artifact alongside the vectors `_delete_fast_vectors`
          already cleans up; deleting an attachment must not leave those
          two behind.
        - Re-verifies ownership itself rather than trusting the caller's
          authorization: `_authorize_fast_ingest_delete`'s "no vector chunks
          = safe retry" rule (`may_delete_session_document`) was designed for
          an idempotent vector-only delete and passes for ANY document with
          zero vector chunks — including any corpus CSV dataset whenever
          `pointer_chunks_enabled` is off (the shipped default). Without this
          method's own check, any authenticated user could delete any other
          user's or team's tabular dataset by calling
          `DELETE /fast/delete/{their_document_uid}`. Same ownership test as
          `TabularService._resolve_owned_attachment_dataset`.
        - `is_platform_bypass` is NOT re-derived here — it must be threaded in
          from `_authorize_fast_ingest_delete`'s own decision for this same
          request. A first version of this check required `uploaded_by ==
          user.uid` unconditionally, with no accommodation for the endpoint's
          own platform-admin bypass: scheduled conversation erasure (CTRLP-12)
          authenticates as a minted service bearer, so `user.uid` never
          equals the original uploader, and the endpoint returned HTTP 200
          while silently skipping the actual Parquet/metadata cleanup —
          erasure was reported complete with the artifact orphaned and
          nothing left to make it retryable. `source_tag == "fast_ingest"`
          and no tags both stay hard requirements regardless of bypass: this
          method must never touch a corpus tabular dataset even for a
          platform caller, since that document class has its own deletion
          path with its own quota/tag/ReBAC cleanup this narrow method
          deliberately skips — `_authorize_fast_ingest_delete`'s own
          platform-admin check runs before it ever resolves metadata, so a
          tagged document reaching this function with `is_platform_bypass`
          set has had no tags check applied yet; this one is what actually
          stops it (P1, codex review — the same gap this method's ownership
          check already closed for the non-bypass case above, but for tags).
        - Deletes the Parquet objects and metadata row directly rather than
          `MetadataService.delete_document_and_artifacts_trusted`: that
          method also releases storage-quota accounting
          (`_delete_and_release`), which requires a Postgres engine even to
          determine there is nothing to release for a tagless, quota-exempt
          attachment — infrastructure this narrow cleanup has no other
          reason to depend on.
        """
        try:
            context = ApplicationContext.get_instance()
            metadata_store = context.get_metadata_store()
            metadata = await metadata_store.get_metadata_by_uid(document_uid)
            if metadata is None or read_tabular_artifact(metadata) is None:
                return
            if metadata.source_tag != FAST_INGEST_SOURCE_TAG:
                return
            if metadata.tags.tag_ids:
                return
            if not is_platform_bypass and metadata.identity.uploaded_by != user.uid:
                return
            content_store = context.get_content_store()
            artifacts_prefix = context.get_config().storage.tabular_store.artifacts_prefix
            prefix = document_artifact_prefix(artifacts_prefix=artifacts_prefix, document_uid=document_uid)
            for stored_object in content_store.list_objects(prefix):
                content_store.delete_object(stored_object.key)
            await metadata_store.delete_metadata(document_uid)
        except Exception:
            logger.warning(
                "[FAST TEXT][INGEST][DELETE] Failed to clean up tabular dataset for doc_uid=%s",
                document_uid,
                exc_info=True,
            )

    async def _resolve_tag_owners(self, tags: List[str], user: KeycloakUser) -> tuple[set[str], set[str]]:
        """Resolve the owning team(s) and personal-space user(s) for a list of tag ids.

        Team ownership prefers ReBAC (`lookup_subjects`), falling back to a team
        metadata lookup by `tag.owner_id` when ReBAC is disabled or errors. A tag
        that resolves to neither is treated as personal, owned by `user` if the
        tag itself carries no resolvable owner. Shared by quota enforcement
        (`_check_quota_before_upload`) and task `team_id` tagging
        (`_stream_upload_process`) so both agree on tag ownership from one path.
        """
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

        return team_ids, user_ids

    async def _evaluate_quota(
        self,
        total_upload_size: int,
        tags: List[str],
        user: KeycloakUser,
        extra_team_ids: Optional[set[str]] = None,
    ) -> QuotaPrecheckResponse:
        """Would `total_upload_size` bytes exceed the owning team's or user's quota?

        Single implementation behind both the pre-receive precheck endpoint
        (declared sizes) and the post-receive upload enforcement
        (`_check_quota_before_upload`), so the two can never drift (#2360).

        A tagless batch is checked against the caller's personal quota, not
        exempt: `tags` defaults to `[]`, so returning early here let any caller
        bypass quota entirely by omitting tags (#2150). `extra_team_ids` covers
        owners whose tags don't exist yet (a folder dropped at a team corpus
        root prechecks before its library tags are created).

        Fail CLOSED on unreadable counters: treating a store error as 0 turned
        any transient blip into a full quota bypass (#2150 review) — those
        paths still raise (400 malformed owner / 503 unverifiable) rather than
        answering allowed.
        """
        if total_upload_size <= 0:
            return QuotaPrecheckResponse(allowed=True)

        team_ids, user_ids = await self._resolve_tag_owners(tags, user)
        if extra_team_ids:
            team_ids |= extra_team_ids
        if not team_ids and not user_ids:
            user_ids = {user.uid}

        cfg = ApplicationContext.get_instance().get_config()

        if team_ids:
            default_limit = cfg.app.default_team_max_resources_storage_size
            engine = ApplicationContext.get_instance().get_pg_async_engine()
            store = TeamMetadataStore(engine)
            for team_id in team_ids:
                allowed, current, max_size = await store.check_quota(TeamId(team_id), total_upload_size, default_limit=default_limit)
                if not allowed:
                    return QuotaPrecheckResponse(allowed=False, scope="team", owner_id=team_id, current=current, limit=max_size)

        personal_limit = cfg.app.personal_max_resources_storage_size
        if user_ids and personal_limit is not None and personal_limit > 0:
            from uuid import UUID

            from fred_core import get_user_store

            user_store = get_user_store()
            for user_id_str in user_ids:
                try:
                    user_uuid = UUID(user_id_str)
                except ValueError:
                    logger.warning("Cannot check personal quota for malformed user id '%s'; rejecting upload", user_id_str)
                    raise HTTPException(status_code=400, detail="Cannot resolve the storage owner for this upload.")
                try:
                    user_row = await user_store.find_user_by_id(user_uuid)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not read personal storage usage for '%s'; rejecting upload: %s", user_id_str, exc)
                    raise HTTPException(status_code=503, detail="Storage quota cannot be verified right now; please retry.")
                current = user_row.current_resources_storage_size or 0 if user_row else 0

                if current + total_upload_size > personal_limit:
                    return QuotaPrecheckResponse(allowed=False, scope="personal", owner_id=user_id_str, current=current, limit=personal_limit)

        return QuotaPrecheckResponse(allowed=True)

    async def _check_quota_before_upload(self, files: List[UploadFile], tags: List[str], user: KeycloakUser) -> None:
        """Reject (400) an upload that would exceed the owning team's or user's
        quota. Post-receive enforcement point — the sizes are read from the
        actually-received files, unlike the client-declared precheck. Kept even
        with the precheck in place: declared sizes can lie.
        """
        total_upload_size = 0
        for f in files:
            file_size = getattr(f, "size", None)
            if file_size is not None:
                total_upload_size += file_size
            else:
                f.file.seek(0, 2)
                total_upload_size += f.file.tell()
                f.file.seek(0)

        verdict = await self._evaluate_quota(total_upload_size, tags, user)
        if not verdict.allowed:
            owner_str = f"team '{verdict.owner_id}'" if verdict.scope == "team" else "personal space"
            limit_str = f"{verdict.limit} bytes" if verdict.limit else "unlimited"
            raise HTTPException(
                status_code=400,
                detail=f"Storage quota exceeded for {owner_str}: limit is {limit_str}, current usage is {verdict.current} bytes, attempting to upload {total_upload_size} bytes.",
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
    ):
        success = 0
        last_error: str | None = None
        total = len(preloaded_files)
        scheduled_candidates: list[tuple[str, str, str | None, str | None]] = []

        # Resolve once (tags are constant for the whole call) so every created
        # task_run row carries the destination team_id — without it, the task is
        # created with team_id=NULL and never matches a team-scoped Activity
        # query (`WHERE team_id = :team_id` never matches NULL), even though it
        # correctly shows up for a platform admin (no team_id filter at all).
        # Ambiguous (tags spanning more than one team) or personal-space uploads
        # deliberately leave it None rather than guess.
        owning_team_id: str | None = None
        if scheduler_task_service is not None:
            team_ids, _ = await self._resolve_tag_owners(tags, user)
            if len(team_ids) == 1:
                owning_team_id = next(iter(team_ids))

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
                            resp = await task_svc.start(req, created_by=user.uid, team_id=owning_team_id, target=target)
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
                    # Canonical progress event carrying task_id, like the preparation
                    # and processing steps — so the UI can correlate every step of the
                    # sequence to its task. workflow_id is bound server-side (above) and
                    # is not consumed by the client, so it is no longer put on the wire.
                    yield (
                        ProcessingProgress(
                            step=current_step,
                            status=Status.SUCCESS,
                            filename=filename,
                            document_uid=document_uid,
                            task_id=task_id,
                        ).model_dump_json()
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

        overall_status = Status.SUCCESS if success == total else Status.FAILED
        done_payload: dict = {"step": "done", "status": overall_status}
        if last_error:
            done_payload["error"] = last_error
        yield json.dumps(done_payload) + "\n"

    def __init__(self, router: APIRouter):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.service = get_ingestion_service()
        self._fast_text_registry = self._build_fast_text_registry()
        self._fast_text_instances: Dict[str, BaseFastTextProcessor] = {}
        self.embedder = ApplicationContext.get_instance().get_embedder()
        self.vector_store: BaseVectorStore = ApplicationContext.get_instance().get_create_vector_store(self.embedder)
        self._tabular_processor = TabularProcessor()
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

            for tag_id in tags:
                await get_rebac_engine().check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)
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
            kpi_actor = KPIActor(type="human", user_id=user.uid)
            parsed_input = IngestionInput(**json.loads(metadata_json))
            tags = parsed_input.tags
            source_tag = parsed_input.source_tag
            profile = parsed_input.profile or ApplicationContext.get_instance().get_config().processing.default_profile

            for tag_id in tags:
                await get_rebac_engine().check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)
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
            )

            return StreamingResponse(event_stream, media_type="application/x-ndjson")

        @router.post(
            "/quota/precheck",
            tags=["Processing"],
            summary="Check a declared upload batch against storage quota before any byte is sent",
            description=(
                "Answers whether `total_size` bytes would exceed the storage quota of the "
                "destination (tags' owning team, explicit `team_id`, or the caller's personal "
                "space) so a whole batch can be rejected before any upload starts. Advisory "
                "only: the upload endpoints re-check against the actually-received sizes."
            ),
        )
        async def quota_precheck(
            precheck: QuotaPrecheckRequest,
            user: KeycloakUser = Depends(get_current_user),
        ) -> QuotaPrecheckResponse:
            # Mirror the upload endpoints' authorization so the precheck leaks
            # no team's usage numbers to callers who couldn't upload there.
            for tag_id in precheck.tags:
                await get_rebac_engine().check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)
            team_id = None if precheck.team_id in (None, "personal") else precheck.team_id
            if team_id:
                await get_rebac_engine().check_user_team_permission_or_raise(
                    user=user,
                    permission=TeamPermission.CAN_UPDATE_RESOURCES,
                    team_id=team_id,
                )
            return await self._evaluate_quota(
                precheck.total_size,
                precheck.tags,
                user,
                extra_team_ids={team_id} if team_id else None,
            )

        @router.post(
            "/fast/text",
            tags=["Processing"],
            summary="Fast text extraction for a single file",
            description=(
                """
                Extract a compact text representation of a file without full ingestion.
                Supported: PDF, DOCX, DOC, ODT, CSV, PPTX, PPT, MD. Intended for agent use where fast, dependency-light text is needed.
            """
            ),
        )
        async def fast_markdown(
            file: UploadFile = File(...),
            options_json: Optional[str] = Form(None, description="JSON string of FastTextOptions"),
            fmt: str = Query("json", alias="format", description="Response format: 'json' or 'text'"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            # AUTHZ-05 §27/8a: stateless extraction, nothing persisted or
            # team-owned — the org-level CAN_PROCESS_CONTENT gate it used is
            # removed (item 8a); authentication alone is sufficient.
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
        ) -> FastIngestResponse:
            """
            Why this exists:
            - Chat attachments need a lightweight ingestion path that stays responsive for the UI.
            - The route extracts compact text, splits oversized payloads, then stores session-scoped vectors.

            How to use:
            - Upload one file plus optional `options_json`, `session_id`, and `scope`.
            - The handler extracts text with the fast attachment processor, chunks it for embeddings, and returns summary metadata for the UI.
            """
            # AUTHZ-05 §27/8a: session-scoped chat-attachment vectors, not
            # team-owned — the org-level CAN_PROCESS_CONTENT gate it used is
            # removed (item 8a); authentication alone is sufficient.
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
            document_uid = uuid.uuid4().hex
            tabular_available = False

            # The tabular build (best-effort, after vectors below) still needs
            # the raw file, so cleanup now wraps the whole handler instead of
            # just fast-text extraction.
            try:
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

                is_csv = filename.lower().endswith(".csv")
                docs: list[Document] = []
                chunks = 0

                # CSV gets a real tabular_v1 dataset below (exact SQL, full
                # data) instead of a text-chunked vector preview: a truncated
                # markdown-table chunk is exactly the kind of imprecise
                # answer source ATTACH-TAB-01 exists to move away from for
                # this file type, and it would compete with the deterministic
                # SQL path instead of complementing it (DESIGN.md,
                # "Session-Scoped Attachment Datasets"). `summary_md` below
                # still uses the extracted text for the UI preview card.
                if not is_csv:
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
                                # Whole pages are dropped past the char cap; the vectors
                                # are the only copy, so readers must be able to say so.
                                "truncated": result.truncated,
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
                            "truncated": result.truncated,
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
                else:
                    logger.info(
                        "[FAST TEXT][INGEST] Skipped vector chunking for CSV doc_uid=%s user=%s file=%s (tabular dataset covers search and SQL)",
                        document_uid,
                        user.uid,
                        filename,
                    )
                    # No fallback retrieval path is left for a CSV once vector
                    # chunking is skipped, so a build failure must reject the
                    # upload — same as the empty-file check above — rather
                    # than accept an attachment the agent can neither search
                    # nor query.
                    try:
                        await self._build_attachment_tabular_dataset(
                            user=user,
                            document_uid=document_uid,
                            filename=filename,
                            raw_path=raw_path,
                        )
                        tabular_available = True
                    except HTTPException:
                        raise
                    except Exception:
                        logger.exception("[FAST TEXT][INGEST] Failed to build tabular dataset for %s", filename)
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "code": "tabular_dataset_build_failed",
                                "message": f"Could not build a queryable dataset from {filename}.",
                            },
                        )
            finally:
                cleanup_uploaded_temp_file(raw_path)

            summary_md = ""
            summary_truncated = False
            if include_summary:
                summary_md = (result.text or "").replace("\x00", "").strip()
                if not summary_md:
                    summary_md = "_(No summary returned by Knowledge Flow)_"
                elif summary_max_chars is not None and len(summary_md) > summary_max_chars:
                    summary_md = summary_md[:summary_max_chars].rstrip() + "\n…"
                    summary_truncated = True

            return FastIngestResponse(
                document_uid=document_uid,
                chunks=chunks,
                total_chars=result.total_chars,
                truncated=result.truncated,
                scope=scope,
                summary_md=summary_md,
                summary_chars=len(summary_md),
                summary_truncated=summary_truncated,
                tabular_available=tabular_available,
            )

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
            is_platform_bypass = await _authorize_fast_ingest_delete(get_rebac_engine(), user, document_uid, self.vector_store)
            try:
                logger.info(
                    "[FAST TEXT][INGEST][DELETE] user=%s doc_uid=%s session=%s storage_key=%s backend=%s platform_bypass=%s",
                    user.uid,
                    document_uid,
                    session_id,
                    storage_key,
                    self._scheduler_backend(),
                    is_platform_bypass,
                )
                await self._delete_fast_ingest_artifacts(
                    user=user,
                    document_uid=document_uid,
                    storage_key=storage_key,
                    is_platform_bypass=is_platform_bypass,
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
