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

from datetime import datetime, timezone
from typing import Annotated, TypeVar
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.conversation_trace import (
    TRACE_MAX_SSE_FRAMES,
    TraceAdmission,
    TraceAdmissionRequest,
    TraceFinalization,
    TraceHistoryAccess,
    TraceHistoryBoundary,
    TraceHistoryTranscript,
    TraceHttpArtifactAccess,
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceHttpEvidence,
    TraceModelArtifactAccess,
    TraceModelCall,
    TraceModelEvidence,
    TraceModelIndex,
    TraceSseArtifactAccess,
    TraceSseFrame,
    TraceSseSegment,
    TraceToolArtifactAccess,
    TraceToolCall,
    TraceToolEvidence,
    is_local_trace_request,
)
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.delegation import AssertedUser
from fred_core.security.oidc import get_current_user_or_service, require_own_credential
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
)
from fred_core.security.structure import (
    LOCAL_DEV_CLIENT_ID,
    is_service_agent,
)
from pydantic import TypeAdapter

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceCatalog,
    ConversationTraceDetail,
    ConversationTraceSettings,
    TraceConsentGrant,
    TraceConsentRequest,
    TraceConsentState,
)
from control_plane_backend.conversation_traces.store import (
    TraceConsentChanged,
    TraceConsentDoesNotExtend,
    TraceConversationReference,
    TraceSessionNotFound,
)
from control_plane_backend.teams.system import resolve_system_team_id

router = APIRouter(tags=["ConversationTraces"])
Container = Annotated[ControlPlaneContainer, Depends(get_application_container)]
Owner = Annotated[KeycloakUser, Depends(require_own_credential)]
SessionId = Annotated[str, Path(min_length=1, max_length=255)]
RouteTeamId = Annotated[TeamId, Path(min_length=1, max_length=255)]
ExchangeId = Annotated[str, Path(min_length=1, max_length=255)]
ArtifactRef = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
FrameIndex = Annotated[int, Path(ge=0, lt=TRACE_MAX_SSE_FRAMES)]

_TraceResponse = TypeVar("_TraceResponse")
_BOUNDARY = TypeAdapter(TraceHistoryBoundary | None)
_HISTORY_TURNS = TypeAdapter(list[TraceHistoryBoundary])
_TRANSCRIPT = TypeAdapter(TraceHistoryTranscript)
_HTTP_EXCHANGE = TypeAdapter(TraceHttpEvidence)
_SSE_FRAME = TypeAdapter(TraceSseFrame)
_MODEL_EVIDENCE = TypeAdapter(TraceModelEvidence)
_TOOL_EVIDENCE = TypeAdapter(TraceToolEvidence)


async def _runtime_history(
    container: ControlPlaneContainer,
    reference: TraceConversationReference,
    authorization: str,
    path: str,
    decoder: TypeAdapter[_TraceResponse],
    *,
    params: dict[str, str | int] | None = None,
) -> _TraceResponse:
    source = next(
        (
            item
            for item in container.configuration.platform.runtime_catalog_sources
            if item.enabled
            and item.runtime_id == reference.runtime_id
            and getattr(item, "base_url", None)
        ),
        None,
    )
    if source is None or reference.session_id in {".", ".."}:
        raise HTTPException(503, "trace_history_unavailable")
    session_path = quote(reference.session_id, safe="")
    url = f"{source.base_url.rstrip('/')}/agents/sessions/{session_path}/{path}"
    try:
        result = await container.get_runtime_http_client().get(
            url,
            params=params,
            headers={"Authorization": authorization},
        )
        if result.status_code in {401, 403}:
            raise HTTPException(403, "trace_history_access_denied")
        result.raise_for_status()
        return decoder.validate_json(result.content)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "trace_history_unavailable") from exc


def _local_content_access(container: ControlPlaneContainer, request: Request) -> bool:
    return (
        container.get_conversation_trace_store().local_development
        and is_local_trace_request(
            request.client.host if request.client is not None else None,
            request.url.hostname,
        )
    )


async def _owned_conversation(
    container: ControlPlaneContainer,
    session_id: str,
    team_id: TeamId,
    user: KeycloakUser,
) -> TraceConversationReference:
    team_id = resolve_system_team_id(user, team_id) or team_id
    reference = await container.get_conversation_trace_store().reference(session_id)
    if (
        reference is None
        or reference.owner_id != user.uid
        or reference.team_id != team_id
    ):
        raise HTTPException(404, "conversation_trace_not_found")
    return reference


async def require_trace_operator(
    container: Container,
    user: Annotated[KeycloakUser, Depends(require_own_credential)],
) -> KeycloakUser:
    await container.get_rebac_engine().check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_CONVERSATION_TRACES, ORGANIZATION_ID
    )
    return user


Operator = Annotated[KeycloakUser, Depends(require_trace_operator)]


async def require_trace_runtime(
    runtime_id: Annotated[str, Path(min_length=1, max_length=255)],
    container: Container,
    user: Annotated[KeycloakUser | AssertedUser, Depends(get_current_user_or_service)],
) -> str:
    settings = container.configuration
    if not isinstance(user, KeycloakUser) or (
        not is_service_agent(user)
        if settings.security.m2m.enabled
        else user.client_id != LOCAL_DEV_CLIENT_ID
    ):
        raise HTTPException(403, "workload_caller_not_allowed")
    if not any(
        source.enabled
        and source.runtime_id == runtime_id
        and source.preparation_client_id is not None
        and source.preparation_client_id == user.client_id
        for source in settings.platform.runtime_catalog_sources
    ):
        raise HTTPException(403, "workload_caller_not_allowed")
    return runtime_id


Runtime = Annotated[str, Depends(require_trace_runtime)]


@router.get(
    "/admin/conversation-traces/settings",
    operation_id="get_conversation_trace_settings",
)
async def get_conversation_trace_settings(
    container: Container, _user: Operator
) -> ConversationTraceSettings:
    return ConversationTraceSettings(
        enabled=await container.get_conversation_trace_store().enabled()
    )


@router.put(
    "/admin/conversation-traces/settings",
    operation_id="set_conversation_trace_settings",
)
async def set_conversation_trace_settings(
    body: ConversationTraceSettings, container: Container, user: Operator
) -> ConversationTraceSettings:
    await container.get_conversation_trace_store().set_enabled(body.enabled)
    emit_audit_log(
        "conversation_trace.settings.updated",
        user_id=user.uid,
        enabled=body.enabled,
    )
    return body


@router.get("/admin/conversation-traces", operation_id="list_conversation_traces")
async def list_conversation_traces(
    container: Container,
    _user: Operator,
    failed_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
) -> ConversationTraceCatalog:
    before = None
    if cursor is not None:
        try:
            timestamp, capture_id = cursor.split("|", 1)
            parsed = datetime.fromisoformat(timestamp)
            before = (
                parsed
                if parsed.tzinfo is not None
                else parsed.replace(tzinfo=timezone.utc),
                str(UUID(capture_id)),
            )
        except ValueError as exc:
            raise HTTPException(422, "invalid_trace_cursor") from exc
    return await container.get_conversation_trace_store().list_conversations(
        failed_only=failed_only,
        limit=limit,
        before=before,
    )


@router.get(
    "/teams/{team_id}/sessions/{session_id}/trace-consent",
    operation_id="get_trace_consent",
)
async def get_trace_consent(
    team_id: RouteTeamId,
    session_id: SessionId,
    user: Owner,
    container: Container,
    request: Request,
    response: Response,
) -> TraceConsentState:
    response.headers["Cache-Control"] = "no-store"
    reference = await _owned_conversation(container, session_id, team_id, user)
    try:
        cutoff = await _runtime_history(
            container,
            reference,
            request.headers.get("Authorization", ""),
            "trace-history-boundary",
            _BOUNDARY,
        )
    except HTTPException:
        return TraceConsentState(
            consent=reference.consent,
            consent_version=reference.consent_version,
            history_unavailable=True,
        )
    return TraceConsentState(
        consent=reference.consent,
        consent_version=reference.consent_version,
        available_cutoff=cutoff,
    )


@router.put(
    "/teams/{team_id}/sessions/{session_id}/trace-consent",
    operation_id="set_trace_consent",
)
async def set_trace_consent(
    team_id: RouteTeamId,
    session_id: SessionId,
    body: TraceConsentRequest,
    user: Owner,
    container: Container,
    request: Request,
    response: Response,
) -> TraceConsentState:
    response.headers["Cache-Control"] = "no-store"
    reference = await _owned_conversation(container, session_id, team_id, user)
    cutoff = await _runtime_history(
        container,
        reference,
        request.headers.get("Authorization", ""),
        "trace-history-boundary",
        _BOUNDARY,
        params={"exchange_id": body.exchange_id},
    )
    if (
        cutoff is None
        or cutoff.exchange_id != body.exchange_id
        or cutoff.last_rank != body.last_rank
    ):
        raise HTTPException(409, "trace_consent_turn_changed")
    try:
        grant, action = await container.get_conversation_trace_store().set_consent(
            reference, cutoff, expected_version=body.expected_version
        )
    except TraceSessionNotFound as exc:
        raise HTTPException(404, "conversation_trace_not_found") from exc
    except TraceConsentChanged as exc:
        raise HTTPException(409, "trace_consent_changed") from exc
    except TraceConsentDoesNotExtend as exc:
        raise HTTPException(409, "trace_consent_does_not_extend") from exc
    if action is not None and grant is not None:
        _audit_consent(action, user.uid, session_id, grant.grant_id, cutoff)
    return TraceConsentState(
        consent=grant,
        consent_version=grant.grant_id if grant is not None else None,
        available_cutoff=cutoff,
    )


def _audit_consent(
    action: str,
    actor_id: str,
    session_id: str,
    grant_id: str,
    cutoff: TraceHistoryBoundary,
) -> None:
    emit_audit_log(
        f"conversation_trace.consent.{action}",
        user_id=actor_id,
        session_id=session_id,
        grant_id=grant_id,
        cutoff_exchange_id=cutoff.exchange_id,
        cutoff_turn=cutoff.turn_number,
        source="owner",
    )


@router.delete(
    "/teams/{team_id}/sessions/{session_id}/trace-consent",
    status_code=204,
    operation_id="revoke_trace_consent",
)
async def revoke_trace_consent(
    team_id: RouteTeamId, session_id: SessionId, user: Owner, container: Container
) -> Response:
    reference = await _owned_conversation(container, session_id, team_id, user)
    try:
        grant, action = await container.get_conversation_trace_store().set_consent(
            reference, None
        )
    except TraceSessionNotFound as exc:
        raise HTTPException(404, "conversation_trace_not_found") from exc
    if action is not None and grant is not None:
        _audit_consent(action, user.uid, session_id, grant.grant_id, grant.cutoff)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get(
    "/admin/conversation-traces/{session_id}", operation_id="get_conversation_trace"
)
async def get_conversation_trace(
    session_id: SessionId,
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=266)] = None,
) -> ConversationTraceDetail:
    response.headers["Cache-Control"] = "no-store"
    after = None
    if cursor is not None:
        try:
            rank, exchange_id = cursor.split("|", 1)
            if (
                not rank.isascii()
                or not rank.isdecimal()
                or len(rank) > 10
                or int(rank) >= 2**31
                or not 1 <= len(exchange_id) <= 255
            ):
                raise ValueError("invalid history rank or exchange")
            after = (int(rank), exchange_id)
        except ValueError as exc:
            raise HTTPException(422, "invalid_trace_cursor") from exc
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if reference is None or not reference.visible:
        raise HTTPException(404, "conversation_trace_not_found")
    params: dict[str, int | str] = {"limit": limit + 1}
    if after is not None:
        params.update(after_rank=after[0], after_exchange=after[1])
    try:
        retained_turns = await _runtime_history(
            container,
            reference,
            request.headers.get("Authorization", ""),
            "trace-history-turns",
            _HISTORY_TURNS,
            params=params,
        )
    except HTTPException:
        retained_turns = []
    # Re-read the active grant after making an independent runtime request.
    reference = await store.reference(session_id)
    if reference is None or not reference.visible:
        raise HTTPException(404, "conversation_trace_not_found")
    return await store.conversation_page(
        reference,
        limit=limit,
        after=after,
        retained_turns=retained_turns,
        local_content_access=_local_content_access(container, request),
    )


@router.get(
    "/admin/conversation-traces/{session_id}/history-access",
    operation_id="get_conversation_trace_history_access",
)
async def get_conversation_trace_history_access(
    session_id: SessionId,
    runtime_id: Annotated[str, Query(min_length=1, max_length=255)],
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
    exchange_id: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
) -> TraceHistoryAccess:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if reference is None or not reference.visible or reference.runtime_id != runtime_id:
        raise HTTPException(403, "trace_history_access_denied")
    grant = reference.consent
    return TraceHistoryAccess(
        owner_id=reference.owner_id,
        cutoff=grant.cutoff if grant is not None else None,
        grant_id=grant.grant_id if grant is not None else None,
        local_content_access=_local_content_access(container, request),
        captured_rank=(
            await store.capture_start_rank(session_id, exchange_id)
            if exchange_id is not None
            else None
        ),
    )


@router.get(
    "/admin/conversation-traces/{session_id}/history/{exchange_id}",
    operation_id="get_conversation_trace_history",
)
async def get_conversation_trace_history(
    session_id: SessionId,
    exchange_id: ExchangeId,
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
    after_rank: Annotated[int, Query(ge=-1, lt=2**31)] = -1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TraceHistoryTranscript:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if (
        reference is None
        or not reference.visible
        or exchange_id in {".", ".."}
        or (reference.consent is None and not _local_content_access(container, request))
    ):
        raise HTTPException(403, "trace_history_access_denied")
    result = await _runtime_history(
        container,
        reference,
        request.headers.get("Authorization", ""),
        f"trace-history-turns/{quote(exchange_id, safe='')}",
        _TRANSCRIPT,
        params={"after_rank": after_rank, "limit": limit},
    )
    current = await store.reference(session_id)
    if current is None or not current.visible or current.consent != reference.consent:
        raise HTTPException(403, "trace_history_access_denied")
    return result


@router.get(
    "/admin/conversation-traces/{session_id}/http/{exchange_id}",
    operation_id="list_conversation_trace_http_attempts",
)
async def list_conversation_trace_http_attempts(
    session_id: SessionId,
    exchange_id: ExchangeId,
    container: Container,
    _user: Operator,
    response: Response,
) -> list[TraceHttpAttempt]:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if reference is None or not reference.visible:
        raise HTTPException(404, "conversation_trace_not_found")
    return [
        attempt
        for attempt in await store.http_attempts(session_id, exchange_id)
        if attempt.tool_ref is None
    ]


async def _artifact_permission(
    container: ControlPlaneContainer,
    reference: TraceConversationReference | None,
    request: Request,
    exchange_id: str,
    *,
    kind: str,
) -> tuple[TraceConversationReference, bool, TraceConsentGrant | None]:
    if reference is None or not reference.visible or exchange_id in {".", ".."}:
        raise HTTPException(403, f"trace_{kind}_access_denied")
    store = container.get_conversation_trace_store()
    local = _local_content_access(container, request)
    grant = reference.consent
    rank = await store.capture_start_rank(reference.session_id, exchange_id)
    if rank is None or (
        not local
        and (
            grant is None
            or (rank, exchange_id) > (grant.cutoff.first_rank, grant.cutoff.exchange_id)
        )
    ):
        raise HTTPException(403, f"trace_{kind}_access_denied")
    return reference, local, grant


async def _http_artifact_access(
    container: ControlPlaneContainer,
    reference: TraceConversationReference | None,
    request: Request,
    exchange_id: str,
    ref: str,
) -> TraceHttpArtifactAccess:
    reference, local, grant = await _artifact_permission(
        container, reference, request, exchange_id, kind="http"
    )
    store = container.get_conversation_trace_store()
    attempts = await store.http_attempts(reference.session_id, exchange_id)
    attempt = next((item for item in attempts if item.ref == ref), None)
    if attempt is None or attempt.completeness == TraceHttpCompleteness.UNAVAILABLE:
        raise HTTPException(404, "trace_http_unavailable")
    if not local and (
        grant is None
        or attempt.observed_through_rank is None
        or attempt.observed_through_rank > grant.cutoff.last_rank
    ):
        raise HTTPException(403, "trace_http_access_denied")
    return TraceHttpArtifactAccess(
        grant_id=grant.grant_id if grant is not None else None,
        local_content_access=local,
        attempt=attempt,
    )


@router.get(
    "/admin/conversation-traces/{session_id}/http-access",
    operation_id="get_conversation_trace_http_access",
)
async def get_conversation_trace_http_access(
    session_id: SessionId,
    runtime_id: Annotated[str, Query(min_length=1, max_length=255)],
    exchange_id: Annotated[str, Query(min_length=1, max_length=255)],
    ref: Annotated[str, Query(pattern=r"^[0-9a-f]{32}$")],
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceHttpArtifactAccess:
    response.headers["Cache-Control"] = "no-store"
    reference = await container.get_conversation_trace_store().reference(session_id)
    if reference is None or reference.runtime_id != runtime_id:
        raise HTTPException(403, "trace_http_access_denied")
    return await _http_artifact_access(container, reference, request, exchange_id, ref)


@router.get(
    "/admin/conversation-traces/{session_id}/http/{exchange_id}/{ref}",
    operation_id="get_conversation_trace_http_evidence",
)
async def get_conversation_trace_http_evidence(
    session_id: SessionId,
    exchange_id: ExchangeId,
    ref: ArtifactRef,
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceHttpEvidence:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    access = await _http_artifact_access(
        container, reference, request, exchange_id, ref
    )
    assert reference is not None
    result = await _runtime_history(
        container,
        reference,
        request.headers.get("Authorization", ""),
        f"trace-http/{quote(exchange_id, safe='')}/{ref}",
        _HTTP_EXCHANGE,
    )
    if access != await _http_artifact_access(
        container, await store.reference(session_id), request, exchange_id, ref
    ):
        raise HTTPException(403, "trace_http_access_denied")
    return result


@router.get(
    "/admin/conversation-traces/{session_id}/sse/{exchange_id}",
    operation_id="list_conversation_trace_sse_segments",
)
async def list_conversation_trace_sse_segments(
    session_id: SessionId,
    exchange_id: ExchangeId,
    container: Container,
    _user: Operator,
    response: Response,
) -> list[TraceSseSegment]:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if reference is None or not reference.visible:
        raise HTTPException(404, "conversation_trace_not_found")
    return await store.sse_segments(session_id, exchange_id)


async def _sse_artifact_access(
    container: ControlPlaneContainer,
    reference: TraceConversationReference | None,
    request: Request,
    exchange_id: str,
    ref: str,
    index: int,
) -> TraceSseArtifactAccess:
    reference, local, grant = await _artifact_permission(
        container, reference, request, exchange_id, kind="sse"
    )
    segments = await container.get_conversation_trace_store().sse_segments(
        reference.session_id, exchange_id
    )
    for segment in segments:
        lane = next(
            (lane for lane in (segment.outgoing, *segment.provider) if lane.ref == ref),
            None,
        )
        if lane is None:
            continue
        if not local and (
            grant is None
            or segment.observed_through_rank is None
            or segment.observed_through_rank > grant.cutoff.last_rank
        ):
            raise HTTPException(403, "trace_sse_access_denied")
        if (
            not 0 <= index < len(lane.frames)
            or (offset := lane.frames[index].offset) is None
        ):
            break
        return TraceSseArtifactAccess(
            grant_id=grant.grant_id if grant is not None else None,
            local_content_access=local,
            offset=offset,
            size=lane.frames[index].size,
        )
    raise HTTPException(404, "trace_sse_unavailable")


@router.get(
    "/admin/conversation-traces/{session_id}/sse-access",
    operation_id="get_conversation_trace_sse_access",
)
async def get_conversation_trace_sse_access(
    session_id: SessionId,
    runtime_id: Annotated[str, Query(min_length=1, max_length=255)],
    exchange_id: Annotated[str, Query(min_length=1, max_length=255)],
    ref: Annotated[str, Query(pattern=r"^[0-9a-f]{32}$")],
    index: Annotated[int, Query(ge=0, lt=TRACE_MAX_SSE_FRAMES)],
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceSseArtifactAccess:
    response.headers["Cache-Control"] = "no-store"
    reference = await container.get_conversation_trace_store().reference(session_id)
    if reference is None or reference.runtime_id != runtime_id:
        raise HTTPException(403, "trace_sse_access_denied")
    return await _sse_artifact_access(
        container, reference, request, exchange_id, ref, index
    )


@router.get(
    "/admin/conversation-traces/{session_id}/sse/{exchange_id}/{ref}/{index}",
    operation_id="get_conversation_trace_sse_frame",
)
async def get_conversation_trace_sse_frame(
    session_id: SessionId,
    exchange_id: ExchangeId,
    ref: ArtifactRef,
    index: FrameIndex,
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceSseFrame:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    access = await _sse_artifact_access(
        container, reference, request, exchange_id, ref, index
    )
    assert reference is not None
    result = await _runtime_history(
        container,
        reference,
        request.headers.get("Authorization", ""),
        f"trace-sse/{quote(exchange_id, safe='')}/{ref}/{index}",
        _SSE_FRAME,
    )
    if access != await _sse_artifact_access(
        container, await store.reference(session_id), request, exchange_id, ref, index
    ):
        raise HTTPException(403, "trace_sse_access_denied")
    return result


@router.get(
    "/admin/conversation-traces/{session_id}/model/{exchange_id}",
    operation_id="list_conversation_trace_model_calls",
)
async def list_conversation_trace_model_calls(
    session_id: SessionId,
    exchange_id: ExchangeId,
    container: Container,
    _user: Operator,
    response: Response,
) -> list[TraceModelCall]:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if reference is None or not reference.visible:
        raise HTTPException(404, "conversation_trace_not_found")
    return list(await store.model_calls(session_id, exchange_id))


async def _model_artifact_access(
    container: ControlPlaneContainer,
    reference: TraceConversationReference | None,
    request: Request,
    exchange_id: str,
    ref: str,
) -> tuple[TraceModelArtifactAccess, TraceModelIndex]:
    reference, local, grant = await _artifact_permission(
        container, reference, request, exchange_id, kind="model"
    )
    calls = await container.get_conversation_trace_store().model_calls(
        reference.session_id, exchange_id
    )
    call = next((item for item in calls if item.ref == ref), None)
    if call is None or call.completeness == TraceHttpCompleteness.UNAVAILABLE:
        raise HTTPException(404, "trace_model_unavailable")
    if not local and (
        grant is None
        or call.observed_through_rank is None
        or call.observed_through_rank > grant.cutoff.last_rank
    ):
        raise HTTPException(403, "trace_model_access_denied")
    return TraceModelArtifactAccess(
        grant_id=grant.grant_id if grant is not None else None,
        local_content_access=local,
        owner_id=reference.owner_id,
        observed_through_rank=call.observed_through_rank,
    ), call


@router.get(
    "/admin/conversation-traces/{session_id}/model-access",
    operation_id="get_conversation_trace_model_access",
)
async def get_conversation_trace_model_access(
    session_id: SessionId,
    runtime_id: Annotated[str, Query(min_length=1, max_length=255)],
    exchange_id: Annotated[str, Query(min_length=1, max_length=255)],
    ref: Annotated[str, Query(pattern=r"^[0-9a-f]{32}$")],
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceModelArtifactAccess:
    response.headers["Cache-Control"] = "no-store"
    reference = await container.get_conversation_trace_store().reference(session_id)
    if reference is None or reference.runtime_id != runtime_id:
        raise HTTPException(403, "trace_model_access_denied")
    access, _ = await _model_artifact_access(
        container, reference, request, exchange_id, ref
    )
    return access


@router.get(
    "/admin/conversation-traces/{session_id}/model/{exchange_id}/{ref}",
    operation_id="get_conversation_trace_model_evidence",
)
async def get_conversation_trace_model_evidence(
    session_id: SessionId,
    exchange_id: ExchangeId,
    ref: ArtifactRef,
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceModelEvidence:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    access, call = await _model_artifact_access(
        container, reference, request, exchange_id, ref
    )
    assert reference is not None
    evidence = await _runtime_history(
        container,
        reference,
        request.headers.get("Authorization", ""),
        f"trace-model/{quote(exchange_id, safe='')}/{ref}",
        _MODEL_EVIDENCE,
    )
    origins = await store.model_origins(
        session_id,
        exchange_id,
        call,
        cutoff_rank=reference.consent.cutoff.last_rank
        if reference.consent is not None and not access.local_content_access
        else None,
    )
    current, _ = await _model_artifact_access(
        container, await store.reference(session_id), request, exchange_id, ref
    )
    if access != current:
        raise HTTPException(403, "trace_model_access_denied")
    return evidence.model_copy(update={"origins": origins})


@router.get(
    "/admin/conversation-traces/{session_id}/tool/{exchange_id}",
    operation_id="list_conversation_trace_tool_calls",
)
async def list_conversation_trace_tool_calls(
    session_id: SessionId,
    exchange_id: ExchangeId,
    container: Container,
    _user: Operator,
    response: Response,
) -> list[TraceToolCall]:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    if reference is None or not reference.visible:
        raise HTTPException(404, "conversation_trace_not_found")
    return await store.tool_calls(session_id, exchange_id)


async def _tool_artifact_access(
    container: ControlPlaneContainer,
    reference: TraceConversationReference | None,
    request: Request,
    exchange_id: str,
    ref: str,
) -> TraceToolArtifactAccess:
    reference, local, grant = await _artifact_permission(
        container, reference, request, exchange_id, kind="tool"
    )
    calls = await container.get_conversation_trace_store().tool_calls(
        reference.session_id, exchange_id
    )
    call = next((call for call in calls if call.ref == ref), None)
    if call is None or call.completeness == TraceHttpCompleteness.UNAVAILABLE:
        raise HTTPException(404, "trace_tool_unavailable")
    if not local and (
        grant is None
        or call.observed_through_rank is None
        or call.observed_through_rank > grant.cutoff.last_rank
    ):
        raise HTTPException(403, "trace_tool_access_denied")
    return TraceToolArtifactAccess(
        grant_id=grant.grant_id if grant is not None else None,
        local_content_access=local,
        observed_through_rank=call.observed_through_rank,
    )


@router.get(
    "/admin/conversation-traces/{session_id}/tool-access",
    operation_id="get_conversation_trace_tool_access",
)
async def get_conversation_trace_tool_access(
    session_id: SessionId,
    runtime_id: Annotated[str, Query(min_length=1, max_length=255)],
    exchange_id: Annotated[str, Query(min_length=1, max_length=255)],
    ref: Annotated[str, Query(pattern=r"^[0-9a-f]{32}$")],
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceToolArtifactAccess:
    response.headers["Cache-Control"] = "no-store"
    reference = await container.get_conversation_trace_store().reference(session_id)
    if reference is None or reference.runtime_id != runtime_id:
        raise HTTPException(403, "trace_tool_access_denied")
    return await _tool_artifact_access(container, reference, request, exchange_id, ref)


@router.get(
    "/admin/conversation-traces/{session_id}/tool/{exchange_id}/{ref}",
    operation_id="get_conversation_trace_tool_evidence",
)
async def get_conversation_trace_tool_evidence(
    session_id: SessionId,
    exchange_id: ExchangeId,
    ref: ArtifactRef,
    container: Container,
    _user: Operator,
    request: Request,
    response: Response,
) -> TraceToolEvidence:
    response.headers["Cache-Control"] = "no-store"
    store = container.get_conversation_trace_store()
    reference = await store.reference(session_id)
    access = await _tool_artifact_access(
        container, reference, request, exchange_id, ref
    )
    assert reference is not None
    evidence = await _runtime_history(
        container,
        reference,
        request.headers.get("Authorization", ""),
        f"trace-tool/{quote(exchange_id, safe='')}/{ref}",
        _TOOL_EVIDENCE,
    )
    if access != await _tool_artifact_access(
        container, await store.reference(session_id), request, exchange_id, ref
    ):
        raise HTTPException(403, "trace_tool_access_denied")
    return evidence


@router.get(
    "/internal/runtimes/{runtime_id}/conversation-traces/{capture_id}/writable",
    operation_id="get_trace_capture_writable",
)
async def get_trace_capture_writable(
    capture_id: UUID, container: Container, runtime_id: Runtime
) -> bool:
    return await container.get_conversation_trace_store().can_write(
        runtime_id, str(capture_id)
    )


@router.post(
    "/internal/runtimes/{runtime_id}/conversation-traces/admit",
    response_model=TraceAdmission | None,
)
async def admit_trace_turn(
    body: TraceAdmissionRequest, container: Container, runtime_id: Runtime
) -> TraceAdmission | None:
    return await container.get_conversation_trace_store().admit(runtime_id, body)


@router.put(
    "/internal/runtimes/{runtime_id}/conversation-traces/{capture_id}", status_code=204
)
async def finalize_trace_turn(
    capture_id: UUID, body: TraceFinalization, container: Container, runtime_id: Runtime
) -> Response:
    accepted = await container.get_conversation_trace_store().finalize(
        runtime_id, str(capture_id), body
    )
    if not accepted and (
        body.http_attempts
        or body.sse is not None
        or body.model_calls
        or body.tool_calls
    ):
        raise HTTPException(409, "trace_capture_no_longer_writable")
    return Response(status_code=204)
