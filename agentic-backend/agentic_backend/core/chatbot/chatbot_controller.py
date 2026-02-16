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

import asyncio
import logging
from typing import List, Literal, Optional, Union

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
    Resource,
    UserSecurity,
    VectorSearchHit,
    authorize_or_raise,
    decode_jwt,
    get_current_user,
    oauth2_scheme,
)
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.websockets import WebSocketState

from agentic_backend.application_context import (
    get_configuration,
    get_rebac_engine,
)
from agentic_backend.common.structures import FrontendSettings
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    # get_deep_search_enabled,
    # get_rag_knowledge_scope,
)
from agentic_backend.core.chatbot.attachment_service import AttachmentService
from agentic_backend.core.chatbot.chat_schema import (
    AwaitingHumanEvent,
    ChatAskInput,
    ChatbotRuntimeSummary,
    ChatMessage,
    ChatWsInput,
    ErrorEvent,
    FinalEvent,
    HitlChoice,
    HitlPayload,
    HumanResumeInput,
    MessagePart,
    Role,
    SessionEvent,
    SessionSchema,
    SessionWithFiles,
    StreamEvent,
    TextPart,
)
from agentic_backend.core.chatbot.chatbot_benchmark_call import (
    handle_chatbot_baseline_websocket,
)
from agentic_backend.core.chatbot.metric_structures import (
    MetricsBucket,
    MetricsResponse,
)
from agentic_backend.core.chatbot.session_orchestrator import (
    SessionOrchestrator,
)
from agentic_backend.core.chatbot.stream_transcoder import InterruptRaised

logger = logging.getLogger(__name__)


async def _safe_ws_send_text(websocket: WebSocket, data: str) -> bool:
    """
    Best-effort send: client disconnects (or server-side close) are expected and
    should not crash the handler or spam logs.
    """
    try:
        if websocket.client_state != WebSocketState.CONNECTED:
            return False
        await websocket.send_text(data)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False
    except Exception:
        logger.debug("WebSocket send failed", exc_info=True)
        return False


def _paginate_message_text(
    message: ChatMessage, text_offset: int = 0, text_limit: Optional[int] = None
) -> ChatMessage:
    if text_limit is None and text_offset == 0:
        return message

    parts = message.parts or []
    total = sum(len(p.text) for p in parts if isinstance(p, TextPart))
    if total == 0:
        return message

    start = min(text_offset, total)
    end = total if text_limit is None else min(total, start + text_limit)

    if start == 0 and end == total:
        return message

    paged_parts: List[MessagePart] = []
    cursor = 0
    for part in parts:
        if not isinstance(part, TextPart):
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


def _summarize_error(e: Exception, context: str | None = None) -> str:
    """
    Produce a single-line summary and log it once (no stack trace).
    Fred is stable and performant and should not spam logs with full tracebacks
    for expected errors (e.g. client disconnects, validation errors, etc).
    """
    summary = f"{type(e).__name__}: {e}"
    if context:
        logger.error("%s: %s", context, summary)
    else:
        logger.error("%s", summary)
    return summary


# ---------------- Echo types for UI OpenAPI ----------------

EchoPayload = Union[
    ChatMessage,
    AwaitingHumanEvent,
    MessagePart,
    HitlPayload,
    HitlChoice,
    ChatAskInput,
    StreamEvent,
    SessionEvent,
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
        "AwaitingHumanEvent",
        "MessagePart",
        "HitlPayload",
        "HitlChoice",
        "StreamEvent",
        "SessionEvent",
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
    agent_id: Optional[str] = None
    title: Optional[str] = None


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency to get the agent_manager from app.state."""
    return request.app.state.agent_manager


def get_session_orchestrator(request: Request) -> SessionOrchestrator:
    """Dependency to get the session_orchestrator from app.state."""
    return request.app.state.session_orchestrator


def get_attachment_service(request: Request) -> AttachmentService:
    """Dependency to get the attachment service from app.state.session_orchestrator."""
    return request.app.state.session_orchestrator.attachment_service


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


def _update_tokens_from_request(
    user: KeycloakUser,
    token: str,
    obj: Union[ChatAskInput, HumanResumeInput],
) -> tuple[KeycloakUser, str, str | None]:
    """
    Update active access/refresh tokens (and user) if the payload brings newer ones.
    Keeps behavior identical while shortening the main flow.
    """
    refresh_token: str | None = None
    incoming_token = getattr(obj, "access_token", None)
    incoming_refresh = getattr(obj, "refresh_token", None)

    if incoming_token and incoming_token != token:
        try:
            refreshed_user = decode_jwt(incoming_token)
        except HTTPException:
            logger.warning("Rejected invalid token provided via ChatAskInput payload.")
        else:
            if refreshed_user.uid != user.uid:
                logger.warning(
                    "WS token subject mismatch (current=%s new=%s); keeping previous token.",
                    user.uid,
                    refreshed_user.uid,
                )
            else:
                token = incoming_token
                user = refreshed_user
                if incoming_refresh:
                    refresh_token = incoming_refresh
    elif incoming_refresh:
        refresh_token = incoming_refresh
    return user, token, refresh_token


def _hydrate_runtime_context(
    runtime_context: Optional[RuntimeContext],
    token: str,
    refresh_token: str | None,
    user: KeycloakUser,
) -> RuntimeContext:
    """
    Ensure runtime_context carries the latest auth/user information.
    """
    ctx = runtime_context or RuntimeContext()
    ctx.access_token = token
    ctx.refresh_token = refresh_token
    ctx.user_id = user.uid
    ctx.user_groups = user.groups or None
    return ctx


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

    ws_input_adapter = TypeAdapter(ChatWsInput)

    async def process_human_resume(
        user: KeycloakUser,
        payload: HumanResumeInput,
        runtime_context: RuntimeContext,
    ):
        """
        Handles the 'human_resume' flow:
        1. Delegates to the orchestrator to resume the interrupted graph execution.
        2. Streams events via callbacks and sends the FinalEvent upon completion.
        """
        (
            session,
            final_messages,
        ) = await session_orchestrator.resume_interrupted_exchange(
            user=user,
            callback=ws_callback,
            session_callback=ws_session_callback,
            session_id=payload.session_id,
            exchange_id=payload.exchange_id,
            agent_id=payload.agent_id,
            resume_payload=payload.payload or {},
            runtime_context=runtime_context,
        )
        if not await _safe_ws_send_text(
            websocket,
            FinalEvent(
                type="final", messages=final_messages, session=session
            ).model_dump_json(),
        ):
            raise WebSocketDisconnect

    async def process_agentic_ask(
        user: KeycloakUser, payload: ChatAskInput, runtime_context: RuntimeContext
    ):
        """
        Regular agentic flow. We process a regular question from the user.
        1. Calls session_orchestrator.chat_ask_websocket() with the right params
        2. Forwards StreamEvents via ws_callback
        3. Sends FinalEvent at the end
        """
        session, final_messages = await session_orchestrator.chat_ask_websocket(
            user=user,
            callback=ws_callback,
            session_callback=ws_session_callback,
            session_id=payload.session_id,
            message=payload.message,
            agent_id=payload.agent_id,
            runtime_context=runtime_context,
            client_exchange_id=payload.client_exchange_id,
        )
        if not await _safe_ws_send_text(
            websocket,
            FinalEvent(
                type="final", messages=final_messages, session=session
            ).model_dump_json(),
        ):
            raise WebSocketDisconnect

    last_session_id: str | None = None

    try:
        while True:
            # We loop here receiving and replying with the same WebSocket connection
            client_request = None
            try:
                client_request = await websocket.receive_json()
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "[CHATBOT] recv raw session_id=%s payload=%s",
                        client_request.get("session_id")
                        if isinstance(client_request, dict)
                        else None,
                        client_request,
                    )

                async def ws_callback(msg_dict: dict):
                    # Callback to stream agent tokens/messages back to the client
                    # It handles both ChatMessage payloads and AwaitingHumanEvent emitted by interrupts.
                    logger.info(
                        "[CHATBOT WS] ws_callback session=%s exchange=%s type=%s keys=%s",
                        msg_dict.get("session_id"),
                        msg_dict.get("exchange_id"),
                        msg_dict.get("type") or "stream",
                        list(msg_dict.keys()),
                    )
                    msg_type = msg_dict.get("type")
                    if msg_type == "awaiting_human":
                        logger.info(
                            "[CHATBOT WS] awaiting_human outbound session=%s exchange=%s payload_keys=%s",
                            msg_dict.get("session_id"),
                            msg_dict.get("exchange_id"),
                            list((msg_dict.get("payload") or {}).keys()),
                        )
                        event = AwaitingHumanEvent(**msg_dict)
                        if not await _safe_ws_send_text(
                            websocket, event.model_dump_json()
                        ):
                            raise WebSocketDisconnect
                        return

                    event = StreamEvent(type="stream", message=ChatMessage(**msg_dict))
                    if not await _safe_ws_send_text(websocket, event.model_dump_json()):
                        raise WebSocketDisconnect

                async def ws_session_callback(session: SessionSchema):
                    # Callback to push session updates (e.g. title change)
                    event = SessionEvent(type="session", session=session)
                    if not await _safe_ws_send_text(websocket, event.model_dump_json()):
                        raise WebSocketDisconnect

                try:
                    # 1. Input Parsing: Validate against the Union of possible inputs
                    parsed = ws_input_adapter.validate_python(client_request)
                except ValidationError:
                    # Fallback: Assume it's a standard Ask input (backward compatibility)
                    parsed = ChatAskInput(**client_request)

                # 2. Security: Update user/tokens if the payload contains refreshed credentials
                user, token, active_refresh_token = _update_tokens_from_request(
                    user=user,
                    token=token,
                    obj=parsed,
                )

                # 3. Context Hydration: Prepare the runtime context with latest auth info
                runtime_context = _hydrate_runtime_context(
                    runtime_context=parsed.runtime_context,
                    token=token,
                    refresh_token=active_refresh_token,
                    user=user,
                )
                if isinstance(parsed, ChatAskInput):
                    last_session_id = parsed.session_id or last_session_id
                elif isinstance(parsed, HumanResumeInput):
                    last_session_id = parsed.session_id or last_session_id
                logger.info(
                    "[CHATBOT WS] parsed type=%s session_id=%s exchange_id=%s agent=%s has_runtime_ctx=%s",
                    type(parsed).__name__,
                    getattr(parsed, "session_id", None)
                    if hasattr(parsed, "session_id")
                    else None,
                    getattr(parsed, "exchange_id", None)
                    if hasattr(parsed, "exchange_id")
                    else None,
                    getattr(parsed, "agent_id", None)
                    if hasattr(parsed, "agent_id")
                    else None,
                    parsed.runtime_context is not None,
                )

                # 4. Dispatch Logic
                if isinstance(parsed, HumanResumeInput):
                    # Case A: Human-in-the-loop Resume
                    # The user is providing input to resume a paused agent execution.
                    await process_human_resume(
                        user=user, payload=parsed, runtime_context=runtime_context
                    )
                    # We then proceed with the next receive loop
                    continue
                elif isinstance(parsed, ChatAskInput):
                    # Case B: Standard Question
                    # The user is asking a new question to an agent.
                    await process_agentic_ask(
                        user=user, payload=parsed, runtime_context=runtime_context
                    )
                    continue
                else:
                    raise ValueError("Unsupported WebSocket input type.")

                # if get_deep_search_enabled(ask.runtime_context):
                #     rag_scope = get_rag_knowledge_scope(ask.runtime_context)
                #     if rag_scope == "general_only":
                #         logger.info(
                #             "[CHATBOT] Deep search ignored because RAG scope is general-only."
                #         )
                #     else:
                #         base_settings = agent_manager.get_agent_settings(ask.agent_id)
                #         delegate_to = (
                #             base_settings.metadata.get("deep_search_delegate_to")
                #             if base_settings and base_settings.metadata
                #             else None
                #         )
                #         if delegate_to:
                #             if agent_manager.get_agent_settings(delegate_to):
                #                 target_agent_id = delegate_to
                #                 logger.info(
                #                     "[CHATBOT] Deep search enabled; delegating %s request to %s.",
                #                     ask.agent_id,
                #                     delegate_to,
                #                 )
                #             else:
                #                 logger.warning(
                #                     "[CHATBOT] Deep search requested for %s but delegate '%s' is not configured; falling back.",
                #                     ask.agent_id,
                #                     delegate_to,
                #                 )

            except WebSocketDisconnect:
                logger.debug("Client disconnected from chatbot WebSocket")
                break
            except InterruptRaised:
                logger.info(
                    "[CHATBOT WS] interrupt raised; awaiting human response session=%s",
                    client_request.get("session_id", "unknown-session")
                    if isinstance(client_request, dict)
                    else "unknown-session",
                )
                # Control-flow: awaiting_human already sent to client.
                continue
            except asyncio.CancelledError:
                logger.error(
                    "[CHATBOT WS] CancelledError (likely client disconnected) session_id=%s",
                    client_request.get("session_id", "unknown-session")
                    if isinstance(client_request, dict)
                    else "unknown-session",
                )
                raise
            except Exception as e:
                summary = _summarize_error(
                    e, "INTERNAL Error processing chatbot client query"
                )
                session_id = (
                    client_request.get("session_id", "unknown-session")
                    if client_request
                    else "unknown-session"
                )
                sent = await _safe_ws_send_text(
                    websocket,
                    ErrorEvent(
                        type="error", content=summary, session_id=session_id
                    ).model_dump_json(),
                )
                if not sent:
                    logger.debug("WebSocket closed; cannot send error event.")
                # Align with baseline: stop the loop after an error.
                try:
                    await websocket.close(code=1011)
                except Exception:
                    logger.debug("WebSocket close failed", exc_info=True)
                    pass
                break
    except Exception as e:
        summary = _summarize_error(e, "EXTERNAL Error processing chatbot client query")
        await _safe_ws_send_text(
            websocket,
            ErrorEvent(
                type="error", content=summary, session_id="unknown-session"
            ).model_dump_json(),
        )
        try:
            await websocket.close(code=1011)
        except Exception:
            logger.debug("WebSocket close failed", exc_info=True)
            pass
    finally:
        if last_session_id:
            try:
                await session_orchestrator.release_session(last_session_id)
            except Exception:
                logger.debug(
                    "Session release failed for session_id=%s",
                    last_session_id,
                    exc_info=True,
                )


@router.websocket("/chatbot/query/ws-baseline")
async def websocket_chatbot_openai_baseline(websocket: WebSocket):
    """
    This endpoint is used to benchmark Fred against an extra simple one-call only
    llm inetraction. It basically allow us to measure easily the overhead of Fred
    against a direct call.
    The actual logic is implemented in handle_chatbot_baseline_websocket()

    Refer to the companion golang benchmark client for more details.
    """
    await websocket.accept()

    await handle_chatbot_baseline_websocket(
        websocket,
        safe_send_text=_safe_ws_send_text,
        summarize_error=_summarize_error,
    )


@router.get(
    "/chatbot/sessions",
    description="Get the list of active chatbot sessions.",
    summary="Get the list of active chatbot sessions.",
)
async def get_sessions(
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> list[SessionWithFiles]:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("[CHATBOT] get_sessions start user=%s", user.uid)
    return await session_orchestrator.get_sessions(user)


@router.post(
    "/chatbot/session",
    description="Create a new empty chatbot session.",
    summary="Create chatbot session.",
    response_model=SessionSchema,
)
async def create_session(
    payload: CreateSessionPayload = Body(default_factory=CreateSessionPayload),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> SessionSchema:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[CHATBOT] create_session start user=%s agent_id=%s title=%s",
            user.uid,
            payload.agent_id,
            payload.title,
        )
    return await session_orchestrator.create_empty_session(
        user=user, agent_id=payload.agent_id, title=payload.title
    )


@router.get(
    "/chatbot/session/{session_id}/history",
    description="Get the history of a chatbot session.",
    summary="Get the history of a chatbot session.",
    response_model=List[ChatMessage],
)
async def get_session_history(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1),
    offset: int = Query(0, ge=0),
    text_limit: Optional[int] = Query(None, ge=1),
    text_offset: int = Query(0, ge=0),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> list[ChatMessage]:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[CHATBOT] get_session_history start session=%s user=%s",
            session_id,
            user.uid,
        )
    history = await session_orchestrator.get_session_history(
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
async def get_session_message(
    session_id: str,
    rank: int,
    text_limit: Optional[int] = Query(None, ge=1),
    text_offset: int = Query(0, ge=0),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> ChatMessage:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[CHATBOT] get_session_message start session=%s rank=%s user=%s",
            session_id,
            rank,
            user.uid,
        )
    message = await session_orchestrator.get_session_message(session_id, rank, user)
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
async def get_session_preferences(
    session_id: str,
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
    user: KeycloakUser = Depends(get_current_user),
):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[CHATBOT] get_session_preferences start session=%s user=%s",
            session_id,
            user.uid,
        )
    return await session_orchestrator.get_session_preferences(session_id, user)


@router.put(
    "/chatbot/session/{session_id}/preferences",
    response_model=dict,
    tags=["Chatbot"],
)
async def update_session_preferences(
    session_id: str,
    payload: SessionPreferencesPayload,
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
    user: KeycloakUser = Depends(get_current_user),
):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[CHATBOT] update_session_preferences start session=%s user=%s",
            session_id,
            user.uid,
        )
    return await session_orchestrator.update_session_preferences(
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
    attachment_service: AttachmentService = Depends(get_attachment_service),
) -> dict:
    authorize_or_raise(user, Action.CREATE, Resource.MESSAGE_ATTACHMENTS)
    authorize_or_raise(user, Action.CREATE, Resource.SESSIONS)
    return await attachment_service.add_attachment_from_upload(
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
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[CHATBOT] get_file_summary start session=%s attachment=%s user=%s",
            session_id,
            attachment_id,
            user.uid,
        )
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
