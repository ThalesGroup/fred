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
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fred_core import KeycloakUser
from fred_core.conversation_trace import (
    TraceAdmission,
    TraceAdmissionRequest,
    TraceFinalization,
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

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceCatalog,
    ConversationTraceDetail,
    ConversationTraceSettings,
)

router = APIRouter(tags=["ConversationTraces"])
Container = Annotated[ControlPlaneContainer, Depends(get_application_container)]


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
    "/admin/conversation-traces/{session_id}", operation_id="get_conversation_trace"
)
async def get_conversation_trace(
    session_id: Annotated[str, Path(min_length=1, max_length=255)],
    container: Container,
    _user: Operator,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
) -> ConversationTraceDetail:
    after = None
    if cursor is not None:
        try:
            rank, capture_id = cursor.split("|", 1)
            if (
                not rank.isascii()
                or not rank.isdecimal()
                or len(rank) > 10
                or int(rank) >= 2**31
            ):
                raise ValueError("invalid history rank")
            after = (int(rank), str(UUID(capture_id)))
        except ValueError as exc:
            raise HTTPException(422, "invalid_trace_cursor") from exc
    detail = await container.get_conversation_trace_store().get_conversation(
        session_id,
        limit=limit,
        after=after,
    )
    if detail is None:
        raise HTTPException(404, "conversation_trace_not_found")
    return detail


@router.post(
    "/internal/runtimes/{runtime_id}/conversation-traces/admit",
    response_model=TraceAdmission | None,
)
async def admit_trace_turn(
    body: TraceAdmissionRequest, container: Container, runtime_id: Runtime
) -> TraceAdmission | None:
    capture_id = await container.get_conversation_trace_store().admit(runtime_id, body)
    return TraceAdmission(capture_id=capture_id) if capture_id else None


@router.put(
    "/internal/runtimes/{runtime_id}/conversation-traces/{capture_id}", status_code=204
)
async def finalize_trace_turn(
    capture_id: UUID, body: TraceFinalization, container: Container, runtime_id: Runtime
) -> Response:
    await container.get_conversation_trace_store().finalize(
        runtime_id, str(capture_id), body
    )
    return Response(status_code=204)
