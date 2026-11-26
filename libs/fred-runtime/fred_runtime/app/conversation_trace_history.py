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
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fred_core import KeycloakUser
from fred_core.conversation_trace import (
    TRACE_SSE_PAGE_FRAMES,
    TraceHistoryAccess,
    TraceHistoryBoundary,
    TraceHistoryIncident,
    TraceHistoryTranscript,
    TraceHttpEvidence,
    TraceId,
    TraceModelEvidence,
    TraceSseFrame,
    TraceSseFramePage,
    TraceSseHeaders,
    TraceToolEvidence,
    is_local_trace_request,
)
from fred_core.history.history_schema import Channel, ToolResultPart
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.security.oidc import require_own_credential
from sqlalchemy.exc import SQLAlchemyError

from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.conversation_trace_model import (
    matched_tool_ids,
    retain_tool_results,
)
from fred_runtime.app.dependencies import get_pod_container
from fred_runtime.app.session_visibility import owner_hidden_sessions

router = APIRouter(prefix="/agents/sessions", tags=["ConversationTraceHistory"])
Container = Annotated[PodApplicationContext, Depends(get_pod_container)]
Caller = Annotated[KeycloakUser, Depends(require_own_credential)]
Session = Annotated[str, Path(min_length=1, max_length=255)]
Exchange = Annotated[str, Path(min_length=1, max_length=255)]
Rank = Annotated[int, Query(ge=-1, lt=2**31)]


def _history(container: PodApplicationContext) -> PostgresHistoryStore | None:
    store = container.get_history_store()
    return store if isinstance(store, PostgresHistoryStore) else None


def _allows_local_trace(container: PodApplicationContext, request: Request) -> bool:
    security = container.configuration.security
    return (
        security.profile is None
        and not security.user.enabled
        and not security.m2m.enabled
        and (security.rebac is None or not security.rebac.enabled)
        and is_local_trace_request(
            request.client.host if request.client is not None else None,
            request.url.hostname,
        )
    )


@router.get(
    "/{session_id}/trace-history-boundary", operation_id="get_trace_history_boundary"
)
async def get_trace_history_boundary(
    session_id: Session,
    caller: Caller,
    container: Container,
    request: Request,
    response: Response,
    exchange_id: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
) -> TraceHistoryBoundary | None:
    response.headers["Cache-Control"] = "no-store"
    store = _history(container)
    if store is None or await owner_hidden_sessions(
        container, caller.uid, request.headers.get("Authorization"), [session_id]
    ):
        return None
    return await store.trace_boundary(session_id, caller.uid, exchange_id)


@router.get(
    "/{session_id}/trace-history-incident/{support_error_ref}",
    operation_id="get_trace_history_incident",
)
async def get_trace_history_incident(
    session_id: Session,
    support_error_ref: TraceId,
    caller: Caller,
    container: Container,
    request: Request,
    response: Response,
) -> TraceHistoryIncident | None:
    response.headers["Cache-Control"] = "no-store"
    store = _history(container)
    if store is None or await owner_hidden_sessions(
        container, caller.uid, request.headers.get("Authorization"), [session_id]
    ):
        return None
    return await store.trace_history_incident(session_id, caller.uid, support_error_ref)


async def _access(
    container: PodApplicationContext,
    request: Request,
    session_id: str,
    exchange_id: str | None = None,
) -> TraceHistoryAccess:
    client = container.conversation_trace_client
    if client is None:
        raise HTTPException(503, "trace_history_access_unavailable")
    access = await client.history_access(
        session_id, request.headers.get("Authorization", ""), exchange_id
    )
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_history_access_denied")
    return access


@router.get(
    "/{session_id}/trace-history-turns", operation_id="list_trace_history_turns"
)
async def list_trace_history_turns(
    session_id: Session,
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=101)] = 51,
    after_rank: Rank = -1,
    after_exchange: Annotated[str, Query(max_length=255)] = "",
    exchange_id: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    latest_only: bool = False,
) -> list[TraceHistoryBoundary]:
    response.headers["Cache-Control"] = "no-store"
    access = await _access(container, request, session_id)
    store = _history(container)
    if store is None:
        return []
    if latest_only or exchange_id is not None:
        boundary = await store.trace_boundary(session_id, access.owner_id, exchange_id)
        return [boundary] if boundary is not None else []
    return await store.trace_history_page(
        session_id,
        access.owner_id,
        limit=limit,
        after=(after_rank, after_exchange) if after_rank >= 0 else None,
    )


@router.get(
    "/{session_id}/trace-history-turns/{exchange_id}",
    operation_id="get_trace_history_transcript",
)
async def get_trace_history_transcript(
    session_id: Session,
    exchange_id: Exchange,
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
    after_rank: Rank = -1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TraceHistoryTranscript:
    response.headers["Cache-Control"] = "no-store"
    access = await _access(container, request, session_id, exchange_id)
    cutoff = access.cutoff
    if cutoff is None and not access.local_content_access:
        raise HTTPException(403, "trace_history_access_denied")
    store = _history(container)
    boundary = (
        await store.trace_boundary(session_id, access.owner_id, exchange_id)
        if store is not None
        else None
    )
    first_rank = boundary.first_rank if boundary is not None else access.captured_rank
    if (
        not access.local_content_access
        and cutoff is not None
        and first_rank is not None
        and not cutoff.covers_exchange(first_rank, exchange_id)
    ):
        raise HTTPException(403, "trace_history_access_denied")
    if store is None or boundary is None:
        return TraceHistoryTranscript(available=False, messages=[])
    result = await store.trace_transcript(
        session_id,
        access.owner_id,
        exchange_id,
        highest_rank=cutoff.last_rank
        if cutoff is not None and not access.local_content_access
        else None,
        after_rank=after_rank,
        limit=limit,
    )
    # A revocation or replacement during the history read must not release the old result.
    if access != await _access(container, request, session_id, exchange_id):
        raise HTTPException(403, "trace_history_access_denied")
    return result


@router.get(
    "/{session_id}/trace-model/{exchange_id}/{ref}",
    operation_id="get_trace_model_evidence",
)
async def get_trace_model_evidence(
    session_id: Session,
    exchange_id: Exchange,
    ref: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
) -> TraceModelEvidence:
    response.headers["Cache-Control"] = "no-store"
    client = container.conversation_trace_client
    if client is None or client.artifacts is None:
        raise HTTPException(503, "trace_model_unavailable")
    authorization = request.headers.get("Authorization", "")
    access = await client.model_access(session_id, exchange_id, ref, authorization)
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_model_access_denied")
    try:
        with anyio.fail_after(5):
            evidence = await client.read_model(session_id, ref)
    except Exception as exc:
        raise HTTPException(503, "trace_model_unavailable") from exc

    tool_ids = matched_tool_ids(evidence)
    history = _history(container)
    if tool_ids and history is not None and access.observed_through_rank is not None:
        try:
            with anyio.fail_after(1):
                transcript = await history.trace_transcript(
                    session_id,
                    access.owner_id,
                    exchange_id,
                    highest_rank=access.observed_through_rank,
                    after_rank=-1,
                    limit=64,
                    channel=Channel.tool_result,
                )
                evidence.matched_results = retain_tool_results(
                    [
                        {"rank": message.rank, **part.model_dump(mode="json")}
                        for message in transcript.messages
                        for part in message.parts
                        if isinstance(part, ToolResultPart) and part.call_id in tool_ids
                    ]
                )
        except (TimeoutError, ValueError, SQLAlchemyError):
            # The invocation remains readable if optional history is unavailable.
            pass
    if access != await client.model_access(session_id, exchange_id, ref, authorization):
        raise HTTPException(403, "trace_model_access_denied")
    return evidence


@router.get(
    "/{session_id}/trace-tool/{exchange_id}/{ref}",
    operation_id="get_trace_tool_evidence",
)
async def get_trace_tool_evidence(
    session_id: Session,
    exchange_id: Exchange,
    ref: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
) -> TraceToolEvidence:
    response.headers["Cache-Control"] = "no-store"
    client = container.conversation_trace_client
    if client is None or client.artifacts is None:
        raise HTTPException(503, "trace_tool_unavailable")
    authorization = request.headers.get("Authorization", "")
    access = await client.tool_access(session_id, exchange_id, ref, authorization)
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_tool_access_denied")
    try:
        with anyio.fail_after(5):
            result = await client.read_tool(session_id, ref)
    except Exception as exc:
        raise HTTPException(503, "trace_tool_unavailable") from exc
    if access != await client.tool_access(session_id, exchange_id, ref, authorization):
        raise HTTPException(403, "trace_tool_access_denied")
    return result


@router.get(
    "/{session_id}/trace-http/{exchange_id}/{ref}",
    operation_id="get_trace_http_evidence",
)
async def get_trace_http_evidence(
    session_id: Session,
    exchange_id: Exchange,
    ref: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
    request_offset: Annotated[int, Query(ge=0, lt=2**31)] = 0,
    response_offset: Annotated[int, Query(ge=0, lt=2**31)] = 0,
) -> TraceHttpEvidence:
    response.headers["Cache-Control"] = "no-store"
    client = container.conversation_trace_client
    if client is None or client.artifacts is None:
        raise HTTPException(503, "trace_http_unavailable")
    authorization = request.headers.get("Authorization", "")
    access = await client.http_access(session_id, exchange_id, ref, authorization)
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_http_access_denied")
    try:
        with anyio.fail_after(5):
            result = await client.read_artifact(
                session_id, ref, request_offset, response_offset
            )
    except Exception as exc:
        raise HTTPException(503, "trace_http_unavailable") from exc
    if access != await client.http_access(session_id, exchange_id, ref, authorization):
        raise HTTPException(403, "trace_http_access_denied")
    return result


@router.get(
    "/{session_id}/trace-sse/{exchange_id}/{ref}/{index}",
    operation_id="get_trace_sse_frame",
)
async def get_trace_sse_frame(
    session_id: Session,
    exchange_id: Exchange,
    ref: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    index: Annotated[int, Path(ge=0, lt=2**31)],
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
) -> TraceSseFrame:
    response.headers["Cache-Control"] = "no-store"
    client = container.conversation_trace_client
    if client is None or client.artifacts is None:
        raise HTTPException(503, "trace_sse_unavailable")
    authorization = request.headers.get("Authorization", "")
    access = await client.sse_access(session_id, exchange_id, ref, index, authorization)
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_sse_access_denied")
    try:
        with anyio.fail_after(5):
            result = await client.read_sse(session_id, ref, access)
    except Exception as exc:
        raise HTTPException(503, "trace_sse_unavailable") from exc
    if access != await client.sse_access(
        session_id, exchange_id, ref, index, authorization
    ):
        raise HTTPException(403, "trace_sse_access_denied")
    return result


@router.get(
    "/{session_id}/trace-sse-frames/{exchange_id}/{ref}/{page}",
    operation_id="get_trace_sse_frame_page",
)
async def get_trace_sse_frame_page(
    session_id: Session,
    exchange_id: Exchange,
    ref: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    page: Annotated[int, Path(ge=0, lt=2**31 // TRACE_SSE_PAGE_FRAMES)],
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
    outgoing_payload: bool = False,
) -> TraceSseFramePage:
    response.headers["Cache-Control"] = "no-store"
    client = container.conversation_trace_client
    if client is None or client.artifacts is None:
        raise HTTPException(503, "trace_sse_unavailable")
    authorization = request.headers.get("Authorization", "")
    index = page * TRACE_SSE_PAGE_FRAMES
    access = await client.sse_access(session_id, exchange_id, ref, index, authorization)
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_sse_access_denied")
    try:
        with anyio.fail_after(5):
            result = await client.read_sse_page(
                session_id, ref, page, outgoing_payload=outgoing_payload
            )
    except Exception as exc:
        raise HTTPException(503, "trace_sse_unavailable") from exc
    if access != await client.sse_access(
        session_id, exchange_id, ref, index, authorization
    ):
        raise HTTPException(403, "trace_sse_access_denied")
    return result


@router.get(
    "/{session_id}/trace-sse-headers/{exchange_id}/{ref}",
    operation_id="get_trace_sse_headers",
)
async def get_trace_sse_headers(
    session_id: Session,
    exchange_id: Exchange,
    ref: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    _caller: Caller,
    container: Container,
    request: Request,
    response: Response,
) -> TraceSseHeaders:
    response.headers["Cache-Control"] = "no-store"
    client = container.conversation_trace_client
    if client is None or client.artifacts is None:
        raise HTTPException(503, "trace_sse_unavailable")
    authorization = request.headers.get("Authorization", "")
    access = await client.sse_header_access(session_id, exchange_id, ref, authorization)
    if access.local_content_access and not _allows_local_trace(container, request):
        raise HTTPException(403, "trace_sse_access_denied")
    try:
        with anyio.fail_after(5):
            result = await client.read_sse_headers(session_id, ref)
    except Exception as exc:
        raise HTTPException(503, "trace_sse_unavailable") from exc
    if access != await client.sse_header_access(
        session_id, exchange_id, ref, authorization
    ):
        raise HTTPException(403, "trace_sse_access_denied")
    return result
