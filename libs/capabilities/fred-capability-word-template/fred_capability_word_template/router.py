# Copyright Thales 2026
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

"""The capability's routes, mounted under `/capabilities/word_template`.

Every handler requires the caller to own the session (`_session_owner`, the
pod's private-per-owner policy). Preview and download read the session's
document (`session_document`); the "Rédaction" view reads and edits it
(`.../content`, `.../edits`, `.../undo`); attachments and images keep the
chat's files. Docx work runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

from docx import Document
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Security,
    UploadFile,
    status,
)
from fastapi.responses import Response, StreamingResponse
from fred_core import (
    KeycloakUser,
    convert_office_bytes_to_pdf,
    get_current_user,
    oauth2_scheme,
)
from fred_runtime.common.kf_workspace_client import (
    KfWorkspaceClient,
    WorkspaceRetrievalError,
)
from pydantic import BaseModel, Field

from fred_capability_word_template.analysis import parse_analysis
from fred_capability_word_template.content import (
    ContentOperation,
    ContentPart,
    RepeatableGroup,
    build_content_parts,
    repeatable_groups,
)
from fred_capability_word_template.images import (
    MAX_IMAGE_BYTES,
    batch_image_ids,
    extract_attachment_images,
    images_for,
    sniff_image_type,
    store_image,
)
from fred_capability_word_template.operations import (
    BatchError,
    apply_batch,
    parse_operation,
)
from fred_capability_word_template.session_document import (
    BaseUnavailable,
    content_sha256,
    load_base_bytes,
    save_snapshot,
    session_docx,
)
from fred_capability_word_template.store import (
    BaseRef,
    Batch,
    BatchConflict,
    SessionState,
    Writer,
    describe_batch,
    get_word_template_store,
)
from fred_capability_word_template.toc import with_update_fields

logger = logging.getLogger(__name__)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"
_FILENAME = "document"
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


class WordTemplateSessionResponse(BaseModel):
    """What the side panel needs to know before fetching a preview.
    ``base_kind``/``base_ref`` name the document's base (a library template
    key, or an attachment id with its ``base_filename``); ``template_key`` is
    set only when the base is a library template."""

    session_id: str
    template_key: str | None = None
    base_kind: Literal["template", "attachment"] | None = None
    base_ref: str | None = None
    base_filename: str | None = None
    pinned: bool = False
    edit_count: int = 0
    updated_at: datetime | None = None


class WordTemplateAttachmentResponse(BaseModel):
    """An attached Word file kept for the session (or the one already kept
    with the same bytes)."""

    attachment_id: str
    filename: str


class WordTemplateImageResponse(BaseModel):
    """An image the model may place in the session's document (or the one
    already kept with the same bytes), referenced ``img:<image_id>``."""

    image_id: str
    filename: str
    content_type: str
    size: int
    context_text: str | None = None


class WordTemplateContentBase(BaseModel):
    """What the document is built on: a library template (``ref`` = its
    key) or an attached file (``ref`` = its id, with its ``filename``)."""

    kind: Literal["template", "attachment"]
    ref: str
    filename: str | None = None


class WordTemplateContentResponse(BaseModel):
    """The "Rédaction" view of the session's CURRENT document.

    ``seq`` is the length of the operation log this view was built from:
    send it back as ``base_seq`` with the next edit. ``parts`` follow the
    document's reading order (``"hf"``, headers and footers, last); see
    ``content.py`` for every block kind."""

    session_id: str
    seq: int
    base: WordTemplateContentBase
    parts: list[ContentPart] = []


class WordTemplateEditRequest(BaseModel):
    """One batch of the collaborator's edits. Every address refers to the
    document as of ``base_seq`` (the ``seq`` of the view they were made
    on); the batch applies entirely or not at all."""

    base_seq: int = Field(ge=0)
    operations: list[ContentOperation] = Field(min_length=1)


class WordTemplateUndoRequest(BaseModel):
    """``base_seq``, when given, must be the current log length (409
    otherwise): the collaborator undoes the edit they saw, never one the
    model made meanwhile."""

    base_seq: int | None = Field(default=None, ge=0)


async def _fetch_template_bytes(
    *, team_id: str, agent_instance_id: str, template_key: str, access_token: str
) -> bytes | None:
    """The template's bytes from the instance config-asset area (the KF path
    `AgentConfigAssetsAdapter` uses). None on any failure."""
    path = f"teams/{team_id}/agents/{agent_instance_id}/config/{template_key}"
    try:
        client = KfWorkspaceClient(access_token=access_token)
        blob = await client.fs_download_blob(path, access_token=access_token)
        return blob.bytes
    except WorkspaceRetrievalError:
        logger.info("[WORD_TEMPLATE] no template asset at %s", path)
        return None
    except Exception:  # noqa: BLE001 - any KF client failure means "no template"
        logger.exception("[WORD_TEMPLATE] failed to fetch template %s", path)
        return None


async def _base_or_404(session_id: str) -> tuple[SessionState, BaseRef]:
    state = await get_word_template_store().get_session(session_id)
    base = state.base if state is not None else None
    if state is None or base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Word document for session {session_id}.",
        )
    return state, base


_BASE_UNAVAILABLE = "The session's Word template could not be retrieved."
_STALE = "The document changed since it was loaded: reload it and edit again."
_STRUCTURAL = {"write", "insert_after", "repeat", "remove"}


@dataclass
class _Current:
    """The session's current document and how it was obtained."""

    state: SessionState
    base: BaseRef
    batches: list[Batch]
    docx: bytes
    base_bytes: bytes | None  # set when the base itself was loaded
    fetch_template: Callable[[str], Awaitable[bytes]]


async def _current_document(session_id: str, access_token: str | None) -> _Current:
    """The session's document: its snapshot, else its base replayed with
    its log (404 without a base, 409 when it cannot be built)."""
    state, base = await _base_or_404(session_id)
    team_id, agent_instance_id = state.team_id, state.agent_instance_id
    if base.kind == "template" and not (team_id and agent_instance_id and access_token):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This session has no agent instance to fetch its template from.",
        )

    async def fetch_template(template_key: str) -> bytes:
        assert team_id and agent_instance_id and access_token  # checked above
        template = await _fetch_template_bytes(
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            template_key=template_key,
            access_token=access_token,
        )
        if template is None:
            raise BaseUnavailable(template_key)
        return template

    loaded: list[bytes] = []

    async def load_base() -> bytes:
        try:
            data = await load_base_bytes(base, session_id, fetch_template)
        except BaseUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_BASE_UNAVAILABLE
            ) from exc
        loaded.append(data)
        return data

    batches = await get_word_template_store().list_batches(session_id)
    try:
        docx = await session_docx(session_id, base, batches, load_base)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - replaying a malformed base can raise anything
        logger.exception("[WORD_TEMPLATE] replay failed for %s", session_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The session's edits could not be applied to its template.",
        ) from exc
    return _Current(
        state, base, batches, docx, loaded[0] if loaded else None, fetch_template
    )


async def _render_or_409(session_id: str, access_token: str | None) -> bytes:
    return (await _current_document(session_id, access_token)).docx


# --- session ownership ------------------------------------------------------------


def _security_enabled() -> bool:
    from fred_core.security import oidc

    return bool(getattr(oidc, "KEYCLOAK_ENABLED", False))


def _history_store() -> Any | None:
    """The pod's conversation history store, the authoritative record of
    who owns a session (None outside a configured pod)."""
    try:
        from fred_runtime.runtime_context import get_runtime_context

        return get_runtime_context().config.history_store
    except Exception:  # noqa: BLE001 - no runtime context: nothing to check against
        return None


async def _session_owner(
    session_id: str,
    user: Annotated[KeycloakUser, Depends(get_current_user)],
) -> KeycloakUser:
    """The caller, once they are known to own ``session_id`` (403 otherwise).
    Mirrors the pod's ``_enforce_session_ownership``: a session with no
    history yet is allowed."""
    if not _security_enabled():
        return user
    history = _history_store()
    if history is None:
        return user
    # The owner's own calls (the pane polls) cost one query.
    if await history.session_belongs_to_user(session_id, user.uid):
        return user
    if not await history.session_exists(session_id):
        return user
    logger.warning(
        "[WORD_TEMPLATE] user=%s denied on session=%s (not its owner)",
        user.uid,
        session_id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"session {session_id!r} does not belong to the authenticated user",
    )


Owner = Annotated[KeycloakUser, Depends(_session_owner)]


# --- the "Rédaction" view -----------------------------------------------------------

# Template key -> sha256 of its bytes (the analysis cache key). A key never
# changes bytes; pod-local, a miss fetches the template once.
_TEMPLATE_SHA: OrderedDict[str, str] = OrderedDict()
_TEMPLATE_SHA_SIZE = 256


async def _analysis_groups(
    session_id: str, current: _Current, batches: list[Batch]
) -> list[RepeatableGroup]:
    """The analysis's repeatable blocks, while their addresses (those of the
    blank base) still hold: no structural edit in the log. Best effort."""
    if any(op.get("op") in _STRUCTURAL for batch in batches for op in batch):
        return []
    base = current.base
    store = get_word_template_store()
    try:
        sha: str | None = None
        if current.base_bytes is not None:
            sha = await asyncio.to_thread(content_sha256, current.base_bytes)
        elif base.kind == "attachment":
            sha = next(
                (
                    a.sha256
                    for a in await store.list_attachments(session_id)
                    if a.attachment_id == base.ref
                ),
                None,
            )
        else:
            sha = _TEMPLATE_SHA.get(base.ref)
            if sha is None:
                data = await current.fetch_template(base.ref)
                sha = await asyncio.to_thread(content_sha256, data)
        if sha is None:
            return []
        if base.kind == "template":
            _TEMPLATE_SHA[base.ref] = sha
            _TEMPLATE_SHA.move_to_end(base.ref)
            while len(_TEMPLATE_SHA) > _TEMPLATE_SHA_SIZE:
                _TEMPLATE_SHA.popitem(last=False)
        raw = await store.get_analysis(sha)
        return repeatable_groups(parse_analysis(raw)) if raw else []
    except Exception:  # noqa: BLE001 - the view works without the groups
        logger.info(
            "[WORD_TEMPLATE] session=%s no repeatable blocks available",
            session_id,
            exc_info=True,
        )
        return []


async def _content_view(
    session_id: str, current: _Current, batches: list[Batch], docx: bytes
) -> WordTemplateContentResponse:
    base = current.base
    groups, filename = await asyncio.gather(
        _analysis_groups(session_id, current, batches),
        _attachment_filename(session_id, base),
    )
    # CPU-bound (parse + map + Markdown): off the event loop.
    parts = await asyncio.to_thread(build_content_parts, docx, groups=groups)
    return WordTemplateContentResponse(
        session_id=session_id,
        seq=len(batches),
        base=WordTemplateContentBase(kind=base.kind, ref=base.ref, filename=filename),
        parts=parts,
    )


async def _attachment_filename(session_id: str, base: BaseRef | None) -> str | None:
    if base is None or base.kind != "attachment":
        return None
    return next(
        (
            a.filename
            for a in await get_word_template_store().list_attachments(session_id)
            if a.attachment_id == base.ref
        ),
        None,
    )


def _stale(seq: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"message": _STALE, "seq": seq},
    )


def _check_docx_and_hash(content: bytes) -> str:
    """python-docx must open it (raises otherwise); returns its sha256."""
    Document(io.BytesIO(content))
    return content_sha256(content)


def build_router() -> APIRouter:
    """The capability's APIRouter (no prefix - the pod mounts it under
    `/capabilities/word_template`)."""

    router = APIRouter(tags=["Word Template"])

    @router.get(
        "/sessions/{session_id}",
        response_model=WordTemplateSessionResponse,
        operation_id="getWordTemplateSession",
        summary="The session's template and edit count",
    )
    async def get_word_template_session(
        session_id: str,
        _user: Owner,
    ) -> WordTemplateSessionResponse:
        state = await get_word_template_store().get_session(session_id)
        if state is None:
            return WordTemplateSessionResponse(session_id=session_id)
        base = state.base
        filename = await _attachment_filename(session_id, base)
        return WordTemplateSessionResponse(
            session_id=session_id,
            template_key=base.ref if base and base.kind == "template" else None,
            base_kind=base.kind if base else None,
            base_ref=base.ref if base else None,
            base_filename=filename,
            pinned=state.pinned_at is not None,
            edit_count=state.batch_count,
            updated_at=state.updated_at,
        )

    @router.post(
        "/sessions/{session_id}/attachments",
        response_model=WordTemplateAttachmentResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="uploadWordTemplateAttachment",
        summary="Keep a Word file attached in the session's chat",
    )
    async def upload_word_template_attachment(
        session_id: str,
        _user: Owner,
        file: Annotated[UploadFile, File()],
    ) -> WordTemplateAttachmentResponse:
        """Called by the frontend for each .docx attached in a chat where
        this capability is active: the platform keeps no attachment bytes,
        so this is the capability's own copy. The model may later make it
        the document's base (``use_attached_document``)."""
        content = await file.read(MAX_ATTACHMENT_BYTES + 1)
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Word files are limited to 20 MB.",
            )
        try:
            # CPU-bound (unzip + XML parse, then hash): off the event loop.
            sha = await asyncio.to_thread(_check_docx_and_hash, content)
        except Exception as exc:  # noqa: BLE001 - python-docx raises many types on a malformed file
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="This file could not be read as a Word (.docx) document.",
            ) from exc
        filename = (file.filename or "document.docx")[:512]
        info = await get_word_template_store().put_attachment(
            session_id, filename, sha, content
        )
        logger.info(
            "[WORD_TEMPLATE] session=%s kept %s (%d bytes)",
            session_id,
            info.attachment_id,
            info.size,
        )
        if not info.images_extracted:
            # Its pictures become session images.
            await extract_attachment_images(session_id, info, content)
        return WordTemplateAttachmentResponse(
            attachment_id=info.attachment_id, filename=info.filename
        )

    @router.delete(
        "/sessions/{session_id}/attachments/{attachment_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="deleteWordTemplateAttachment",
        summary="Forget a Word file removed from the session's chat",
    )
    async def delete_word_template_attachment(
        session_id: str,
        attachment_id: str,
        _user: Owner,
    ) -> Response:
        """Called by the frontend when the collaborator removes an attached
        .docx from the chat. Refused (409) while it is the document's base;
        pictures taken from it that the document places stay."""
        store = get_word_template_store()
        state = await store.get_session(session_id)
        base = state.base if state is not None else None
        if base is not None and base.kind == "attachment" and base.ref == attachment_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This file is the document's base and stays.",
            )
        placed = batch_image_ids(await store.list_batches(session_id))
        if not await store.delete_attachment(
            session_id, attachment_id, keep_image_ids=placed
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
            )
        logger.info("[WORD_TEMPLATE] session=%s forgot %s", session_id, attachment_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete(
        "/sessions/{session_id}/images/{image_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="deleteWordTemplateImage",
        summary="Forget an image removed from the session's chat",
    )
    async def delete_word_template_image(
        session_id: str,
        image_id: str,
        _user: Owner,
    ) -> Response:
        """Called by the frontend when the collaborator removes an attached
        image from the chat. Refused (409) once the document places it."""
        store = get_word_template_store()
        if image_id in batch_image_ids(await store.list_batches(session_id)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This image is placed in the document and stays.",
            )
        if not await store.delete_image(session_id, image_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Image not found."
            )
        logger.info("[WORD_TEMPLATE] session=%s forgot %s", session_id, image_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/sessions/{session_id}/images",
        response_model=WordTemplateImageResponse,
        response_model_exclude_none=True,
        status_code=status.HTTP_201_CREATED,
        operation_id="uploadWordTemplateImage",
        summary="Keep an image attached in the session's chat",
    )
    async def upload_word_template_image(
        session_id: str,
        _user: Owner,
        file: Annotated[UploadFile, File()],
    ) -> WordTemplateImageResponse:
        """Called by the frontend for each image attached in a chat where
        this capability is active: the model may then place it in the
        document as ``![caption](img:<image_id>)``. PNG, JPEG or GIF,
        recognised by their bytes."""
        content = await file.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Images are limited to 10 MB.",
            )
        content_type = sniff_image_type(content)
        if content_type is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PNG, JPEG and GIF images can be placed in a document.",
            )
        info = await store_image(
            session_id, content, content_type, file.filename or "image"
        )
        logger.info(
            "[WORD_TEMPLATE] session=%s kept %s (%d bytes)",
            session_id,
            info.image_id,
            info.size,
        )
        return WordTemplateImageResponse(
            image_id=info.image_id,
            filename=info.filename,
            content_type=info.content_type,
            size=info.size,
            context_text=info.context_text,
        )

    @router.get(
        "/sessions/{session_id}/images/{image_id}",
        operation_id="getWordTemplateImage",
        summary="One session image's bytes (editor display)",
        response_class=Response,
        responses={200: {"content": {"image/*": {}}}},
    )
    async def get_word_template_image(
        session_id: str,
        image_id: str,
        _user: Owner,
    ) -> Response:
        found = await get_word_template_store().get_image(session_id, image_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Image not found."
            )
        info, content = found
        return Response(
            content=content,
            media_type=info.content_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @router.get(
        "/sessions/{session_id}/document.docx",
        operation_id="downloadWordTemplateDocument",
        summary="Download the session's Word document",
    )
    async def download_word_template_document(
        session_id: str,
        _user: Owner,
        access_token: str | None = Security(oauth2_scheme),
    ) -> StreamingResponse:
        data = await _render_or_409(session_id, access_token)
        # Word recomputes the table of contents' page numbers on opening.
        data = await asyncio.to_thread(with_update_fields, data)
        headers = {"Content-Disposition": f'attachment; filename="{_FILENAME}.docx"'}
        return StreamingResponse(iter([data]), media_type=_DOCX_MIME, headers=headers)

    @router.get(
        "/sessions/{session_id}/preview.pdf",
        operation_id="previewWordTemplateDocument",
        summary="Word-faithful PDF preview of the session's document",
    )
    async def preview_word_template_document(
        session_id: str,
        _user: Owner,
        access_token: str | None = Security(oauth2_scheme),
    ) -> StreamingResponse:
        """Converted in the pod by fred-core's bounded LibreOffice helper
        (the binary ships in the fred-agents image), regenerated on every
        call."""
        data = await _render_or_409(session_id, access_token)
        pdf = await convert_office_bytes_to_pdf(data, suffix=".docx")
        if pdf is None:
            logger.warning(
                "[WORD_TEMPLATE] session=%s PDF conversion failed",
                session_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The document could not be converted to a PDF preview.",
            )
        return StreamingResponse(iter([pdf]), media_type=_PDF_MIME)

    @router.get(
        "/sessions/{session_id}/content",
        response_model=WordTemplateContentResponse,
        response_model_exclude_none=True,
        operation_id="getWordTemplateContent",
        summary="The session's document as editable parts (Rédaction view)",
    )
    async def get_word_template_content(
        session_id: str,
        _user: Owner,
        access_token: str | None = Security(oauth2_scheme),
    ) -> WordTemplateContentResponse:
        """404 while the session has no base document; 409 when it cannot
        be built (template not retrievable)."""
        current = await _current_document(session_id, access_token)
        return await _content_view(session_id, current, current.batches, current.docx)

    @router.post(
        "/sessions/{session_id}/edits",
        response_model=WordTemplateContentResponse,
        response_model_exclude_none=True,
        operation_id="editWordTemplateContent",
        summary="Apply one batch of the collaborator's edits",
        responses={
            409: {"description": "The document changed since base_seq: reload"},
            422: {"description": "The batch was rejected: detail.problems"},
        },
    )
    async def edit_word_template_content(
        session_id: str,
        body: WordTemplateEditRequest,
        user: Owner,
        access_token: str | None = Security(oauth2_scheme),
    ) -> WordTemplateContentResponse:
        """Same validation as the model's ``edit_document``: on any problem
        nothing is applied and ``detail.problems`` lists them all (422). A
        batch made on an older state of the log is refused (409,
        ``detail.seq`` = the current log length). On success the batch is
        appended with author ``collaborator`` (it pins the base like the
        model's first edit) and the new view is returned."""
        current = await _current_document(session_id, access_token)
        batches = current.batches
        if body.base_seq != len(batches):
            raise _stale(len(batches))
        operations = [
            op.model_dump(by_alias=True, exclude_none=True) for op in body.operations
        ]
        images = await images_for(session_id, [operations])
        try:
            new_docx = await asyncio.to_thread(
                apply_batch, current.docx, operations, images
            )
        except BatchError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": "The edit was rejected, nothing was applied.",
                    "problems": exc.problems,
                },
            ) from exc
        except Exception as exc:  # noqa: BLE001 - an engine failure on an odd document is a 422, not a 500
            logger.exception(
                "[WORD_TEMPLATE] session=%s batch failed unexpectedly", session_id
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": "This edit could not be applied, nothing was applied.",
                    "problems": [],
                },
            ) from exc
        batch: Batch = [
            parse_operation(op).model_dump(by_alias=True, exclude_none=True)
            for op in operations
        ]
        state = current.state
        writer = Writer(
            user_id=user.uid,
            team_id=state.team_id,
            agent_instance_id=state.agent_instance_id,
        )
        try:
            seq = await get_word_template_store().append_batch(
                session_id,
                current.base,
                batch,
                writer,
                expected_count=len(batches),
                author="collaborator",
            )
        except BatchConflict as exc:
            latest = await get_word_template_store().get_session(session_id)
            raise _stale(latest.batch_count if latest else len(batches)) from exc
        new_log = [*batches, batch]
        await save_snapshot(session_id, current.base, new_log, new_docx)
        logger.info(
            "[WORD_TEMPLATE] session=%s collaborator edit #%d: %s",
            session_id,
            seq,
            describe_batch(batch),
        )
        return await _content_view(session_id, current, new_log, new_docx)

    @router.post(
        "/sessions/{session_id}/undo",
        response_model=WordTemplateContentResponse,
        response_model_exclude_none=True,
        operation_id="undoWordTemplateEdit",
        summary="Cancel the last edit (the model's or the collaborator's)",
        responses={409: {"description": "The document changed since base_seq"}},
    )
    async def undo_word_template_edit(
        session_id: str,
        _user: Owner,
        body: WordTemplateUndoRequest | None = None,
        access_token: str | None = Security(oauth2_scheme),
    ) -> WordTemplateContentResponse:
        """Drops the last batch of the log, whoever made it (as the model's
        ``undo_last_edit``), and returns the new view. With nothing to undo,
        the view is returned unchanged."""
        await _base_or_404(session_id)
        expected = body.base_seq if body is not None else None
        try:
            dropped = await get_word_template_store().drop_last_batch(
                session_id, expected_count=expected
            )
        except BatchConflict as exc:
            latest = await get_word_template_store().get_session(session_id)
            raise _stale(latest.batch_count if latest else 0) from exc
        current = await _current_document(session_id, access_token)
        if dropped is not None:
            logger.info(
                "[WORD_TEMPLATE] session=%s undone: %s",
                session_id,
                describe_batch(dropped),
            )
        return await _content_view(session_id, current, current.batches, current.docx)

    return router
