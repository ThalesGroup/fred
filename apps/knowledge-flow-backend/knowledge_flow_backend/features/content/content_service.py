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
import logging
import mimetypes
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, NamedTuple, Tuple

import pandas as pd
from fred_core import AuthorizationError, DocumentPermission, KeycloakUser, convert_office_file_to_pdf
from fred_core.documents.document_structures import DocumentMetadata, FileType, ProcessingStage, ProcessingStatus
from fred_core.kpi import BaseKPIWriter, KPIActor
from tabulate import tabulate

from knowledge_flow_backend.core.stores.content.base_content_store import FileMetadata
from knowledge_flow_backend.features.tabular.artifacts import read_tabular_artifact

logger = logging.getLogger(__name__)

# Office formats the viewer can show as-is, by rendering them to PDF. LibreOffice reads
# each directly (no OOXML upgrade first). Only formats ingestion accepts belong here:
# one no processor handles never reaches the library, so listing it would be inert.
PDF_RENDERABLE_SUFFIXES = {".docx", ".doc", ".odt", ".pptx", ".ppt"}

# Name of the derived PDF cached under the document's own output/ prefix, so it is
# wiped along with everything else when the document is deleted.
PDF_RENDER_ARTIFACT_NAME = "render.pdf"

# Renders run on their OWN small pool, never the default executor `asyncio.to_thread`
# would use. A conversion holds its worker for the whole `soffice` run — up to the
# 60 s timeout — and the default executor is shared with RAG search, summarization,
# metadata deletes and ingestion. Left there, a handful of Word previews would stall
# the retrieval path of every agent turn on the pod. The worker count doubles as the
# cap on concurrent `soffice` processes, each of which costs hundreds of MB of RSS.
# Same admission shape as `features/tabular/execution.py`.
PDF_RENDER_MAX_CONCURRENCY = 2

_render_executor: ThreadPoolExecutor | None = None
_render_executor_lock = threading.Lock()


def _get_render_executor() -> ThreadPoolExecutor:
    global _render_executor
    if _render_executor is None:
        with _render_executor_lock:
            if _render_executor is None:
                _render_executor = ThreadPoolExecutor(
                    max_workers=PDF_RENDER_MAX_CONCURRENCY,
                    thread_name_prefix="office-pdf-render",
                )
    return _render_executor


class PdfRenderUnsupportedError(ValueError):
    """Raised when a document's format has no PDF rendering path."""


class PdfRenderFailedError(RuntimeError):
    """Raised when LibreOffice could not produce a PDF for a supported format."""


class PdfRender(NamedTuple):
    """One document rendered as PDF, and whether those exact bytes are persisted.

    `cached` is what makes byte ranges safe to serve: LibreOffice stamps
    /CreationDate and /ID, so two renders of the same document differ in length
    and offsets. Only bytes that came from (or were just written to) the cache
    are guaranteed to be the same object a follow-up range request will read.
    """

    content: bytes
    file_name: str
    cached: bool


class ContentService:
    """
    Service for retrieving document content and converting it to markdown.
    Focuses solely on content retrieval and conversion.
    """

    def __init__(self):
        """Initialize content service with necessary stores."""
        from knowledge_flow_backend.application_context import ApplicationContext

        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        self.content_store = ApplicationContext.get_instance().get_content_store()
        self.config = ApplicationContext.get_instance().get_config()
        self.rebac = ApplicationContext.get_instance().get_rebac_engine()
        self.kpi: BaseKPIWriter = ApplicationContext.get_instance().get_kpi_writer()
        self._tabular_service = None
        # Per-document cold-render locks; see `_render_lock`.
        self._render_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _preview_status(metadata: DocumentMetadata) -> ProcessingStatus:
        return metadata.processing.stages.get(ProcessingStage.PREVIEW_READY, ProcessingStatus.NOT_STARTED)

    @staticmethod
    def _is_tabular_document(metadata: DocumentMetadata) -> bool:
        """
        Return whether one document should use the tabular preview flow.

        Why this exists:
        - Tabular previews are now rendered from indexed Parquet artifacts
          rather than persisted `table.csv` files.

        How to use:
        - Pass the loaded document metadata before selecting the preview path.
        """
        return metadata.file.file_type == FileType.CSV or metadata.file.mime_type == "text/csv"

    @staticmethod
    def _dataframe_to_markdown_preview(df: pd.DataFrame) -> str:
        """
        Convert one bounded DataFrame into the UI markdown preview format.

        Why this exists:
        - Markdown and Parquet-backed tabular previews should share the same
          empty-state formatting.

        How to use:
        - Pass a small preview DataFrame, typically already limited to the
          desired row count.
        """

        def _format_cell(value: object) -> str:
            text = "" if value is None else str(value)
            return text.replace("|", "&#124;").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

        formatted_headers = [_format_cell(name) for name in df.columns.tolist()]
        formatted_rows = [[_format_cell(cell) for cell in row] for row in df.itertuples(index=False, name=None)]
        preview_str = tabulate(formatted_rows, headers=formatted_headers, tablefmt="github")
        if preview_str is None or preview_str.strip() == "":
            return "_(The CSV file is empty or has no data to display)_"
        return preview_str

    def _get_tabular_service(self):
        """
        Lazily return the tabular service used for Parquet-backed previews.

        Why this exists:
        - Content previews need tabular runtime access only for CSV documents.
        - Lazy initialization keeps the default content-service setup light in
          tests that never touch tabular previews.

        How to use:
        - Call before rendering one tabular preview from a Parquet artifact.
        """
        if self._tabular_service is None:
            from knowledge_flow_backend.features.tabular.service import TabularService

            self._tabular_service = TabularService()
        return self._tabular_service

    async def _render_tabular_preview(self, user: KeycloakUser, metadata: DocumentMetadata) -> str:
        """
        Render one tabular preview directly from the indexed Parquet artifact.

        Why this exists:
        - The tabular runtime should not persist a second large preview copy of
          the source CSV just for UI rendering.

        How to use:
        - Call only once `SQL_INDEXED` is done and a `tabular_v1` artifact is
          present on the document metadata.
        """
        preview_frame = await self._get_tabular_service().read_dataset_preview_frame(
            user,
            metadata.document_uid,
            max_rows=200,
        )
        return self._dataframe_to_markdown_preview(preview_frame)

    def _get_output_artifact(self, document_uid: str, *candidate_names: str) -> tuple[str, bytes]:
        for candidate_name in candidate_names:
            try:
                data = self.content_store.get_output_artifact(f"{document_uid}/output/{candidate_name}")
                return candidate_name, data
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"No preview artifact found for document {document_uid}. Tried: {', '.join(candidate_names)}")

    async def get_document_metadata(self, user: KeycloakUser, document_uid: str) -> DocumentMetadata:
        """
        Return the metadata dict for a document UID.

        Raises
        -------
        ValueError
            If the UID is empty.
        FileNotFoundError
            If no metadata exists for that UID.
        """
        if not document_uid:
            raise ValueError("Document UID is required")

        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

        metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
        if metadata is None:
            # Let the controller map this to a 404
            raise FileNotFoundError(f"No metadata found for document {document_uid}")
        return metadata

    async def get_original_content(self, user: KeycloakUser, document_uid: str) -> Tuple[BinaryIO, str, str]:
        """
        Returns binary stream of original input file, filename and content type.
        """
        metadata = await self.get_document_metadata(user, document_uid)
        document_name = metadata.document_name
        content_type = mimetypes.guess_type(document_name)[0] or "application/octet-stream"

        try:
            stream = self.content_store.get_content(document_uid)
        except FileNotFoundError:
            raise FileNotFoundError(f"Original input file not found for document {document_uid}")
        return stream, document_name, content_type

    async def get_document_media(self, user: KeycloakUser, document_uid: str, media_id: str) -> Tuple[BinaryIO, str, str]:
        """
        Returns media file associated with a document if it exists.
        """
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)
        content_type = mimetypes.guess_type(media_id)[0] or "application/octet-stream"

        try:
            stream = self.content_store.get_media(document_uid, media_id)
        except FileNotFoundError:
            raise FileNotFoundError(f"No media found for document {document_uid} with media ID {media_id}")

        return stream, media_id, content_type

    async def get_preview_artifact(
        self,
        user: KeycloakUser,
        document_uid: str,
        artifact_path: str,
    ) -> Tuple[BinaryIO, str, str]:
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)
        artifact_name = (artifact_path or "").strip().lstrip("/")
        if not artifact_name:
            raise FileNotFoundError("Preview artifact path is empty.")

        try:
            data = self.content_store.get_output_artifact(f"{document_uid}/output/{artifact_name}")
        except FileNotFoundError:
            raise FileNotFoundError(f"No preview artifact found for document {document_uid} at path {artifact_name}")

        content_type = mimetypes.guess_type(artifact_name)[0] or "application/octet-stream"
        return BytesIO(data), artifact_name.split("/")[-1], content_type

    def _get_vector_store(self):
        """Resolved lazily: only the session-attachment fallback below needs it."""
        from knowledge_flow_backend.application_context import ApplicationContext

        context = ApplicationContext.get_instance()
        return context.get_create_vector_store(context.get_embedder())

    def _session_attachment_text(self, user: KeycloakUser, document_uid: str) -> str:
        return self._get_vector_store().get_own_session_document_text(document_uid, user.uid)

    async def get_markdown_preview(self, user: KeycloakUser, document_uid: str) -> str:
        """
        Return a markdown preview of the document.
        For CSV files, returns the first 200 rows as a markdown table.
        For other files, returns the generated markdown preview.

        Resolves both document sources Fred exposes to agents under one uid:
        corpus documents (metadata + preview artifact) and session attachments
        (chat uploads, which exist only as vectors). It is the single resolution
        point - the summarize and extract features read through it too.

        This method raises FileNotFoundError if no preview is found.
        """
        try:
            document_metadata = await self.get_document_metadata(user, document_uid)
        except (FileNotFoundError, AuthorizationError):
            # No corpus record the caller may read: either a session attachment
            # (no metadata, no ReBAC tuple, so the check fails closed) or a uid
            # they genuinely cannot reach. Reconstruction joins only the
            # caller's OWN session chunks, so a denied corpus document is never
            # readable back through its vectors - empty re-raises the denial.
            try:
                text = await asyncio.to_thread(self._session_attachment_text, user, document_uid)
            except Exception:
                # An unreachable or misconfigured vector store must not rewrite
                # the caller's 403/404 into some unrelated status.
                logger.warning("Session-attachment fallback failed for document %s", document_uid, exc_info=True)
                text = ""
            if text:
                return text
            raise
        if self._is_tabular_document(document_metadata):
            sql_indexed_status = document_metadata.processing.stages.get(ProcessingStage.SQL_INDEXED, ProcessingStatus.NOT_STARTED)
            if sql_indexed_status == ProcessingStatus.DONE and read_tabular_artifact(document_metadata) is not None:
                return await self._render_tabular_preview(user, document_metadata)

        preview_status = self._preview_status(document_metadata)
        if preview_status != ProcessingStatus.DONE:
            raise FileNotFoundError(f"Preview not ready for document {document_uid}. Current preview stage: {preview_status.value}.")
        mime_type = document_metadata.file.mime_type
        if self._is_tabular_document(document_metadata):
            try:
                candidate_name, preview_bytes = self._get_output_artifact(
                    document_uid,
                    "table.csv",
                    "output.md",
                    "output.txt",
                )
            except FileNotFoundError:
                raise FileNotFoundError(f"No preview found for document {document_uid} of type {mime_type}.")

            if candidate_name == "table.csv":
                csv_file_like = BytesIO(preview_bytes)
                df = pd.read_csv(csv_file_like, nrows=200)
                return self._dataframe_to_markdown_preview(df)
            return preview_bytes.decode("utf-8")

        try:
            _, preview_bytes = self._get_output_artifact(document_uid, "output.md", "output.txt")
            return preview_bytes.decode("utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(f"No preview found for document {document_uid} of type {mime_type}.")

    async def get_file_metadata(self, user: KeycloakUser, document_uid: str) -> FileMetadata:
        metadata = await self.get_document_metadata(user, document_uid)
        meta = self.content_store.get_file_metadata(document_uid)
        # The DB record is authoritative for the display name (it reflects a
        # rename); the content store's own file_name is just whatever the blob
        # was originally uploaded as and never changes.
        meta.file_name = metadata.document_name
        if not meta.content_type:
            import mimetypes

            guessed = mimetypes.guess_type(meta.file_name)[0]
            meta.content_type = guessed or "application/octet-stream"
        return meta

    async def get_full_stream(self, user: KeycloakUser, document_uid: str) -> BinaryIO:
        await self.get_document_metadata(user, document_uid)
        return self.content_store.get_content(document_uid)

    async def get_range_stream(self, user: KeycloakUser, document_uid: str, *, start: int, length: int) -> BinaryIO:
        await self.get_document_metadata(user, document_uid)
        if start < 0 or length <= 0:
            raise ValueError("Invalid byte range requested.")
        return self.content_store.get_content_range(document_uid, start=start, length=length)

    def _render_office_to_pdf(self, document_uid: str, suffix: str) -> tuple[bytes, bool] | None:
        """Blocking: pull the original file, convert it with LibreOffice, cache the PDF.

        Called through `asyncio.to_thread` — both the store round-trips and the
        `soffice` subprocess are blocking, and a conversion can take seconds.
        """
        with tempfile.TemporaryDirectory(prefix="pdf-render-") as tmp:
            source_path = Path(tmp) / f"source{suffix}"
            stream = self.content_store.get_content(document_uid)
            try:
                with source_path.open("wb") as out:
                    while chunk := stream.read(1024 * 1024):
                        out.write(chunk)
            finally:
                getattr(stream, "close", lambda: None)()

            pdf_path = convert_office_file_to_pdf(source_path)
            if pdf_path is None:
                return None
            pdf_bytes = pdf_path.read_bytes()

        try:
            self.content_store.put_output_artifact(
                f"{document_uid}/output/{PDF_RENDER_ARTIFACT_NAME}",
                pdf_bytes,
                content_type="application/pdf",
            )
        except Exception:
            # Not fatal, but the caller must not serve byte ranges out of bytes no
            # follow-up request can read back — see PdfRender.cached.
            logger.warning("[CONTENT] Could not cache the PDF render of %s", document_uid, exc_info=True)
            return pdf_bytes, False
        return pdf_bytes, True

    def _render_lock(self, document_uid: str) -> asyncio.Lock:
        """Serialize cold renders of ONE document within this worker.

        Without it a document opened by several viewers at once is converted once
        per viewer, and the losing renders overwrite the cache the winners' range
        requests are reading. Best-effort by nature: it does not span replicas,
        which is why `PdfRender.cached` — not this lock — is what actually keeps a
        ranged response consistent.
        """
        lock = self._render_locks.get(document_uid)
        if lock is None:
            lock = self._render_locks[document_uid] = asyncio.Lock()
        return lock

    async def _read_cached_render(self, document_uid: str) -> bytes | None:
        """Read the cached PDF off the event loop; None when it is not there yet."""

        def _read() -> bytes | None:
            try:
                return self._get_output_artifact(document_uid, PDF_RENDER_ARTIFACT_NAME)[1]
            except FileNotFoundError:
                return None

        return await asyncio.to_thread(_read)

    async def get_pdf_render(self, user: KeycloakUser, document_uid: str) -> PdfRender:
        """
        Return the document rendered as PDF, plus the name to serve it under.

        A supported office format (see `PDF_RENDERABLE_SUFFIXES`) is converted by
        LibreOffice and cached under the document's own `output/` prefix, so only
        the first viewer pays the conversion and the artifact is deleted with the
        document. A `.pdf` is NOT handled here — it needs no rendering and is
        served untouched by `/raw_content/stream/{uid}`.

        Raises `PdfRenderUnsupportedError` for a format with no rendering path and
        `PdfRenderFailedError` when the conversion itself could not be performed.
        """
        metadata = await self.get_document_metadata(user, document_uid)
        document_name = metadata.document_name
        suffix = Path(document_name).suffix.lower()

        if suffix not in PDF_RENDERABLE_SUFFIXES:
            detail = "is already a PDF — stream it from /raw_content/stream" if suffix == ".pdf" else "has no PDF rendering path"
            raise PdfRenderUnsupportedError(f"Document {document_uid} ({suffix or 'no extension'}) {detail}.")

        pdf_name = f"{Path(document_name).stem}.pdf"
        cached = await self._read_cached_render(document_uid)
        if cached is not None:
            return PdfRender(cached, pdf_name, cached=True)

        lock = self._render_lock(document_uid)
        try:
            async with lock:
                # A conversion may have completed while this request waited for the lock.
                cached = await self._read_cached_render(document_uid)
                if cached is not None:
                    return PdfRender(cached, pdf_name, cached=True)

                loop = asyncio.get_running_loop()
                with self.kpi.timer(
                    "content.pdf_render_latency_ms",
                    dims={"file_type": suffix.lstrip(".")},
                    actor=KPIActor(type="system"),
                ) as kpi_dims:
                    rendered = await loop.run_in_executor(
                        _get_render_executor(),
                        self._render_office_to_pdf,
                        document_uid,
                        suffix,
                    )
                    kpi_dims["status"] = "error" if rendered is None else "ok"
        finally:
            # Keep the registry from growing one Lock per document ever previewed:
            # the entry only exists to rendezvous concurrent cold opens.
            if not lock.locked():
                self._render_locks.pop(document_uid, None)

        if rendered is None:
            raise PdfRenderFailedError(f"LibreOffice could not render document {document_uid} as PDF.")
        pdf_bytes, is_cached = rendered
        return PdfRender(pdf_bytes, pdf_name, cached=is_cached)
