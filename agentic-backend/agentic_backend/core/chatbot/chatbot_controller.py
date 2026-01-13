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

from __future__ import annotations

import logging
from typing import List, Literal, Optional, Union
from uuid import uuid4

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Security,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fred_core import (
    Action,
    KeycloakUser,
    RBACProvider,
    UserSecurity,
    VectorSearchHit,
    decode_jwt,
    get_current_user,
    oauth2_scheme,
)
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from agentic_backend.application_context import get_configuration, get_rebac_engine
from agentic_backend.common.structures import AgentSettings, FrontendSettings
from agentic_backend.common.utils import log_exception
from agentic_backend.core.a2a.a2a_bridge import (
    get_proxy_for_agent,
    is_a2a_agent,
    stream_a2a_as_chat_messages,
)
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_deep_search_enabled,
    get_rag_knowledge_scope,
)
from agentic_backend.core.chatbot.chat_schema import (
    ChatAskInput,
    ChatbotRuntimeSummary,
    ChatMessage,
    ErrorEvent,
    FinalEvent,
    MessagePart,
    Role,
    SessionSchema,
    SessionWithFiles,
    StreamEvent,
    TextPart,
    make_user_text,
)
from agentic_backend.core.chatbot.metric_structures import (
    MetricsBucket,
    MetricsResponse,
)
from agentic_backend.core.chatbot.session_orchestrator import (
    SessionOrchestrator,
    _utcnow_dt,
)

logger = logging.getLogger(__name__)


def _paginate_message_text(
    message: ChatMessage, text_offset: int = 0, text_limit: Optional[int] = None
) -> ChatMessage:
    if text_limit is None and text_offset == 0:
        return message

    parts = message.parts or []
    total = sum(len(p.text) for p in parts if getattr(p, "type", None) == "text")
    if total == 0:
        return message

    start = min(text_offset, total)
    end = total if text_limit is None else min(total, start + text_limit)

    if start == 0 and end == total:
        return message

    paged_parts: List[MessagePart] = []
    cursor = 0
    for part in parts:
        if getattr(part, "type", None) != "text":
            paged_parts.append(part)
            continue

        text = part.text or ""
        next_cursor = cursor + len(text)
        if end <= cursor or start >= next_cursor:
            cursor = next_cursor
            continue

        slice_start = max(0, start - cursor)
        slice_end = min(len(text), end - cursor)
        if slice_end > slice_start:
            paged_parts.append(TextPart(text=text[slice_start:slice_end]))
        cursor = next_cursor

    extras = dict(message.metadata.extras or {})
    extras["text_pagination"] = {
        "offset": start,
        "limit": text_limit,
        "total": total,
        "has_more": end < total,
    }
    metadata = message.metadata.model_copy(update={"extras": extras})
    return message.model_copy(update={"parts": paged_parts, "metadata": metadata})


# ---------------- Echo types for UI OpenAPI ----------------

EchoPayload = Union[
    ChatMessage,
    ChatAskInput,
    StreamEvent,
    FinalEvent,
    ErrorEvent,
    SessionSchema,
    SessionWithFiles,
    MetricsResponse,
    MetricsBucket,
    VectorSearchHit,
    RuntimeContext,
    ChatbotRuntimeSummary,
]


class EchoEnvelope(BaseModel):
    kind: Literal[
        "ChatMessage",
        "StreamEvent",
        "FinalEvent",
        "ErrorEvent",
        "SessionSchema",
        "SessionWithFiles",
        "MetricsResponse",
        "MetricsBucket",
        "VectorSearchHit",
        "RuntimeContext",
        "ChatbotRuntimeSummary",
    ]
    payload: EchoPayload = Field(..., description="Schema payload being echoed")


class FrontendConfigDTO(BaseModel):
    frontend_settings: FrontendSettings
    user_auth: UserSecurity
    is_rebac_enabled: bool


class CreateSessionPayload(BaseModel):
    agent_name: Optional[str] = None
    title: Optional[str] = None


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency to get the agent_manager from app.state."""
    return request.app.state.agent_manager


def get_session_orchestrator(request: Request) -> SessionOrchestrator:
    """Dependency to get the session_orchestrator from app.state."""
    return request.app.state.session_orchestrator


def get_agent_manager_ws(websocket: WebSocket) -> AgentManager:
    """Dependency to get the agent_manager from app.state for WebSocket."""
    return websocket.app.state.agent_manager


def get_session_orchestrator_ws(websocket: WebSocket) -> SessionOrchestrator:
    """Dependency to get the session_orchestrator from app.state for WebSocket."""
    return websocket.app.state.session_orchestrator


# Create a RBAC provider object to retrieve user permissions in the config/permissions route
rbac_provider = RBACProvider()

# Create an APIRouter instance here
router = APIRouter(tags=["Frontend"])


@router.post(
    "/schemas/echo",
    tags=["Schemas"],
    summary="Ignore. Not a real endpoint.",
    description="Ignore. This endpoint is only used to include some types (mainly one used in websocket) in the OpenAPI spec, so they can be generated as typescript types for the UI. This endpoint is not really used, this is just a code generation hack.",
)
def echo_schema(envelope: EchoEnvelope) -> None:
    pass


@router.get(
    "/config/frontend_settings",
    summary="Get the frontend dynamic configuration",
)
def get_frontend_config() -> FrontendConfigDTO:
    cfg = get_configuration()
    return FrontendConfigDTO(
        frontend_settings=cfg.frontend_settings,
        user_auth=UserSecurity(
            enabled=cfg.security.user.enabled,
            realm_url=cfg.security.user.realm_url,
            client_id=cfg.security.user.client_id,
        ),
        is_rebac_enabled=get_rebac_engine().enabled,
    )


@router.get(
    "/config/permissions",
    summary="Get the current user's permissions",
    response_model=list[str],
)
def get_user_permissions(
    current_user: KeycloakUser = Depends(get_current_user),
) -> list[str]:
    """
    Return a flat list of 'resource:action' strings the user is allowed to perform.:
    """
    return rbac_provider.list_permissions_for_user(current_user)


@router.get(
    "/chatbot/agenticflows",
    description="Get the list of available agentic flows",
    summary="Get the list of available agentic flows",
)
def get_agentic_flows(
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),  # Inject the dependency
) -> List[AgentSettings]:
    flows = agent_manager.get_agentic_flows()
    return flows


@router.websocket("/chatbot/query/ws")
async def websocket_chatbot_question(
    websocket: WebSocket,
    session_orchestrator: SessionOrchestrator = Depends(
        get_session_orchestrator_ws
    ),  # Use WebSocket-specific dependency
    agent_manager: AgentManager = Depends(get_agent_manager_ws),
):
    """
    Transport-only:
      - Accept WS
      - Parse ChatAskInput
      - Provide a callback that forwards StreamEvents
      - Send FinalEvent or ErrorEvent
      - All heavy lifting is in SessionOrchestrator.chat_ask_websocket()
    """
    # All other code is the same, but it now uses the injected dependencies
    # `agent_manager` and `session_orchestrator` which are guaranteed to be
    # the correct, lifespan-managed instances.
    await websocket.accept()
    auth = websocket.headers.get("authorization") or ""
    token = (
        auth.split(" ", 1)[1]
        if auth.lower().startswith("bearer ")
        else websocket.query_params.get("token")
    )
    if not token:
        await websocket.close(code=4401)
        return

    try:
        user = decode_jwt(token)
    except HTTPException:
        await websocket.close(code=4401)
        return

    active_token = token
    active_user = user
    active_refresh_token: str | None = None

    try:
        while True:
            client_request = None
            try:
                client_request = await websocket.receive_json()
                ask = ChatAskInput(**client_request)

                incoming_token = ask.access_token
                incoming_refresh = ask.refresh_token
                if incoming_token and incoming_token != active_token:
                    try:
                        refreshed_user = decode_jwt(incoming_token)
                    except HTTPException:
                        logger.warning(
                            "Rejected invalid token provided via ChatAskInput payload."
                        )
                    else:
                        if refreshed_user.uid != active_user.uid:
                            logger.warning(
                                "WS token subject mismatch (current=%s new=%s); keeping previous token.",
                                active_user.uid,
                                refreshed_user.uid,
                            )
                        else:
                            active_token = incoming_token
                            active_user = refreshed_user
                            if incoming_refresh:
                                active_refresh_token = incoming_refresh
                elif incoming_refresh:
                    active_refresh_token = incoming_refresh

                # TODO HACK SEND THE TOKEN DIRECTLY IN RUNTIME CONTEXT
                if not ask.runtime_context:
                    ask.runtime_context = RuntimeContext()
                ask.runtime_context.access_token = active_token
                ask.runtime_context.refresh_token = active_refresh_token
                ask.runtime_context.user_id = active_user.uid

                target_agent_name = ask.agent_name
                if get_deep_search_enabled(ask.runtime_context):
                    rag_scope = get_rag_knowledge_scope(ask.runtime_context)
                    if rag_scope == "general_only":
                        logger.info(
                            "[CHATBOT] Deep search ignored because RAG scope is general-only."
                        )
                    else:
                        base_settings = agent_manager.get_agent_settings(ask.agent_name)
                        delegate_to = (
                            base_settings.metadata.get("deep_search_delegate_to")
                            if base_settings and base_settings.metadata
                            else None
                        )
                        if delegate_to:
                            if agent_manager.get_agent_settings(delegate_to):
                                target_agent_name = delegate_to
                                logger.info(
                                    "[CHATBOT] Deep search enabled; delegating %s request to %s.",
                                    ask.agent_name,
                                    delegate_to,
                                )
                            else:
                                logger.warning(
                                    "[CHATBOT] Deep search requested for %s but delegate '%s' is not configured; falling back.",
                                    ask.agent_name,
                                    delegate_to,
                                )

                async def ws_callback(msg_dict: dict):
                    event = StreamEvent(type="stream", message=ChatMessage(**msg_dict))
                    await websocket.send_text(event.model_dump_json())

                # Route to A2A proxy if the stub agent is selected
                target_settings = agent_manager.get_agent_settings(target_agent_name)
                if target_settings and is_a2a_agent(target_settings):
                    meta = target_settings.metadata or {}
                    base_url = meta.get("a2a_base_url")
                    configured_a2a_token = meta.get("a2a_token")
                    force_disable_streaming = bool(meta.get("a2a_disable_streaming"))
                    if not base_url:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Agent '{target_agent_name}' is marked as A2A but is missing 'a2a_base_url' metadata.",
                        )
                    proxy = get_proxy_for_agent(
                        websocket.app,
                        target_agent_name,
                        base_url,
                        token,
                        force_disable_streaming=force_disable_streaming,
                    )
                    session_id = ask.session_id or f"a2a-{uuid4()}"
                    # If a session_id was provided, enforce ownership to match regular agents
                    if ask.session_id:
                        session_orchestrator._authorize_user_action_on_session(  # type: ignore[attr-defined]
                            ask.session_id, active_user, Action.UPDATE
                        )
                    # Get or create the persisted session just like the regular flow
                    session = session_orchestrator._get_or_create_session(  # type: ignore[attr-defined]
                        user_id=active_user.uid,
                        query=ask.message,
                        session_id=session_id,
                    )
                    prior = session_orchestrator.history_store.get(session.id) or []
                    base_rank = len(prior)
                    exchange_id = ask.client_exchange_id or str(uuid4())
                    rank = base_rank

                    # Emit the user message first
                    user_msg = make_user_text(
                        session_id, exchange_id, rank, ask.message
                    )
                    collected_messages = [user_msg]
                    await websocket.send_text(
                        StreamEvent(type="stream", message=user_msg).model_dump_json()
                    )
                    rank += 1

                    async for msg in stream_a2a_as_chat_messages(
                        proxy=proxy,
                        user_id=active_user.uid,
                        # Prefer the configured agent token; fall back to the caller token.
                        access_token=configured_a2a_token or active_token,
                        text=ask.message,
                        session_id=session_id,
                        exchange_id=exchange_id,
                        start_rank=rank,
                    ):
                        rank = msg.rank + 1
                        collected_messages.append(msg)
                        await websocket.send_text(
                            StreamEvent(type="stream", message=msg).model_dump_json()
                        )

                    session.updated_at = _utcnow_dt()
                    # Persist session + history so it behaves like regular agents
                    session_orchestrator.session_store.save(session)
                    session_orchestrator.history_store.save(
                        session.id, prior + collected_messages, active_user.uid
                    )
                    await websocket.send_text(
                        FinalEvent(
                            type="final", messages=collected_messages, session=session
                        ).model_dump_json()
                    )

                else:
                    (
                        session,
                        final_messages,
                    ) = await session_orchestrator.chat_ask_websocket(
                        user=active_user,
                        callback=ws_callback,
                        session_id=ask.session_id,
                        message=ask.message,
                        agent_name=target_agent_name,
                        runtime_context=ask.runtime_context,
                        client_exchange_id=ask.client_exchange_id,
                    )

                    await websocket.send_text(
                        FinalEvent(
                            type="final", messages=final_messages, session=session
                        ).model_dump_json()
                    )

            except WebSocketDisconnect:
                logger.debug("Client disconnected from chatbot WebSocket")
                break
            except Exception as e:
                summary = log_exception(
                    e, "INTERNAL Error processing chatbot client query"
                )
                session_id = (
                    client_request.get("session_id", "unknown-session")
                    if client_request
                    else "unknown-session"
                )
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(
                        ErrorEvent(
                            type="error", content=summary, session_id=session_id
                        ).model_dump_json()
                    )
                else:
                    logger.error("[🔌 WebSocket] Connection closed by client.")
                    break
    except Exception as e:
        summary = log_exception(e, "EXTERNAL Error processing chatbot client query")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(
                ErrorEvent(
                    type="error", content=summary, session_id="unknown-session"
                ).model_dump_json()
            )


@router.get(
    "/chatbot/sessions",
    description="Get the list of active chatbot sessions.",
    summary="Get the list of active chatbot sessions.",
)
def get_sessions(
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> list[SessionWithFiles]:
    return session_orchestrator.get_sessions(user)


@router.post(
    "/chatbot/session",
    description="Create a new empty chatbot session.",
    summary="Create chatbot session.",
    response_model=SessionSchema,
)
def create_session(
    payload: CreateSessionPayload = Body(default_factory=CreateSessionPayload),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> SessionSchema:
    return session_orchestrator.create_empty_session(
        user=user, agent_name=payload.agent_name, title=payload.title
    )


@router.get(
    "/chatbot/session/{session_id}/history",
    description="Get the history of a chatbot session.",
    summary="Get the history of a chatbot session.",
    response_model=List[ChatMessage],
)
def get_session_history(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1),
    offset: int = Query(0, ge=0),
    text_limit: Optional[int] = Query(None, ge=1),
    text_offset: int = Query(0, ge=0),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> list[ChatMessage]:
    history = session_orchestrator.get_session_history(
        session_id=session_id,
        user=user,
        limit=limit,
        offset=offset,
    )
    if text_limit is not None or text_offset > 0:
        history = [
            _paginate_message_text(m, text_offset=text_offset, text_limit=text_limit)
            if m.role == Role.user
            else m
            for m in history
        ]
    return history


@router.get(
    "/chatbot/session/{session_id}/message/{rank}",
    description="Get a single chatbot message by rank.",
    summary="Get a single chatbot message.",
    response_model=ChatMessage,
)
def get_session_message(
    session_id: str,
    rank: int,
    text_limit: Optional[int] = Query(None, ge=1),
    text_offset: int = Query(0, ge=0),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> ChatMessage:
    logger.info(
        "[CHATBOT] get_session_message start session=%s rank=%s user=%s",
        session_id,
        rank,
        user.uid,
    )
    message = session_orchestrator.get_session_message(session_id, rank, user)
    if text_limit is not None or text_offset > 0:
        message = _paginate_message_text(
            message, text_offset=text_offset, text_limit=text_limit
        )
    logger.info(
        "[CHATBOT] get_session_message done session=%s rank=%s user=%s",
        session_id,
        rank,
        user.uid,
    )
    return message


class SessionPreferencesPayload(BaseModel):
    preferences: dict = {}


@router.get(
    "/chatbot/session/{session_id}/preferences",
    response_model=dict,
    tags=["Chatbot"],
)
def get_session_preferences(
    session_id: str,
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
    user: KeycloakUser = Depends(get_current_user),
):
    return session_orchestrator.get_session_preferences(session_id, user)


@router.put(
    "/chatbot/session/{session_id}/preferences",
    response_model=dict,
    tags=["Chatbot"],
)
def update_session_preferences(
    session_id: str,
    payload: SessionPreferencesPayload,
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
    user: KeycloakUser = Depends(get_current_user),
):
    return session_orchestrator.update_session_preferences(
        session_id, user, payload.preferences
    )


@router.delete(
    "/chatbot/session/{session_id}",
    description="Delete a chatbot session.",
    summary="Delete a chatbot session.",
)
async def delete_session(
    session_id: str,
    user: KeycloakUser = Depends(get_current_user),
    access_token: str = Security(oauth2_scheme),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> bool:
    await session_orchestrator.delete_session(
        session_id, user, access_token=access_token
    )
    return True


@router.post(
    "/chatbot/upload",
    description="Upload a file to be attached to a chatbot conversation",
    summary="Upload a file",
)
async def upload_file(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    user: KeycloakUser = Depends(get_current_user),
    access_token: str = Security(oauth2_scheme),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> dict:
    return await session_orchestrator.add_attachment_from_upload(
        user=user, access_token=access_token, session_id=session_id, file=file
    )


@router.get(
    "/chatbot/upload/{attachment_id}/summary",
    description="Get the markdown summary generated for an uploaded file",
    summary="Get attachment summary",
)
async def get_file_summary(
    session_id: str,
    attachment_id: str,
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> dict:
    return await session_orchestrator.get_attachment_summary(
        user=user, session_id=session_id, attachment_id=attachment_id
    )


@router.delete(
    "/chatbot/upload/{attachment_id}",
    description="Delete an uploaded file from a chatbot conversation",
    summary="Delete an uploaded file",
)
async def delete_file(
    session_id: str,
    attachment_id: str,
    user: KeycloakUser = Depends(get_current_user),
    access_token: str = Security(oauth2_scheme),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> None:
    await session_orchestrator.delete_attachment(
        user=user,
        session_id=session_id,
        attachment_id=attachment_id,
        access_token=access_token,
    )
