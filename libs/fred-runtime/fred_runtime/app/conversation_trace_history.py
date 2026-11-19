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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fred_core import KeycloakUser
from fred_core.conversation_trace import (
    TraceHistoryAccess,
    TraceHistoryBoundary,
    TraceHistoryTranscript,
    is_local_trace_request,
)
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.security.oidc import require_own_credential

from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.dependencies import get_pod_container

router = APIRouter(prefix="/agents/sessions", tags=["ConversationTraceHistory"])
Container = Annotated[PodApplicationContext, Depends(get_pod_container)]
Caller = Annotated[KeycloakUser, Depends(require_own_credential)]
Session = Annotated[str, Path(min_length=1, max_length=255)]
Exchange = Annotated[str, Path(min_length=1, max_length=255)]
Rank = Annotated[int, Query(ge=-1, lt=2**31)]


def _history(container: PodApplicationContext) -> PostgresHistoryStore | None:
    store = container.get_history_store()
    return store if isinstance(store, PostgresHistoryStore) else None


@router.get(
    "/{session_id}/trace-history-boundary", operation_id="get_trace_history_boundary"
)
async def get_trace_history_boundary(
    session_id: Session,
    caller: Caller,
    container: Container,
    response: Response,
    exchange_id: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
) -> TraceHistoryBoundary | None:
    response.headers["Cache-Control"] = "no-store"
    store = _history(container)
    if store is None:
        return None
    return await store.trace_boundary(session_id, caller.uid, exchange_id)


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
    security = container.configuration.security
    if access.local_content_access and (
        security.profile is not None
        or security.user.enabled
        or security.m2m.enabled
        or (security.rebac is not None and security.rebac.enabled)
        or not is_local_trace_request(
            request.client.host if request.client is not None else None,
            request.url.hostname,
        )
    ):
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
) -> list[TraceHistoryBoundary]:
    response.headers["Cache-Control"] = "no-store"
    access = await _access(container, request, session_id)
    store = _history(container)
    if store is None:
        return []
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
        and (first_rank, exchange_id) > (cutoff.first_rank, cutoff.exchange_id)
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
